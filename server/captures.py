
"""私有素材、语块卡、原片定位和本地示范音频。"""

import base64
import binascii
import hashlib
import json
import os
import re
import shutil
import threading
import time as clock
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit
from uuid import uuid4

from . import alignment, library, speech_worker, tts
from .config import DATA_DIR, atomic_write_text, is_dry_run, load_settings

CAPTURES_DIR = DATA_DIR / "captures"
CAPTURES_LOCK = threading.RLock()
_AUDIO_LOCK = threading.Lock()
IMAGE_MAX = 10 * 1024 ** 2
BACKUP_MAX = 150 * 1024 ** 2
ID = re.compile(r"cap_[0-9a-f]{16}")
CARD_ID = re.compile(r"card_[0-9a-f]{16}")
WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)?|[0-9]+")
CJK = re.compile(r"[\u3400-\u9fff]")
UNSUPPORTED_DIAGNOSIS = re.compile(
    r"发音|口音|重音|语调|评分|pronunciation|intonation|accent|score", re.I,
)
CARD_FIELDS = (
    "target_chunk", "chunk_in_sentence", "chunk_zh", "en", "zh", "trigger_context",
    "explanation", "usage_boundary", "feynman_hook", "transfer_prompt_zh",
    "transfer_example_en",
)
GOALS = ("activate_chunk", "comprehend_input", "fix_error", "fill_gap")
STATUSES = ("inbox", "active", "archived")
IMAGE_TYPES = {
    "image/jpeg": ("jpg", b"\xff\xd8\xff"),
    "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
    "image/webp": ("webp", b"RIFF"),
}


def _clean(value: object, limit: int, label: str, *, required: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError(f"{label} 格式不正确或长度超过限制")
    return value.strip()


def _identity(prefix: str, seed: str) -> str:
    return f"{prefix}_{hashlib.sha256(seed.encode()).hexdigest()[:16]}"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, data: dict) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def capture_path(capture_id: str) -> Path:
    if not ID.fullmatch(capture_id) or not library._safe_id(capture_id):
        raise ValueError("素材编号无效")
    path = CAPTURES_DIR / capture_id
    if not (path / "meta.json").is_file():
        raise FileNotFoundError("素材不存在")
    return path


def make_cloze(en: str, chunk_in_sentence: str) -> str:
    matches = list(WORD.finditer(en))
    target = speech_worker.tokens(chunk_in_sentence)
    if not target:
        raise ValueError("语块须出现在示范原句中")
    for index in range(len(matches) - len(target) + 1):
        words = matches[index:index + len(target)]
        if speech_worker.tokens(" ".join(word[0] for word in words)) != target:
            continue
        masked = WORD.sub(lambda m: "[" + m[0][0] + "_" * max(1, len(m[0]) - 1) + "]",
                          en[words[0].start():words[-1].end()])
        return en[:words[0].start()] + masked + en[words[-1].end():]
    raise ValueError("语块须出现在示范原句中")


