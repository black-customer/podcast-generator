"""OpenAI 兼容文本改写与 Agent 任务指令，校验音频文本与逐句材料。

数据契约（R03）：
- natural_english：干净、可背诵的地道英文回答（无任何表演标签）。
- podcast_text：用户可见的完整问答文本（A:/B: 对话，无表演标签）。
- podcast_script：隐藏的 TTS 表演稿（A:/B: 对话，只允许白名单标签）。
原始回答永远由 original_answer.txt 保存，改写失败也不得覆盖或清除。
"""
from __future__ import annotations

import json
import logging
import re
import threading
from urllib.parse import urlsplit

import httpx

from .audioqa import strip_all_tags, strip_disallowed_tags
from .config import DEFAULT_SETTINGS, real_llm_api_key

logger = logging.getLogger(__name__)
MAX_REPAIRS = 1
# 表演稿与可见文本的词义一致性下限（内容词 jaccard）。同义改写通常 >0.5。
SEMANTIC_OVERLAP_MIN = 0.35
SYSTEM_SCHEMA = (
    "Rewrite an IELTS learner's raw answer. Reply with one JSON object, no markdown. "
    'Schema: {"natural_english": str}.\n'
    "- natural_english: the clean, natural, first-person spoken English answer, "
    "directly recitable, no stage directions, no brackets.\n"
    "Keep the user's real experiences, opinions and details; never invent facts. "
    "Include the distinct details and meanings the learner gives in supplemental Chinese intent, "
    "even if those details are missing from the raw English. "
    "Only quote actual English from the original attempt as evidence of an error. "
    "For a lexical gap present in the intent but missing from the attempt, mark the matching "
    "sentence as explicit_gap and provide the missing expression as its key_chunk."
)

_REPAIR_INSTRUCTION = (
    "Your previous JSON was rejected:\n{errors}\n"
    "Return the corrected complete JSON object now, same schema, no commentary."
)


class RewriteError(RuntimeError):
    pass


class TextPermissionError(RewriteError):
    """Key 无文本模型权限或未配置——必须显式提示用户改用 Agent 模式。"""


class BundleFormatError(RewriteError):
    """合并响应无法提供可用音频文本，可以改用三文本生成。"""


class MultimodalUnsupportedError(RewriteError):
    """当前文本服务不能读取图片。"""


REQUIRED_FIELDS = ("natural_english", "podcast_text", "podcast_script")
_TAG_TEXT_RE = re.compile(r"\[([^\[\]]*)\]")
GENERATION_TAGS = frozenset({"curious", "relaxed", "uncertain", "emphasis", "break"})
_WORD_RE = re.compile(r"[a-z']{3,}")
_STOPWORDS = frozenset({
    "the", "and", "was", "were", "she", "her", "his", "him", "you", "your", "yor",
    "that", "this", "with", "for", "are", "but", "not", "just", "always", "very",
    "they", "them", "their", "there", "here", "what", "when", "how", "who", "why",
    "have", "has", "had", "did", "does", "don", "doesn", "didn", "can", "could",
    "would", "will", "into", "about", "from", "like", "some", "than", "then",
})


def original_answer_of(texts: dict) -> str:
    """原始回答读取：original_answer → chinese → natural_english（旧条目回退）。"""
    for field in ("original_answer", "chinese", "natural_english"):
        v = (texts.get(field) or "").strip()
        if v:
            return v
    return ""


def build_messages(question: str, english_attempt: str, chinese_intent: str = "") -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_SCHEMA},
        {
            "role": "user",
            "content": (
                f"Question:\n{(question or '').strip()}\n\n"
                f"The learner's raw answer (Chinese, English or mixed):\n"
                f"{(english_attempt or '').strip()}\n\n"
                "Optional Chinese intent (intended meaning, not evidence of an error):\n"
                f"{chinese_intent.strip()}"
            ),
        },
    ]


def _content_words(text: str) -> set[str]:
    words = set(_WORD_RE.findall((text or "").lower()))
    return words - _STOPWORDS


