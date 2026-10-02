"""Q05 私有作答草稿与收听位置；不写公开语料，不覆盖损坏的个人记录。"""
from __future__ import annotations

import hashlib
import json
import math
import threading
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import assemble, audio, bank, library
from .config import DATA_DIR, atomic_write_text

PRIVATE_DIR = DATA_DIR / "study_private"
LOCK = threading.RLock()
router = APIRouter(prefix="/api")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _load(name: str) -> dict:
    path = PRIVATE_DIR / f"{name}.v1.json"
    if not path.exists():
        return {"version": 1, "records": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("version") != 1 or not isinstance(doc.get("records"), dict):
            raise ValueError()
        if any(not isinstance(r, dict) for r in doc["records"].values()):
            raise ValueError()
        for record in doc["records"].values():
            if name == "answer_drafts":
                if (not isinstance(record.get("revision"), int)
                        or record["revision"] < 0 or not isinstance(record.get("answer"), str)
                        or (record.get("answer") and not isinstance(
                            record.get("question_text"), str))
                        or record.get("mode", "agent") not in ("agent", "api")):
                    raise ValueError()
            elif (record.get("kind") not in ("item", "episode")
                  or not all(isinstance(record.get(f), str) for f in
                             ("topic_id", "item_id", "track", "audio_fingerprint", "saved_at"))
                  or not isinstance(record.get("position"), (float, int))
                  or not isinstance(record.get("completed"), bool)
                  or not math.isfinite(record["position"]) or record["position"] < 0):
                raise ValueError()
        return doc
    except (OSError, ValueError, AttributeError, TypeError) as exc:
        raise HTTPException(
            503, "个人记录暂时无法读取；原文件仍保留，请备份并检查后重试。"
        ) from exc


def _save(name: str, doc: dict) -> None:
    try:
        atomic_write_text(PRIVATE_DIR / f"{name}.v1.json",
                          json.dumps(doc, ensure_ascii=False, indent=2))
    except OSError as exc:
        raise HTTPException(503, "保存失败；原记录仍保留，请检查磁盘权限或空间后重试。") from exc


def _id(value: str) -> str:
    if not value or not library._safe_id(value):
        raise HTTPException(422, "无效的条目或题目编号")
    return value


def _question(qid: str) -> dict | None:
    try:
        return bank.find_question(bank.load_bank(), qid)
    except FileNotFoundError:
        return None


def _draft(qid: str, record: dict) -> dict:
    question = _question(qid)
    return {"question_id": qid, "revision": 0, "answer": "", "mode": "agent", **record,
            "question_missing": question is None,
            "question_changed": bool(record.get("question_text") and question
                                     and record["question_text"] != question["text"])}


class DraftIn(BaseModel):
    question_text: str
    answer: str = Field(max_length=200000)
    mode: str = "agent"
    revision: int = Field(ge=0)


@router.get("/answer-drafts")
def drafts_list():
    with LOCK:
        return {"drafts": [_draft(qid, record) for qid, record in
                           _load("answer_drafts")["records"].items() if record.get("answer")]}


@router.get("/answer-drafts/{question_id}")
def draft_get(question_id: str):
    with LOCK:
        return _draft(_id(question_id), _load("answer_drafts")["records"].get(question_id, {}))


@router.put("/answer-drafts/{question_id}")
def draft_put(question_id: str, body: DraftIn):
    _id(question_id)
    if body.mode not in ("agent", "api"):
        raise HTTPException(422, "请选择 Agent 或 API 模式")
    with LOCK:
        doc = _load("answer_drafts")
        current = doc["records"].get(question_id, {})
        question = _question(question_id)
        if not question or question["text"] != body.question_text:
            raise HTTPException(409, "题目已变化或不存在；当前文字仍保留，请复制或查看原草稿。")
        if current.get("revision", 0) != body.revision:
            raise HTTPException(409, "另一页面已更新草稿；当前输入仍保留，请查看并选择恢复内容。")
        record = {"question_text": body.question_text, "answer": body.answer,
                  "mode": body.mode, "revision": body.revision + 1, "saved_at": _now()}
        doc["records"][question_id] = record
        _save("answer_drafts", doc)
        return _draft(question_id, record)


@router.delete("/answer-drafts/{question_id}")
def draft_delete(question_id: str, revision: int):
    with LOCK:
        doc = _load("answer_drafts")
        current = doc["records"].get(_id(question_id), {})
        if current.get("revision", 0) != revision:
            raise HTTPException(409, "草稿已更新，未清除新内容。")
        record = {"revision": revision + 1, "answer": "", "mode": "agent", "saved_at": _now()}
        doc["records"][question_id] = record
        _save("answer_drafts", doc)
        return _draft(question_id, record)


def _source(kind: str, topic_id: str, item_id: str, track: str) -> dict:
    _id(topic_id)
    if kind not in ("item", "episode") or track not in ("default", "monologue", "podcast"):
        raise HTTPException(422, "无效的音频来源或音轨")
    try:
        if kind == "item":
            _id(item_id)
            path = library.resolve_audio_file(library.item_path(topic_id, item_id), track)
            title = library.item_title(library.read_item_texts(
                library.item_path(topic_id, item_id)), item_id)
        else:
            path = assemble.episode_path(topic_id, track=track)
            title = library.load_topic_name(library.topic_dir(topic_id))
        if path is None or not path.is_file() or not path.stat().st_size:
            raise FileNotFoundError()
        actual = "monologue" if path.name.endswith("_monologue.mp3") else (
            "podcast" if path.name.endswith("_podcast.mp3") else track)
        if actual == "default" and kind == "item":
            actual = "podcast" if library.load_meta(path.parent).get("dialogue") else "monologue"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"kind": kind, "topic_id": topic_id, "item_id": item_id, "track": actual,
                "title": title, "audio_fingerprint": digest}
    except (OSError, ValueError) as exc:
        raise HTTPException(404, "音频不存在或无法读取；原收听记录仍保留。") from exc


