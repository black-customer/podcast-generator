"""桌面三步练习、私有录音、闪电复习和口语病历。"""

import hashlib
import json
import os
import re
import threading
import uuid
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory

from . import alignment, audio, library, oral_review, speech_bridge, study, study_progress, timeline
from .config import TMP_DIR, atomic_write_text, load_settings
from .speech_worker import tokens

MAX_RECORDING_BYTES = 30 * 1024 * 1024
_LOCK = threading.RLock()
_FORMATS = {**study_progress.MEDIA_TYPES, "audio/wav": ".wav", "audio/mpeg": ".mp3"}


def _check_upload(data: bytes, media_type: str, duration: float, limit: int) -> str:
    kind = media_type.split(";", 1)[0].strip().lower()
    if kind not in _FORMATS or not 0 < len(data) <= MAX_RECORDING_BYTES:
        raise ValueError("录音格式或文件大小不支持")
    if not 0 < duration <= limit:
        raise ValueError(f"录音时长须在 {limit} 秒内")
    return kind


def _folder(topic_id: str, item_id: str) -> Path:
    return study_progress._folder(topic_id, item_id) / "arcade"


def _read(folder: Path) -> list[dict]:
    index = folder / "recordings.json"
    return json.loads(index.read_text(encoding="utf-8")) if index.is_file() else []


def _public(entry: dict, topic_id: str, item_id: str) -> dict:
    return {key: entry[key] for key in ("id", "stage", "duration_sec", "created_at", "analysis",
                                      "analysis_error", "sentence_index")} | {
        "url": f"/api/topics/{topic_id}/items/{item_id}/arcade/recordings/{entry['id']}"
    }


def _save(folder: Path, entry: dict, data: bytes) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (entry["id"] + _FORMATS[entry["media_type"]])
    staged = target.with_suffix(".tmp~")
    try:
        staged.write_bytes(data)
        os.replace(staged, target)
        index = _read(folder)
        atomic_write_text(folder / "recordings.json", json.dumps(
            [*index, entry], ensure_ascii=False, indent=2
        ))
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        staged.unlink(missing_ok=True)