def validate_card_payload(raw_card: dict, *, original_english: str = "") -> dict:
    if not isinstance(raw_card, dict):
        raise ValueError("语块卡须为 JSON 对象")
    row = {field: _clean(raw_card.get(field), 1500, field, required=True)
           for field in CARD_FIELDS}
    goal = raw_card.get("goal_type", "activate_chunk")
    status = raw_card.get("status", "inbox")
    if goal not in GOALS or status not in STATUSES:
        raise ValueError("学习目标或卡片状态无效")
    for field in ("en", "transfer_example_en"):
        if CJK.search(row[field]) or re.search(r"[\[\]\r\n]", row[field]):
            raise ValueError("英文示范须为无表演标注的单行英文")
    if not speech_worker.matched_chunks(row["en"], [row["chunk_in_sentence"]]):
        raise ValueError("示范原句必须包含完整、连续的目标语块")
    example = row["transfer_example_en"]
    if example.casefold() == row["en"].casefold():
        raise ValueError("迁移示范需要使用新情境")
    row.update(goal_type=goal, status=status)
    row["disambiguator"] = _clean(raw_card.get("disambiguator", ""), 1500, "排除提示")
    if hint := _clean(raw_card.get("contrast_hint", ""), 1500, "对比提示"):
        row["contrast_hint"] = hint
    row["cloze_prompt"] = make_cloze(row["en"], row["chunk_in_sentence"])
    error = raw_card.get("original_error")
    row["original_error"] = None
    if error is not None:
        if not isinstance(error, dict):
            raise ValueError("纠错需要原话、问题和改法")
        parts = {key: _clean(error.get(key), 1500, key, required=True)
                 for key in ("quote", "issue", "correction")}
        if (parts["quote"] not in original_english
                or len(re.findall(r"[A-Za-z]+", parts["quote"])) < 2
                or UNSUPPORTED_DIAGNOSIS.search(parts["issue"])):
            raise ValueError("纠错必须有可核对的英文原话证据")
        row["original_error"] = parts
    if goal == "fix_error" and not row["original_error"]:
        raise ValueError("纠错卡必须有英文原话证据")
    fingerprint_data = {k: v for k, v in row.items() if k != "status"}
    row["content_fingerprint"] = hashlib.sha256(
        json.dumps(fingerprint_data, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    return row


def _image(value: str) -> tuple[str, bytes]:
    if not isinstance(value, str) or len(value) > (IMAGE_MAX * 4 // 3 + 64):
        raise ValueError("单张截图须小于等于 10 MiB")
    prefix, _, encoded = value.partition(",")
    mime = prefix.removeprefix("data:").removesuffix(";base64")
    if mime not in IMAGE_TYPES or prefix != f"data:{mime};base64":
        raise ValueError("截图只支持 JPEG、PNG 或 WebP")
    extension, signature = IMAGE_TYPES[mime]
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("截图编码无效") from exc
    if (len(data) > IMAGE_MAX or not data.startswith(signature)
            or (extension == "webp" and data[8:12] != b"WEBP")):
        raise ValueError("图片内容或大小不符合要求")
    return extension, data


def _url(raw: str, *, bilibili: bool = False, seconds: float = 0) -> str:
    if not raw:
        return ""
    parsed = urlsplit(raw)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None):
        raise ValueError("素材链接须为有效的 HTTP(S) 链接")
    if not bilibili:
        return raw
    if (parsed.hostname not in {"www.bilibili.com", "bilibili.com", "m.bilibili.com"}
            or parsed.port is not None or not re.fullmatch(
                r"/(?:video/(?:BV[a-zA-Z0-9]{10}|av[0-9]+)|"
                r"bangumi/play/(?:ep|ss)[1-9][0-9]*)/?",
                parsed.path,
            )):
        raise ValueError("素材需要有效的 B 站视频、分集或剧季链接")
    params = {}
    page = parse_qs(parsed.query).get("p", [""])[0]
    if re.fullmatch(r"[1-9][0-9]{0,5}", page):
        params["p"] = page
    params["t"] = str(int(seconds))
    return urlunsplit(("https", "www.bilibili.com", parsed.path.rstrip("/"),
                       urlencode(params), ""))


def _ingest(source: dict, images: list[tuple[str, bytes]], title: str, *,
            kind: str, provider: str, external: str = "") -> tuple[dict, bool]:
    capture_id = _identity("cap", external) if external else f"cap_{uuid4().hex[:16]}"
    path = CAPTURES_DIR / capture_id
    if (path / "meta.json").is_file():
        return _json(path / "meta.json"), False
    time = library.now_iso()
    meta = {"version": 1, "id": capture_id, "source_type": kind, "provider": provider,
            "title": title, "external_id": external, "extract_state": "pending",
            "extract_error": "", "extract_mode": "", "created_at": time, "updated_at": time}
    CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".capture-", dir=CAPTURES_DIR) as work:
        staged = Path(work)
        filenames = []
        if images:
            (staged / "assets").mkdir()
        for index, (extension, data) in enumerate(images):
            name = f"frame{('-' + str(index + 1)) if index else ''}.{extension}"
            (staged / "assets" / name).write_bytes(data)
            filenames.append(name)
        _write(staged / "source.json", {**source, "assets": filenames})
        _write(staged / "meta.json", meta)
        for attempt in range(5):
            try:
                os.replace(staged, path)
                break
            except OSError as exc:
                if (path / "meta.json").is_file() and external:
                    return _json(path / "meta.json"), False
                if not isinstance(exc, PermissionError) or attempt == 4:
                    raise
                clock.sleep(0.025 * (attempt + 1))
    return meta, True


def ingest_snippet(text: str = "", images: list[str] | None = None, title: str = "",
                   source_url: str = "", note: str = "") -> dict:
    text = _clean(text, 100_000, "摘录")
    title = _clean(title, 1000, "标题") or (text[:65] if text else "随手截图")
    if images is not None and (not isinstance(images, list) or len(images) > 3):
        raise ValueError("单次最多添加三张图片")
    decoded = [_image(value) for value in images or []]
    if not text and not decoded:
        raise ValueError("请填写摘录或添加截图")
    source = {"text": text, "note": _clean(note, 100_000, "备注"),
              "source_url": _url(_clean(source_url, 4000, "素材链接"))}
    with CAPTURES_LOCK:
        meta, _ = _ingest(source, decoded, title, kind="snippet", provider="manual")
        return meta


def ingest_scenes(notes: list[dict]) -> dict:
    if not isinstance(notes, list) or len(notes) > 5000:
        raise ValueError("备份最多包含 5000 条场景")
    validated = []
    total = 0
    for row in notes:
        if not isinstance(row, dict) or not isinstance(row.get("source"), dict):
            raise ValueError("场景来源格式无效")
        note_id = _clean(row.get("id"), 200, "场景编号", required=True)
        time = row.get("time")
        if (type(time) not in (int, float) or not 0 <= time <= 31 * 24 * 3600):
            raise ValueError("原片时间戳无效")
        url = _url(_clean(row["source"].get("url", ""), 4000, "原片链接"),
                   bilibili=True, seconds=time)
        images = [_image(row["imageUrl"])] if row.get("imageUrl") else []
        total += sum(len(data) for _, data in images)
        if total > BACKUP_MAX:
            raise ValueError("备份超过 150 MiB")
        series = _clean(row.get("seriesTitle", ""), 1000, "剧集标题")
        episode = _clean(row.get("epTitle", ""), 1000, "分集标题")
        title = " · ".join(filter(None, (series, episode, f"{int(time)//60}:{int(time)%60:02d}")))
        source = {"note_id": note_id, "series_id": _clean(row.get("seriesId", ""), 300, "剧集"),
                  "series_title": series, "episode_title": episode, "time": time,
                  "userNote": _clean(row.get("userNote", ""), 100_000, "场景备注"),
                  "source_url": url}
        validated.append((source, images, title, f"cnc:{note_id}"))
    ids, imported, updated = [], 0, 0
    with CAPTURES_LOCK:
        for source, images, title, external in validated:
            meta, created = _ingest(source, images, title, kind="scene",
                                    provider="bilibili_cnc", external=external)
            ids.append(meta["id"])
            imported += created
            if not created and meta["extract_state"] == "pending" and source["userNote"]:
                path = capture_path(meta["id"]) / "source.json"
                stored = _json(path)
                if stored.get("userNote") != source["userNote"]:
                    stored["userNote"] = source["userNote"]
                    _write(path, stored)
                    updated += 1
        if ids:
            _update_index()
    return {"imported": imported, "updated": updated, "duplicates": len(ids) - imported - updated,
            "capture_ids": ids}


def _update_index() -> None:
    by_external = {row["external_id"]: row["id"] for row in list_captures() if row["external_id"]}
    _write(CAPTURES_DIR / "index.json", {"version": 1, "by_external_id": by_external})


def list_captures(source_type: str | None = None) -> list[dict]:
    result = []
    with CAPTURES_LOCK:
        for path in CAPTURES_DIR.glob("cap_*/meta.json"):
            if ID.fullmatch(path.parent.name):
                meta = _json(path)
                if not source_type or meta["source_type"] == source_type:
                    result.append(meta)
    return sorted(result, key=lambda row: (row["created_at"], row["id"]), reverse=True)


def get_capture(capture_id: str) -> dict:
    with CAPTURES_LOCK:
        path = capture_path(capture_id)
        return {**_json(path / "meta.json"), "source": _json(path / "source.json")}


def asset_file(capture_id: str, name: str) -> tuple[Path, str]:
    found = get_capture(capture_id)
    if name not in found["source"]["assets"] or not re.fullmatch(
        r"frame(?:-[2-3])?\.(?:jpg|png|webp)", name
    ):
        raise FileNotFoundError("素材图片不存在")
    path = capture_path(capture_id) / "assets" / name
    mime = next(key for key, pair in IMAGE_TYPES.items() if pair[0] == path.suffix[1:])
    return path, mime


def _rows(path: Path) -> list[dict]:
    return _json(path / "cards.json")["cards"] if (path / "cards.json").is_file() else []


def list_cards(status: str | None = None, source_type: str | None = None,
               capture_id: str | None = None, q: str = "") -> list[dict]:
    with CAPTURES_LOCK:
        parents = [get_capture(capture_id)] if capture_id else [
            get_capture(meta["id"]) for meta in list_captures(source_type)
        ]
        result = []
        for capture in parents:
            for row in _rows(capture_path(capture["id"])):
                if status and row["status"] != status:
                    continue
                if q.casefold() not in " ".join((row["en"], row["zh"],
                                                  capture["title"])).casefold():
                    continue
                result.append({**row, "capture_id": capture["id"], "capture": capture})
    return result


def get_card(card_id: str) -> dict:
    if not CARD_ID.fullmatch(card_id):
        raise ValueError("卡片编号无效")
    for row in list_cards():
        if row["id"] == card_id:
            return row
    raise FileNotFoundError("语块卡不存在")


def set_extract_state(capture_id: str, state: str, mode: str, error: str = "") -> None:
    with CAPTURES_LOCK:
        path = capture_path(capture_id)
        meta = _json(path / "meta.json")
        meta.update(extract_state=state, extract_mode=mode, extract_error=error[:300],
                    updated_at=library.now_iso())
        _write(path / "meta.json", meta)


def prepare_cards(capture_id: str, raw: list[dict]) -> list[dict]:
    capture = get_capture(capture_id)
    if not isinstance(raw, list) or not 1 <= len(raw) <= 2:
        raise ValueError("每条素材须生成一至两张语块卡")
    result = []
    for row in raw:
        clean = validate_card_payload(
            row, original_english=capture["source"].get("original_english", ""),
        )
        identity = _identity("card", capture_id + "\n" + clean["chunk_in_sentence"].casefold())
        clean.update(id=identity, status="inbox", updated_at=library.now_iso())
        result.append(clean)
    if len({row["id"] for row in result}) != len(result):
        raise ValueError("同一素材的目标语块必须各不相同")
    return result


def save_cards(capture_id: str, rows: list[dict], mode: str) -> list[dict]:
    with CAPTURES_LOCK:
        path = capture_path(capture_id)
        existing = _rows(path)
        seen = {row["id"] for row in existing}
        result = existing + [row for row in rows if row["id"] not in seen]
        _write(path / "cards.json", {"version": 1, "cards": result})
        set_extract_state(capture_id, "ready", mode)
        return result


def update_card(card_id: str, patch: dict) -> dict:
    with CAPTURES_LOCK:
        current = get_card(card_id)
        capture = current["capture"]
        row = validate_card_payload(
            current | patch, original_english=capture["source"].get("original_english", ""),
        )
        row.update(id=card_id, updated_at=library.now_iso())
        path = capture_path(capture["id"])
        rows = [row if candidate["id"] == card_id else candidate for candidate in _rows(path)]
        _write(path / "cards.json", {"version": 1, "cards": rows})
        return {**row, "capture_id": capture["id"], "capture": capture}


def approve_card(card_id: str, *, goal_type: str | None = None) -> dict:
    patch = {"status": "active"}
    if goal_type is not None:
        patch["goal_type"] = goal_type
    return update_card(card_id, patch)


def archive_card(card_id: str) -> dict:
    return update_card(card_id, {"status": "archived"})


def delete_capture(capture_id: str) -> None:
    with CAPTURES_LOCK:
        path = capture_path(capture_id).resolve()
        if path.parent != CAPTURES_DIR.resolve() or path.name != capture_id:
            raise ValueError("素材目录无效")
        shutil.rmtree(path)
        _update_index()


def audio_file(card_id: str) -> Path:
    row = get_card(card_id)
    root = capture_path(row["capture_id"]) / "audio"
    path = root / f"{card_id}.mp3"
    doc = alignment.load_alignment(root / f"{card_id}.alignment.json", row["en"], path)
    if not doc or doc.get("content_fingerprint") != row["content_fingerprint"]:
        raise FileNotFoundError("示范音频尚未就绪")
    return path


def synthesize_card_audio(capture_id: str, card_id: str, *, force: bool = False) -> dict:
    with _AUDIO_LOCK:
        return _synthesize_card_audio(capture_id, card_id, force=force)


def _synthesize_card_audio(capture_id: str, card_id: str, *, force: bool) -> dict:
    row = get_card(card_id)
    if row["capture_id"] != capture_id or row["status"] != "active":
        raise ValueError("请先确认入库")
    if not force:
        try:
            existing = audio_file(card_id)
        except FileNotFoundError:
            pass
        else:
            return {"audio_url": f"/api/cards/{card_id}/audio", "size": existing.stat().st_size}
    settings = load_settings()
    path = capture_path(capture_id) / "audio"
    path.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix=".synth-", dir=path) as directory:
        staged = Path(directory) / "sample.mp3"
        result, _, spoken, words = tts._synthesize_with_qa(
            row["en"], staged, settings, force_monologue=True,
        )
        doc = alignment.build_alignment_doc(
            mode="sse" if words else "measured", source_text=spoken, audio_path=staged,
            segments=result[4], track="monologue", words=words,
        )
        doc.update(content_fingerprint=row["content_fingerprint"], dry_run=is_dry_run(settings))
        with CAPTURES_LOCK:
            now = get_card(card_id)
            if (now["status"] != "active"
                    or now["content_fingerprint"] != row["content_fingerprint"]):
                raise ValueError("合成期间卡片已更新，请重新播放")
            staged.replace(path / f"{card_id}.mp3")
            alignment.save_alignment(doc, path / f"{card_id}.alignment.json")
    return {"audio_url": f"/api/cards/{card_id}/audio", "dry_run": doc["dry_run"]}
