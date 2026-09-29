"""逐句学习材料：播报文本绑定、原话证据与安全音频定位。"""

import hashlib
import json
import re
import threading

from . import library, rewrite, timeline
from .config import atomic_write_text, load_settings

VERSION = 1
MATERIAL_FILE = "study_material.json"
_ACTIVE: set[tuple[str, str]] = set()
_ACTIVE_LOCK = threading.Lock()

SYSTEM_PROMPT = """You prepare faithful Chinese-English study materials for an IELTS learner.
Return one JSON object only with complete_chinese and sentences. Each sentence has zh, en,
explanation, usage and optionally original_error {quote, issue, correction}. Copy every supplied
English answer sentence exactly and in order into en. Explain useful grammar and collocations in
Chinese. The complete Chinese meaning and each zh must preserve the learner's original meaning;
do not invent experiences. Only report an original_error when an exact English quote from the raw
answer proves a real grammatical or spelling error. Never treat a valid alternative wording as an
error. Chinese input is not evidence of an English error. Do not infer pronunciation or scores."""


class MaterialError(ValueError):
    """材料不完整或无法与实际回答核对。"""


def _answer_sentences(text: str) -> list[str]:
    from .tts import parse_dialogue

    dialogue = parse_dialogue(text or "") or []
    answer = []
    for speaker, body in dialogue:
        if speaker.lower() == "b":
            answer.extend(re.split(r"(?<=[.!?])\s+", body.strip()))
    return [part.strip() for part in answer if part.strip()]


def source_fingerprint(texts: dict) -> str:
    values = [texts.get(key) or "" for key in (
        "original_answer", "natural_english", "podcast_text", "podcast_script"
    )]
    raw = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _spoken_words(text: str) -> list[str]:
    return re.findall(r"[a-z]+(?:['’][a-z]+)?", re.sub(r"\[[^\]]*\]", "", text).lower())


def expected_sentences(texts: dict) -> list[str]:
    visible = _answer_sentences(texts.get("podcast_text") or "")
    if not visible:
        raise MaterialError("缺少可核对的 B 回答台词")
    script = texts.get("podcast_script") or ""
    if script and _spoken_words(" ".join(visible)) != _spoken_words(
        " ".join(_answer_sentences(script))
    ):
        raise MaterialError("可见回答与实际播报稿词序不同，需先复核音频文本")
    return visible


def validate_material(material: dict, texts: dict) -> dict:
    if not isinstance(material, dict):
        raise MaterialError("逐句材料必须是 JSON 对象")
    original = (texts.get("original_answer") or "").strip()
    if not original:
        raise MaterialError("缺少原始回答，请先补齐再准备学习材料")
    expected = expected_sentences(texts)
    chinese = material.get("complete_chinese")
    rows = material.get("sentences")
    if not isinstance(chinese, str) or not chinese.strip():
        raise MaterialError("缺少完整中文原意")
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise MaterialError(f"逐句材料须按播报顺序提供 {len(expected)} 句")
    cleaned = []
    for index, (row, en) in enumerate(zip(rows, expected, strict=True), 1):
        if not isinstance(row, dict):
            raise MaterialError(f"第 {index} 句格式错误")
        for field in ("zh", "en", "explanation", "usage"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise MaterialError(f"第 {index} 句缺少 {field}")
        if row["en"].strip() != en:
            raise MaterialError(f"第 {index} 句英文与实际 B 回答台词不一致")
        entry = {field: row[field].strip() for field in (
            "zh", "en", "explanation", "usage"
        )}
        error = row.get("original_error")
        if error is not None:
            if not isinstance(error, dict) or any(
                not isinstance(error.get(key), str) or not error[key].strip()
                for key in ("quote", "issue", "correction")
            ):
                raise MaterialError(f"第 {index} 句个人错误缺少原话、问题或改法")
            quote = error["quote"].strip()
            if quote not in original or len(_spoken_words(quote)) < 2:
                raise MaterialError(f"第 {index} 句个人错误没有可核对的原始英文证据")
            entry["original_error"] = {
                key: error[key].strip() for key in ("quote", "issue", "correction")
            }
        cleaned.append(entry)
    return {
        "version": VERSION,
        "source_fingerprint": source_fingerprint(texts),
        "complete_chinese": chinese.strip(),
        "sentences": cleaned,
    }


def save_material(topic_id: str, item_id: str, material: dict) -> dict:
    with library.LIB_LOCK:
        path = library.item_path(topic_id, item_id)
        if not path.exists():
            raise FileNotFoundError("条目不存在")
        if library.resolve_audio_file(path, "podcast") is None:
            raise MaterialError("播客音频尚未完成")
        result = validate_material(material, library.read_item_texts(path))
        atomic_write_text(path / MATERIAL_FILE, json.dumps(result, ensure_ascii=False, indent=2))
        meta = library.load_meta(path)
        meta["study_status"] = "ready"
        meta["study_error"] = ""
        library.save_meta(path, meta)
        library.invalidate_item_cache(path)
        return result


def set_status(topic_id: str, item_id: str, status: str, error: str = "") -> None:
    if status not in ("preparing", "failed"):
        raise ValueError("非法材料状态")
    library.update_item_meta(topic_id, item_id, study_status=status, study_error=error[:300])


def generate_material(topic_id: str, item_id: str) -> dict:
    """独立的一次文本模型调用；调用失败只改变材料状态。"""
    full = library.get_item_full(topic_id, item_id)
    if not full.get("original_answer"):
        raise MaterialError("缺少原始回答，请先补齐")
    if not full.get("has_audio_podcast"):
        raise MaterialError("播客音频尚未完成")
    sentences = expected_sentences(full)
    fingerprint = source_fingerprint(full)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({
            "question": full.get("question"),
            "original_answer": full["original_answer"],
            "exact_spoken_sentences": sentences,
        }, ensure_ascii=False)},
    ]
    settings = load_settings()
    if settings.get("dry_run"):
        raise MaterialError("dry-run 不调用文本模型；可用 Agent 材料命令准备")
    content = rewrite._chat(settings, messages, None)
    result = rewrite._extract_json(content)
    if fingerprint != source_fingerprint(library.get_item_full(topic_id, item_id)):
        raise MaterialError("准备期间回答已变化，请重新准备材料")
    return save_material(topic_id, item_id, result)