def _semantic_overlap(a: str, b: str) -> float:
    wa, wb = _content_words(a), _content_words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def validate_texts(texts: dict) -> list[str]:
    """结构校验：字段完整、A/B 对话格式、标签政策、可见文本与表演稿词义一致。"""
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if not isinstance(texts.get(field), str) or not texts[field].strip():
            errors.append(f"缺少必填字段或为空: {field}")
    if errors:
        return errors

    for field in ("natural_english", "podcast_text"):
        found = _TAG_TEXT_RE.findall(texts[field])
        if found:
            errors.append(f"可见文本 {field} 不允许任何表演标签，需输出干净英文: {found[:3]}")
    from .tts import parse_dialogue

    for field in ("podcast_text", "podcast_script"):
        dialogue = parse_dialogue(texts[field])
        if dialogue is None or dialogue[0][0] != "a":
            errors.append(f"{field} 必须是完整 A:/B: 对话格式（A=提问者，B=回答者）")

    generated_tags = [tag.strip().lower() for tag in _TAG_TEXT_RE.findall(texts["podcast_script"])]
    unsafe = [tag for tag in generated_tags if tag not in GENERATION_TAGS]
    if unsafe:
        errors.append(
            f"podcast_script 含新生成策略禁用标签 {unsafe[:3]}，"
            "只允许 curious/relaxed/uncertain/emphasis/break"
        )
    if generated_tags.count("curious") > 1 or generated_tags.count("relaxed") > 1:
        errors.append("curious/relaxed 开场标签各最多使用一次")
    extras = sum(generated_tags.count(tag) for tag in ("uncertain", "emphasis", "break"))
    if extras > 2:
        errors.append("回答中的 uncertain/emphasis/break 合计最多使用两个")

    _cleaned_script, removed = strip_disallowed_tags(texts["podcast_script"])
    if removed:
        errors.append(
            f"podcast_script 含白名单外标签 {removed[:3]}，只允许表演白名单内的标签"
        )

    visible = strip_all_tags(texts["podcast_text"])[0]
    spoken = strip_all_tags(_cleaned_script)[0]
    if (visible.split() != spoken.split() and
            _semantic_overlap(visible, spoken) < SEMANTIC_OVERLAP_MIN):
        errors.append("podcast_text 与 podcast_script 内容词义不一致（表演稿必须忠实于可见文本）")
    return errors