def _blind_folder(token: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", token or ""):
        raise ValueError("盲答录音标识无效")
    return TMP_DIR / f"arcade-blind-{token}"


def transcribe_blind(data: bytes, media_type: str, duration: float,
                     language: str | None = None) -> dict:
    kind = _check_upload(data, media_type, duration, 180)
    token = uuid.uuid4().hex
    work = _blind_folder(token)
    work.mkdir(parents=True)
    recording = work / ("recording" + _FORMATS[kind])
    try:
        recording.write_bytes(data)
        analysis = speech_bridge.request(load_settings(), "transcribe_and_analyze",
                                         path=recording, language=language)
        entry = {"id": token, "stage": "blind", "analysis": analysis, "analysis_error": "",
                 "sentence_index": None, "duration_sec": round(duration, 2), "media_type": kind,
                 "created_at": library.now_iso()}
        atomic_write_text(work / "recording.json", json.dumps(entry, ensure_ascii=False))
    except Exception:
        recording.unlink(missing_ok=True)
        if not any(work.iterdir()):
            work.rmdir()
        raise
    return {"blind_token": token, "transcript": analysis.get("transcript", ""),
            "analysis": analysis}


def check_blind(token: str) -> None:
    if not (_blind_folder(token) / "recording.json").is_file():
        raise ValueError("盲答录音已使用或过期，请重新录制")


def attach_blind(token: str, topic_id: str, item_id: str) -> None:
    with _LOCK:
        check_blind(token)
        work = _blind_folder(token)
        meta = work / "recording.json"
        entry = json.loads(meta.read_text(encoding="utf-8"))
        recording = work / ("recording" + _FORMATS[entry["media_type"]])
        _save(_folder(topic_id, item_id), entry, recording.read_bytes())
        meta.unlink()
        recording.unlink(missing_ok=True)
        work.rmdir()


def _answer_spans(lines: list[dict]) -> list[dict]:
    return [line for line in lines if line.get("speaker") == "B" and
            line.get("end", 0) > line.get("start", 0)]


def _sentence_spans(rows: list[dict], locations: dict) -> list[dict]:
    scope = {"scope": "full_answer", "start": 0, "end": None}
    lines = _answer_spans(locations["lines"])
    if locations["mode"] != "sse":
        return [scope] * len(rows)
    candidates = [(line, tokens(re.sub(r"\[[^\]]*\]", "", line["text"]))) for line in lines]
    exact = len(candidates) == len(rows) and all(
        words == tokens(row["en"]) for (_, words), row in zip(candidates, rows, strict=True)
    )
    if exact:
        return [{"scope": "sentence", "start": line["start"], "end": line["end"]}
                for line, _ in candidates]
    # 旧 SSE 有时将整段回答作一行，使用实际词时间戳定位连续句子。
    aligned = [word for word in locations["words"] if word.get("end", 0) > word.get("start", 0)
               and any(line["start"] - 0.03 <= word["start"] < line["end"] for line in lines)]
    flat = [(token, word) for word in aligned for token in tokens(word.get("text", ""))]
    heard = [token for token, _ in flat]
    cursor, spans = 0, []
    for row in rows:
        goal = tokens(row["en"])
        found = next((i for i in range(cursor, len(heard) - len(goal) + 1)
                      if goal and heard[i:i + len(goal)] == goal), None)
        if found is None:
            spans.append(scope)
            continue
        cursor = found + len(goal)
        spans.append({"scope": "sentence", "start": flat[found][1]["start"],
                      "end": flat[cursor - 1][1]["end"]})
    return spans


def view(topic_id: str, item_id: str) -> dict:
    with _LOCK, library.LIB_LOCK:
        full = library.get_item_full(topic_id, item_id)
        found = study.get_material(topic_id, item_id)
        material = found.get("material", {})
        rows = material.get("sentences", [])
        fingerprint = material.get("source_fingerprint")
        path = library.item_path(topic_id, item_id)
        mp3 = library.resolve_audio_file(path, "podcast")
        audio_url = f"/api/topics/{topic_id}/items/{item_id}/audio/podcast"
        if mp3:
            audio_url += f"?v={mp3.stat().st_mtime_ns}"
        locations = timeline.get_or_create_timeline(topic_id, item_id) if mp3 else {
            "lines": [], "words": [], "mode": "estimated"
        }
        voice = None
        if mp3:
            src, _ = library.get_track_source_text(full, "podcast")
            doc = alignment.load_alignment(path / "alignment_podcast.json", src, mp3) or {}
            voices = {row.get("voice") for row in doc.get("segments", [])
                      if row.get("speaker") == "b"}
            if len(voices) == 1:
                voice = next(iter(voices))
        recs = _read(_folder(topic_id, item_id))
        baseline = next((e for e in reversed(recs) if e["stage"] == "blind"), None)
        final = next((e for e in reversed(recs) if e["stage"] == "final" and
                      e.get("fingerprint") == fingerprint), None)
        return {"question": full["question"], "original_answer": study._effective_original(full),
                "status": found["status"], "reason": found.get("reason", ""),
                "source_fingerprint": fingerprint, "audio_url": audio_url if mp3 else "",
                "dry_run": bool(library.load_meta(path).get("dry_run")), "voice": voice,
                "alignment": locations, "answer_spans": _answer_spans(locations["lines"]),
                "sentences": [{**row, "audio": span} for row, span in zip(
                    rows, _sentence_spans(rows, locations), strict=True
                )], "blind": _public(baseline, topic_id, item_id) if baseline else None,
                "final": _public(final, topic_id, item_id) if final else None}


def record(topic_id: str, item_id: str, stage: str, data: bytes, media_type: str,
           duration: float, index: int | None = None, upload_key: str | None = None,
           fingerprint: str | None = None) -> dict:
    if stage not in {"blind", "chunk", "final"}:
        raise ValueError("录音阶段无效")
    limit = {"blind": 180, "chunk": 30, "final": 60}[stage]
    kind = _check_upload(data, media_type, duration, limit)
    if upload_key and not re.fullmatch(r"[\w-]{1,100}", upload_key):
        raise ValueError("录音上传标识无效")
    folder = _folder(topic_id, item_id)
    found = study.get_material(topic_id, item_id).get("material", {})
    revision = found.get("source_fingerprint")
    if stage != "blind" and (not revision or fingerprint and revision != fingerprint):
        raise ValueError("学习材料已更新，请刷新后再录制")
    rows = found.get("sentences", [])
    if stage == "chunk" and (index is None or not 0 <= index < len(rows)):
        raise ValueError("句子序号无效")
    digest = hashlib.sha256(data).hexdigest()

    def previous() -> dict | None:
        existing = next((e for e in _read(folder) if upload_key and
                         e.get("upload_key") == upload_key), None)
        if existing and (existing["digest"], existing["stage"], existing["sentence_index"],
                         existing.get("fingerprint")) != (digest, stage, index, revision):
            raise ValueError("上传标识与这次录音不一致")
        return existing

    with _LOCK:
        if saved := previous():
            return _public(saved, topic_id, item_id)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    analysis, error = None, ""
    with TemporaryDirectory(prefix="arcade-analysis-", dir=TMP_DIR) as directory:
        path = Path(directory) / ("take" + _FORMATS[kind])
        path.write_bytes(data)
        settings = load_settings()
        try:
            if stage == "chunk":
                row = rows[index]
                analysis = speech_bridge.request(settings, "check_utterance", path=path,
                                                 text=row["en"], chunks=[row.get("key_chunk", "")])
            else:
                chunks = [row["key_chunk"] for row in rows if row.get("key_chunk")]
                analysis = speech_bridge.request(settings, "transcribe_and_analyze", path=path,
                                                 language="en" if stage == "final" else None,
                                                 chunks=chunks)
        except speech_bridge.SpeechError as exc:
            error = str(exc)
    entry = {"id": uuid.uuid4().hex, "stage": stage, "duration_sec": round(duration, 2),
             "analysis": analysis, "analysis_error": error, "media_type": kind,
             "created_at": library.now_iso(), "sentence_index": index, "fingerprint": revision,
             "upload_key": upload_key, "digest": digest}
    with _LOCK, library.LIB_LOCK:
        if not library.item_path(topic_id, item_id).exists():
            raise FileNotFoundError("条目不存在")
        if saved := previous():
            return _public(saved, topic_id, item_id)
        _save(folder, entry, data)
    return _public(entry, topic_id, item_id)


def recording(topic_id: str, item_id: str, recording_id: str) -> tuple[Path, str]:
    folder = _folder(topic_id, item_id)
    entry = next((e for e in _read(folder) if e["id"] == recording_id), None)
    if entry:
        path = folder / (entry["id"] + _FORMATS[entry["media_type"]])
        if path.is_file():
            return path, entry["media_type"]
    raise FileNotFoundError("录音不存在")


def export(topic_id: str, item_id: str) -> Path:
    current = view(topic_id, item_id)
    if not current["blind"] or not current["final"]:
        raise ValueError("需要盲答和脱稿两段录音才能导出")
    if (current["dry_run"] or current["alignment"]["mode"] == "estimated" or
            not current["answer_spans"]):
        raise ValueError("需要有实测定位的示范回答才能导出")
    source = library.resolve_audio_file(library.item_path(topic_id, item_id), "podcast")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    result = TMP_DIR / f"arcade-evolution-{uuid.uuid4().hex}.mp3"
    try:
        with TemporaryDirectory(prefix="arcade-export-", dir=TMP_DIR) as directory:
            work = Path(directory)
            takes = [(recording(topic_id, item_id, current[key]["id"])[0], [])
                     for key in ("blind", "final")]
            takes.extend((source, ["-ss", str(line["start"]), "-t",
                                   str(line["end"] - line["start"])])
                         for line in current["answer_spans"])
            entries = []
            for index, (path, limits) in enumerate(takes):
                clip = work / f"part-{index}.mp3"
                audio._run(["ffmpeg", "-y", "-i", str(path), *limits, "-vn", "-ar", "44100",
                            "-ac", "1", "-b:a", "128k", str(clip)])
                entries.append({"path": clip, "gap_before": 0.35 if 0 < index <= 2 else 0})
            audio.concat_mp3(entries, result)
    except Exception:
        result.unlink(missing_ok=True)
        raise
    return result


def blitz() -> dict:
    cards = oral_review.blitz_cards()
    sources = {}
    result = []
    for card in cards:
        key = (card["topic_id"], card["item_id"])
        if key not in sources:
            sources[key] = view(*key)
        source = sources[key]
        index = card["sentence_index"]
        if (source["source_fingerprint"] != card["source_fingerprint"] or
                index >= len(source["sentences"])):
            continue
        result.append({
            **oral_review._preview(card), "source_fingerprint": card["source_fingerprint"],
            "audio_url": source["audio_url"], **source["sentences"][index],
        })
    return {"due_count": len(result), "cards": result}


def _category(error: dict) -> str:
    if error.get("category") in study.ERROR_LABELS:
        return error["category"]
    return next((key for key, pattern in {
        "plural": r"单复数|复数|可数|plural", "tense": r"过去式|时态|tense",
        "subject_verb_agreement": r"主谓|agreement", "article": r"冠词|article",
        "preposition": r"介词|preposition", "word_order": r"语序|word order",
        "conjunction": r"连词|conjunction", "collocation": r"搭配|collocation",
    }.items() if re.search(pattern, error["issue"], re.I)), "other")


def error_board() -> dict:
    counts: Counter = Counter()
    for material_path in library.TOPICS_DIR.glob(f"*/items/*/{study.MATERIAL_FILE}"):
        tid, iid = material_path.parent.parent.parent.name, material_path.parent.name
        try:
            found = study.get_material(tid, iid)
        except (OSError, ValueError):
            continue
        seen = set()
        for row in found.get("material", {}).get("sentences", []):
            if error := row.get("original_error"):
                key = (_category(error), error["quote"].casefold(), error["correction"].casefold())
                seen.add(key)
        counts.update(category for category, *_ in seen)
    with oral_review._LOCK:
        attempts = oral_review._load()["attempts"]
    today = oral_review._today().isoformat()
    chunks = list(dict.fromkeys(entry["key_chunk"] for entry in reversed(attempts)
                               if entry["date"] == today and entry.get("key_chunk")))[:12]
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    top = [{"category": key, "label": study.ERROR_LABELS[key], "count": count}
           for key, count in ranked]
    prompt = ["用英语和我做 10 分钟口语陪练。每次问一个简短的雅思口语问题，让我先说完。"]
    if chunks:
        prompt.append("引导我自然用到这些语块：" + "、".join(chunks) + "。")
    if top:
        prompt.append("重点留意：" + "、".join(entry["label"] for entry in top[:2]) + "。")
    prompt.append("每轮只指出一处有原话证据的错误，给出自然改法，再让我说一遍。")
    return {"top": top, "today_chunks": chunks, "prompt": "\n".join(prompt)}