def prepare_async(topic_id: str, item_id: str) -> bool:
    """返回是否新启动；重复点击不产生额外计费调用。"""
    key = (topic_id, item_id)
    with _ACTIVE_LOCK:
        if key in _ACTIVE:
            return False
        _ACTIVE.add(key)
    try:
        set_status(topic_id, item_id, "preparing")
    except Exception:
        with _ACTIVE_LOCK:
            _ACTIVE.discard(key)
        raise

    def run() -> None:
        try:
            generate_material(topic_id, item_id)
        except Exception as exc:
            set_status(topic_id, item_id, "failed", str(exc))
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE.discard(key)

    threading.Thread(target=run, name="study-material", daemon=True).start()
    return True


def get_material(topic_id: str, item_id: str) -> dict:
    path = library.item_path(topic_id, item_id)
    if not path.exists():
        raise FileNotFoundError("条目不存在")
    texts = library.read_item_texts(path)
    meta = library.load_meta(path)
    result: dict = {"status": "needs_input", "reason": "请补齐逐句学习材料"}
    if not texts.get("original_answer"):
        result["reason"] = "缺少原始回答；请补齐后准备材料，旧音频仍可播放"
        return result
    if library.resolve_audio_file(path, "podcast") is None:
        result["reason"] = "播客音频尚未完成"
        return result
    file = path / MATERIAL_FILE
    if file.exists():
        try:
            stored = json.loads(file.read_text(encoding="utf-8"))
            if stored.get("source_fingerprint") != source_fingerprint(texts):
                return {"status": "changed", "reason": "回答正文或原始回答已变化，请复核材料"}
            validated = validate_material(stored, texts)
            return {"status": "ready", "material": validated}
        except (OSError, ValueError, TypeError) as exc:
            return {"status": "failed", "reason": f"材料需修复：{str(exc)[:160]}"}
    if meta.get("study_status") == "preparing":
        with _ACTIVE_LOCK:
            if (topic_id, item_id) not in _ACTIVE:
                return {"status": "failed", "reason": "准备任务中断，请重试"}
        return {"status": "preparing", "reason": "逐句材料正在准备"}
    if meta.get("study_status") == "failed":
        return {"status": "failed", "reason": meta.get("study_error") or "材料准备失败"}
    return result


def sentence_audio(topic_id: str, item_id: str, index: int) -> dict:
    found = get_material(topic_id, item_id)
    if found["status"] != "ready":
        raise MaterialError("逐句材料尚未就绪")
    rows = found["material"]["sentences"]
    if index < 0 or index >= len(rows):
        raise MaterialError("句子序号越界")
    path = library.item_path(topic_id, item_id)
    audio = library.resolve_audio_file(path, "podcast")
    if not audio:
        raise MaterialError("音频不可用")
    response = {"scope": "full_answer", "start": 0, "end": None,
                "reason": "这句没有可靠的独立时间位置，将播放完整音频"}
    located = timeline.get_or_create_timeline(topic_id, item_id, "podcast")
    if located.get("mode") not in ("sse",):
        return response
    target = rows[index]["en"]
    matches = [line for line in located.get("lines", [])
               if line.get("speaker", "").upper() == "B"
               and target == re.sub(r"\[[^\]]*\]", "", line.get("text") or "").strip()]
    if len(matches) == 1 and (matches[0].get("end") or 0) > (matches[0].get("start") or 0):
        return {"scope": "sentence", "start": matches[0]["start"],
                "end": matches[0]["end"], "reason": "经文本和音频指纹核对的时间轴"}
    return response
