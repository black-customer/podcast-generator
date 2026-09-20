"""StepFun 文本改写（JSON Mode）与 Agent 任务指令：一次请求产出三份文本并校验。

数据契约（R03）：
- natural_english：干净、可背诵的地道英文回答（无任何表演标签）。
- podcast_text：用户可见的完整问答文本（A:/B: 对话，无表演标签）。
- podcast_script：隐藏的 TTS 表演稿（A:/B: 对话，只允许白名单标签）。
原始回答永远由 original_answer.txt 保存，改写失败也不得覆盖或清除。
"""
from __future__ import annotations

import json
import re
import threading

import httpx

from .audioqa import strip_all_tags, strip_disallowed_tags
from .config import real_stepfun_api_key

TEXT_API_URL = "https://api.stepfun.com/v1/chat/completions"
DEFAULT_TEXT_MODEL = "step-3.7-flash"
MAX_REPAIRS = 1
# 表演稿与可见文本的词义一致性下限（内容词 jaccard）。同义改写通常 >0.5。
SEMANTIC_OVERLAP_MIN = 0.35
SYSTEM_SCHEMA = (
    "You rewrite an IELTS learner's raw answer into three fields and reply with ONE JSON "
    "object only (no markdown fence, no commentary). Schema:\n"
    '{"natural_english": str, "podcast_text": str, "podcast_script": str}\n'
    "- natural_english: the clean, natural, first-person spoken English answer, "
    "directly recitable, no stage directions, no brackets.\n"
    "- podcast_text: a friendly two-speaker dialogue the user can read: lines starting "
    "with 'A:' (the interviewer asking) and 'B:' (the user answering, based strictly on "
    "their raw answer). No brackets.\n"
    "- podcast_script: the SAME dialogue as podcast_text for a TTS engine, keeping the "
    "same words and meaning, optionally with sparse performance tags from this "
    "allowlist only: [pause] [short pause] [long pause] [break] [chuckle] [sigh] "
    "[softly] [uncertain] [emphasis] [curious] [relaxed] [thoughtful].\n"
    "Keep the user's real experiences, opinions and level of detail; never invent facts."
)

_REPAIR_INSTRUCTION = (
    "Your previous JSON was rejected:\n{errors}\n"
    "Return the corrected complete JSON object now, same schema, no commentary."
)


class RewriteError(RuntimeError):
    pass


class TextPermissionError(RewriteError):
    """Key 无文本模型权限或未配置——必须显式提示用户改用 Agent 模式。"""


REQUIRED_FIELDS = ("natural_english", "podcast_text", "podcast_script")
_DIALOGUE_RE = re.compile(r"^\s*[ab]\s*[:：]", re.IGNORECASE | re.MULTILINE)
_TAG_TEXT_RE = re.compile(r"\[([^\[\]]*)\]")
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


def build_messages(question: str, answer: str) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_SCHEMA},
        {
            "role": "user",
            "content": (
                f"Question:\n{(question or '').strip()}\n\n"
                f"The learner's raw answer (Chinese, English or mixed):\n"
                f"{(answer or '').strip()}"
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
        if not (texts.get(field) or "").strip():
            errors.append(f"缺少必填字段或为空: {field}")
    if errors:
        return errors

    for field in ("natural_english", "podcast_text"):
        found = _TAG_TEXT_RE.findall(texts[field])
        if found:
            errors.append(f"可见文本 {field} 不允许任何表演标签，需输出干净英文: {found[:3]}")
    for field in ("podcast_text", "podcast_script"):
        if not _DIALOGUE_RE.search(texts[field]):
            errors.append(f"{field} 必须是 A:/B: 对话格式（A=提问者，B=回答者）")

    _cleaned_script, removed = strip_disallowed_tags(texts["podcast_script"])
    if removed:
        errors.append(
            f"podcast_script 含白名单外标签 {removed[:3]}，只允许表演白名单内的标签"
        )

    visible = strip_all_tags(texts["podcast_text"])[0]
    if _semantic_overlap(visible, _cleaned_script) < SEMANTIC_OVERLAP_MIN:
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


def _chat(settings: dict, messages: list[dict], cancel: threading.Event | None) -> str:
    key = real_stepfun_api_key(settings)
    if not key:
        raise TextPermissionError(
            "未配置 StepFun Key，无法使用 API 模式改写；请改用 Agent 模式（不消耗文本 API）"
        )
    if cancel is not None and cancel.is_set():
        raise RewriteError("已取消")
    model = str(settings.get("stepfun_text_model") or DEFAULT_TEXT_MODEL)
    try:
        response = httpx.post(
            TEXT_API_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model,
                "messages": messages,
                "response_format": {"type": "json_object"},
                "temperature": 0.6,
            },
            timeout=120,
        )
    except httpx.HTTPError as exc:
        raise RewriteError(f"StepFun 文本 API 网络错误: {exc}") from exc
    if response.status_code in (401, 403):
        raise TextPermissionError(
            f"当前 StepFun Key 无文本模型权限（HTTP {response.status_code}），"
            "请改用 Agent 模式或在平台开通文本模型"
        )
    if response.status_code != 200:
        raise RewriteError(
            f"StepFun 文本 API {response.status_code}: {(response.text or '')[:200]}"
        )
    try:
        choice = response.json()["choices"][0]
    except (KeyError, IndexError, ValueError) as exc:
        raise RewriteError("StepFun 文本 API 响应缺少 choices") from exc
    return str(choice.get("message", {}).get("content") or "")


def generate_texts(
    settings: dict,
    question: str,
    answer: str,
    cancel: threading.Event | None = None,
) -> tuple[dict, int]:
    """一次 JSON Mode 请求生成三份文本；结构失败带错误清单修复重试一次。"""
    messages = build_messages(question, answer)
    repairs = 0
    for attempt in range(MAX_REPAIRS + 1):
        content = _chat(settings, messages, cancel)
        data = _extract_json(content)
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
在仓库根目录把三份文本写成 JSON 文件（UTF-8）：
{{
  "natural_english": "干净、可背诵的地道英文回答（第一人称口语，无任何方括号标签）",
  "podcast_text": "A:/B: 对话格式（A=提问者，B=基于我的回答作答），无标签",
  "podcast_script": "与 podcast_text 同一句话的 TTS 表演稿，
只允许白名单标签如 [pause] [break] [chuckle]"
}}
然后执行（先校验，通过才会原子写入并合成音频）：
.venv/Scripts/python pipeline.py complete \\
  --topic-id {topic_id} --item-id {item_id} --result-json <你的json文件路径>
命令成功会输出播放页 URL 与 MP3 路径；校验失败请按错误提示修正 JSON 后重试。

## 硬性约束
- 三份文本的词句与我的回答保持一致，不得编造新经历
- podcast_text / natural_english 内不允许任何 [tag]
- 不要在文件、指令或回复中出现任何 API Key"""
