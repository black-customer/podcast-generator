"""本机私有练习记录：草稿、复习事实与分版本录音。"""

import json
import os
import threading
import uuid
from pathlib import Path

from . import library
from .config import DATA_DIR, atomic_write_text

PRIVATE_DIR = DATA_DIR / "study_private"
STAGES = frozenset({"before", "dictation", "chinese", "recall", "summary"})
RECORDING_STAGES = frozenset({"before", "chinese", "recall"})
MEDIA_TYPES = {"audio/webm": ".webm", "audio/ogg": ".ogg", "audio/mp4": ".m4a"}
_LOCK = threading.RLock()


def _folder(topic_id: str, item_id: str) -> Path:
    item = library.item_path(topic_id, item_id)
    if not item.exists():
        raise FileNotFoundError("条目不存在")
    return PRIVATE_DIR / topic_id / item_id


def _default() -> dict:
    return {"version": 1, "stage": "before", "before_started": False, "sentence_index": 0,
            "draft": [], "facts": {}, "recordings": []}


def get_progress(topic_id: str, item_id: str) -> dict:
    file = _folder(topic_id, item_id) / "state.json"
    if not file.exists():
        return _default()
    try:
        stored = json.loads(file.read_text(encoding="utf-8"))
        if isinstance(stored, dict) and stored.get("version") == 1:
            return {**_default(), **stored}
    except (OSError, json.JSONDecodeError):
        pass
    raise ValueError("练习记录损坏，请先备份本机文件")


def _write(topic_id: str, item_id: str, state: dict) -> None:
    file = _folder(topic_id, item_id) / "state.json"
    atomic_write_text(file, json.dumps(state, ensure_ascii=False, indent=2))


def save_progress(topic_id: str, item_id: str, update: dict) -> dict:
    if not isinstance(update, dict):
        raise ValueError("练习进度格式错误")
    stage = update.get("stage")
    if stage is not None and stage not in STAGES:
        raise ValueError("非法学习阶段")
    if "before_started" in update and not isinstance(update["before_started"], bool):
        raise ValueError("学习入口状态错误")
    index = update.get("sentence_index")
    if index is not None and (not isinstance(index, int) or not 0 <= index < 10000):
        raise ValueError("句子序号错误")
    draft = update.get("draft")
    if draft is not None and (not isinstance(draft, list) or len(draft) > 200 or any(
        not isinstance(word, str) or len(word) > 100 for word in draft
    )):
        raise ValueError("草稿格式错误")
    facts = update.get("facts")
    if facts is not None and (not isinstance(facts, dict) or len(facts) > 10000):
        raise ValueError("复习记录格式错误")
    if facts is not None:
        for key, value in facts.items():
            if not str(key).isdigit() or int(key) >= 10000 or not isinstance(value, dict):
                raise ValueError("复习记录格式错误")
            if any(k not in {"hint_used", "wrong_attempts", "favorite", "passed",
                             "review_attempts"} for k in value):
                raise ValueError("复习记录字段错误")
            for field, entry in value.items():
                if field in {"hint_used", "favorite", "passed"} and not isinstance(entry, bool):
                    raise ValueError("复习记录布尔值错误")
                if field in {"wrong_attempts", "review_attempts"} and (
                    not isinstance(entry, int) or isinstance(entry, bool)
                    or not 0 <= entry <= 100000
                ):
                    raise ValueError("复习记录次数错误")
    with _LOCK:
        state = get_progress(topic_id, item_id)
        for key in ("stage", "before_started", "sentence_index", "draft"):
            if key in update:
                state[key] = update[key]
        if facts is not None:
            for key, value in facts.items():
                state["facts"][str(key)] = {**state["facts"].get(str(key), {}), **value}
        _write(topic_id, item_id, state)
        return state


def save_recording(
    topic_id: str, item_id: str, stage: str, data: bytes, duration_sec: float, media_type: str
) -> dict:
    if stage not in RECORDING_STAGES:
        raise ValueError("非法录音阶段")
    if not isinstance(duration_sec, (int, float)) or not 0 < duration_sec <= 7200:
        raise ValueError("录音时长错误")
    if not data or len(data) > 30 * 1024 * 1024:
        raise ValueError("录音大小超出范围")
    media_type = media_type.split(";", 1)[0].strip().lower()
    if media_type not in MEDIA_TYPES:
        raise ValueError("录音格式不支持")
    with _LOCK:
        state = get_progress(topic_id, item_id)
        folder = _folder(topic_id, item_id)
        folder.mkdir(parents=True, exist_ok=True)
        rec_id = uuid.uuid4().hex
        name = rec_id + MEDIA_TYPES[media_type]
        path = folder / name
        temp = folder / (name + ".tmp~")
        try:
            temp.write_bytes(data)
            os.replace(temp, path)
            question = library.read_item_texts(library.item_path(topic_id, item_id))["question"]
            entry = {"id": rec_id, "question": question, "stage": stage,
                     "created_at": library.now_iso(),
                     "duration_sec": round(float(duration_sec), 2), "media_type": media_type,
                     "filename": name}
            state["recordings"].append(entry)
            _write(topic_id, item_id, state)
        except Exception:
            temp.unlink(missing_ok=True)
            path.unlink(missing_ok=True)
            raise
        return entry


def read_recording(topic_id: str, item_id: str, rec_id: str) -> tuple[bytes, str]:
    state = get_progress(topic_id, item_id)
    entry = next((r for r in state["recordings"] if r["id"] == rec_id), None)
    if entry is None:
        raise FileNotFoundError("录音不存在")
    path = _folder(topic_id, item_id) / entry["filename"]
    return path.read_bytes(), entry["media_type"]


def delete_recording(topic_id: str, item_id: str, rec_id: str) -> None:
    with _LOCK:
        state = get_progress(topic_id, item_id)
        entry = next((r for r in state["recordings"] if r["id"] == rec_id), None)
        if entry is None:
            raise FileNotFoundError("录音不存在")
        state["recordings"] = [r for r in state["recordings"] if r["id"] != rec_id]
        _write(topic_id, item_id, state)
        (_folder(topic_id, item_id) / entry["filename"]).unlink(missing_ok=True)


def review_items() -> list[dict]:
    from . import study

    rows = []
    if not PRIVATE_DIR.exists():
        return rows
    for state_file in PRIVATE_DIR.glob("*/*/state.json"):
        topic_id, item_id = state_file.parent.parent.name, state_file.parent.name
        try:
            state = get_progress(topic_id, item_id)
            found = study.get_material(topic_id, item_id)
            if found["status"] != "ready":
                continue
            full = library.get_item_full(topic_id, item_id)
        except (FileNotFoundError, ValueError):
            continue
        sentences = found["material"]["sentences"]
        for key, facts in state["facts"].items():
            if not str(key).isdigit():
                continue  # 手改坏的事实键：跳过而不是让复习库 500
            index = int(key)
            if index >= len(sentences) or not (
                facts.get("wrong_attempts", 0) > 0 or facts.get("hint_used")
                or facts.get("favorite")
            ):
                continue
            rows.append({"topic_id": topic_id, "item_id": item_id,
                         "sentence_index": index, "zh": sentences[index]["zh"],
                         "source": full["title"], "facts": facts})
    rows.sort(key=lambda r: (r["topic_id"], r["item_id"], r["sentence_index"]))
    return rows