def _extract_json(content: str) -> dict:
    text = (content or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RewriteError(f"模型返回不是合法 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RewriteError("模型返回的 JSON 不是对象")
    return data


def text_config(settings: dict) -> tuple[str, str, str]:
    provider = settings.get("llm_provider") or "deepseek"
    key = real_llm_api_key(settings)
    base = str(settings.get("llm_base_url") or DEFAULT_SETTINGS["llm_base_url"])
    model = str(settings.get("llm_model") or DEFAULT_SETTINGS["llm_model"])
    base = base.strip().rstrip("/")
    try:
        parsed = urlsplit(base)
        loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    except ValueError as exc:
        raise RewriteError("文本改写 Base URL 无效") from exc
    secure_transport = parsed.scheme == "https" or (loopback and parsed.scheme == "http")
    if (not parsed.hostname or parsed.username or parsed.password or parsed.query or
            parsed.fragment or not secure_transport):
        raise RewriteError("文本改写 Base URL 需要 HTTPS，或使用本机 HTTP 地址")
    if loopback and provider == "custom":
        key = ""
    if not key and not (loopback and provider == "custom"):
        raise TextPermissionError("未配置文本改写 Key，请前往设置")
    return f"{base}/chat/completions", model.strip(), key


def text_available(settings: dict) -> bool:
    try:
        text_config(settings)
    except RewriteError:
        return False
    return True


def _chat(settings: dict, messages: list[dict], cancel: threading.Event | None, *,
          multimodal: bool = False) -> str:
    if cancel is not None and cancel.is_set():
        raise RewriteError("已取消")
    vision_base = settings.get("vision_base_url")
    vision_model = settings.get("vision_model")
    if multimodal and (vision_base or vision_model):
        if not vision_model:
            raise RewriteError("请在设置中填写独立视觉模型名称")
        settings = {**settings, "llm_model": vision_model}
        if vision_base:
            settings = {**settings, "llm_base_url": vision_base, "llm_provider": "custom",
                        "llm_api_key": settings.get("vision_api_key"), "deepseek_api_key": ""}
    url, model, key = text_config(settings)
    payload = {"model": model, "messages": messages, "response_format": {"type": "json_object"},
               "temperature": 0.6, "max_tokens": 4096}
    if urlsplit(url).hostname == "api.deepseek.com":
        payload["thinking"] = {"type": "disabled"}
    try:
        response = httpx.post(
            url, headers={"Authorization": f"Bearer {key}"} if key else {},
            json=payload, timeout=120,
        )
    except httpx.HTTPError as exc:
        raise RewriteError("无法连接文本改写服务，请检查网络和 Base URL") from exc
    if response.status_code in (401, 403):
        raise TextPermissionError(
            f"当前 Key 无文本模型权限（HTTP {response.status_code}），"
            "请改用 Agent 模式或在平台开通文本模型"
        )
    if multimodal and response.status_code in (400, 422):
        raise MultimodalUnsupportedError(
            "当前模型未接受图片，请选择多模态模型，或使用 Agent 批量看图制卡"
        )
    if response.status_code != 200:
        raise RewriteError(f"文本改写服务返回 HTTP {response.status_code}，请检查模型和额度")
    try:
        return str(response.json()["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise RewriteError("文本改写响应缺少内容") from exc


def _with_supplement(messages: list[dict], supplement: dict | None) -> list[dict]:
    if supplement:
        messages.append({"role": "user", "content": (
            "External feedback is unverified advice, never evidence of an error. "
            + json.dumps({"external_feedback": supplement.get("feedback", "")}, ensure_ascii=False)
        )})
    return messages


def normalize_dialogue_payload(data: dict, question: str) -> dict:
    """题干和自然英文是 API 问答的唯一文本源。"""
    answer = data.get("natural_english")
    if not isinstance(answer, str):
        return {}
    answer = " ".join(strip_all_tags(answer)[0].split())
    asked = " ".join(strip_all_tags(question)[0].split())
    if not answer or not asked:
        return {}
    return {"natural_english": answer, "podcast_text": f"A: {asked}\nB: {answer}",
            "podcast_script": f"A: [curious] {asked}\nB: [relaxed] {answer}"}


def generate_complete_bundle(settings: dict, question: str, english_attempt: str,
                             cancel: threading.Event | None = None,
                             supplement: dict | None = None,
                             chinese_intent: str = "") -> dict:
    from . import study

    intent = chinese_intent or (supplement or {}).get("intent", "")
    messages = _with_supplement(build_messages(question, english_attempt, intent), supplement)
    messages[0]["content"] = messages[0]["content"].replace(
        'Schema: {"natural_english": str}.',
        'Exactly two top-level keys: {"natural_english":"It helps me unwind.",'
        '"study_material":{"complete_chinese":"这让我放松。","sentences":[{"zh":"这让我放松。",'
        '"en":"It helps me unwind.","explanation":"It 指前面提到的活动。",'
        '"usage":"help 加人和动词原形。","key_chunk":"helps me unwind"}],'
        '"coach_summary":{"headline":"已经说出了活动带来的感受，再练一下动词形式就更自然了。",'
        '"strengths":["给出了原因"],"focus_points":["练习第三人称单数"]}}}.',
    ) + (
        "\nInside study_material, supply exactly one row per sentence of natural_english, "
        "copying each complete sentence including punctuation. "
        "Put all Chinese explanation and feedback inside study_material. " + study.MATERIAL_GUIDANCE
    )
    content = _chat(settings, messages, cancel)
    try:
        data = _extract_json(content)
    except RewriteError as exc:
        raise BundleFormatError("合并生成没有返回有效 JSON") from exc
    texts = normalize_dialogue_payload(data, question)
    errors = validate_texts(texts)
    if errors:
        raise BundleFormatError("合并生成的音频文本校验失败")
    try:
        material = study.validate_material(
            data.get("study_material"), {**texts, "original_answer": english_attempt},
            require_chunks=True,
        )
    except study.MaterialError as exc:
        logger.info("合并生成的逐句材料校验失败：%s", exc)
        # 保留已经通过校验的三份文本，材料可单独补齐。
        material = None
    return {**texts, "study_material": material}


def generate_texts(
    settings: dict,
    question: str,
    answer: str,
    cancel: threading.Event | None = None,
    supplement: dict | None = None,
) -> tuple[dict, int]:
    """一次 JSON Mode 请求生成三份文本；结构失败带错误清单修复重试一次。"""
    messages = _with_supplement(
        build_messages(question, answer, (supplement or {}).get("intent", "")), supplement
    )
    repairs = 0
    for attempt in range(MAX_REPAIRS + 1):
        content = _chat(settings, messages, cancel)
        data = normalize_dialogue_payload(_extract_json(content), question)
        errors = validate_texts(data)
        if not errors:
            return {field: data[field].strip() for field in REQUIRED_FIELDS}, repairs
        if attempt >= MAX_REPAIRS:
            break
        repairs += 1
        messages = messages + [
            {"role": "assistant", "content": content},
            {"role": "user", "content": _REPAIR_INSTRUCTION.format(errors="\n".join(errors))},
        ]
    raise RewriteError("改写结果校验未通过（已重试一次）:\n" + "\n".join(errors))


def build_agent_prompt(topic_id: str, item_id: str, question: str, answer: str) -> str:
    """Agent 模式的一键任务指令：含题目、原始回答、目标条目与固定完成命令，绝不含 Key。"""
    return f"""请为我的英语学习播客完成一次「回答改写 + 音频生成」任务。

## 规范
先读取仓库根目录的 skills/ielts-audio/SKILL.md 并严格遵守其中的数据契约与标签政策。

## 题目
{(question or '').strip()}

## 我的原始回答（中文/英文/混合，忠实改写，不要虚构事实）
{(answer or '').strip()}

## 目标条目（已在网页端创建）
--topic-id {topic_id}
--item-id {item_id}

## 完成方式
在仓库根目录把三份文本和逐句材料写成同一个 JSON 文件（UTF-8）：
{{
  "natural_english": "干净、可背诵的地道英文回答（第一人称口语，无任何方括号标签）",
  "podcast_text": "A:/B: 对话格式（A=提问者，B=基于我的回答作答），无标签",
  "podcast_script": "与 podcast_text 同一句话的 TTS 表演稿，使用规范所允许的标签",
  "study_material": {{
    "complete_chinese": "回答的完整中文原意",
    "sentences": [{{"zh": "本句中文", "en": "B 回答英文原句", "explanation": "句子组织说明",
      "usage": "词法或搭配说明", "key_chunk": "原句中连续的可复用英文词组"}}]
  }}
}}
然后执行（先校验，通过才会原子写入并合成音频）：
.venv/Scripts/python pipeline.py complete \\
  --topic-id {topic_id} --item-id {item_id} --result-json <你的json文件路径>
命令成功会输出播放页 URL 与 MP3 路径；校验失败请按错误提示修正 JSON 后重试。

从 podcast_text 的 B 回答按播报顺序逐句提取材料，
以原始回答为依据写完整中文原意和每句中文、explanation、usage；en 必须逐字复制 B 回答句子。
只有原始英文原话能证明语法或拼写错误时，才给该句增加 original_error，包含
quote（原始回答中的准确英文片段）、issue、correction；中文与开放表达不写个人错误。
参考表达要自然且可驾驭，不为高级词汇增加难度；一轮训练保持当前版本稳定。
可增加 outline 与 groups（各项为中文 label 和实际句子零基 indices）；Part 3 增加
一条相关英文 followup。缺口分类 gap_kind 可为 text_supported_error、explicit_gap、refinement，
其中个人错误必须有 original_error 证据；不从文字推断发音、分数或已验证的语义正确性。

## 硬性约束
- 三份文本的词句与我的回答保持一致，不得编造新经历
- podcast_text / natural_english 内不允许任何 [tag]
- 禁止笑声、呼吸、叹气和戏剧化标签；口头禅必须有实际语义功能
- 不要在文件、指令或回复中出现任何 API Key"""