def _key(source: dict) -> str:
    return json.dumps([source[k] for k in ("kind", "topic_id", "item_id", "track")],
                      ensure_ascii=False)


def _progress(source: dict, doc: dict) -> dict:
    saved = doc["records"].get(_key(source), {})
    changed = bool(saved and saved.get("audio_fingerprint") != source["audio_fingerprint"])
    return {**saved, **source, "position": 0 if changed or saved.get("completed")
            else saved.get("position", 0), "state": "audio_changed" if changed else "ready",
            "completed": False if changed else bool(saved.get("completed", False))}


@router.get("/listening-progress/latest")
def progress_latest():
    with LOCK, library.LIB_LOCK:
        doc = _load("listening_progress")
        records = sorted(doc["records"].values(), key=lambda r: r.get("saved_at", ""), reverse=True)
        for record in records:
            try:
                source = _source(record["kind"], record["topic_id"], record["item_id"],
                                 record["track"])
            except (HTTPException, KeyError):
                continue
            return _progress(source, doc)
        return {"latest": None}


@router.get("/listening-progress")
def progress_get(topic_id: str, item_id: str = "", track: str = "podcast", kind: str = "item"):
    with LOCK, library.LIB_LOCK:
        return _progress(_source(kind, topic_id, item_id, track), _load("listening_progress"))


class ProgressIn(BaseModel):
    kind: str = "item"
    topic_id: str
    item_id: str = ""
    track: str = "podcast"
    audio_fingerprint: str
    position: float = Field(ge=0)
    duration: float = Field(default=0, ge=0)
    completed: bool = False


@router.put("/listening-progress")
def progress_put(body: ProgressIn):
    if not math.isfinite(body.position) or not math.isfinite(body.duration):
        raise HTTPException(422, "播放时间无效")
    with LOCK, library.LIB_LOCK:
        source = _source(body.kind, body.topic_id, body.item_id, body.track)
        if body.audio_fingerprint != source["audio_fingerprint"]:
            raise HTTPException(409, "音频已变化；旧位置已保留，本次请从头播放。")
        doc = _load("listening_progress")
        # 实际时长由音频核对，客户端异常数值不能把恢复点写到音频之外。
        path = (assemble.episode_path(body.topic_id, track=source["track"])
                if body.kind == "episode" else library.resolve_audio_file(
                    library.item_path(body.topic_id, body.item_id), source["track"]))
        duration = audio.probe_duration(path)
        position = min(body.position, max(0, duration - 0.05)) if duration > 0 else 0
        doc["records"][_key(source)] = {**source, "position": position,
                                       "duration": duration, "completed": body.completed,
                                       "saved_at": _now()}
        _save("listening_progress", doc)
        return _progress(source, doc)
