"""数据层：话题 / 条目的扫描与 CRUD。存储为纯文本文件 + meta.json。"""
import json
import re
import shutil
import threading
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR, EPISODES_DIR, TOPICS_DIR

LIB_LOCK = threading.RLock()

# 文本变化后对应轨道音频视为过期的字段
STALE_TEXT_FIELDS = (
    "natural_english",
    "fish_script",
    "monologue_text",
    "monologue_script",
    "podcast_text",
    "podcast_script",
)

TEXT_FIELDS = [
    "question",
    "chinese",
    "natural_english",
    "fish_script",
    "monologue_text",
    "monologue_script",
    "podcast_text",
    "podcast_script",
]
FIELD_FILES = {
    "question": "question.txt",
    "chinese": "chinese.txt",
    "natural_english": "natural_english.txt",
    "fish_script": "fish_script.txt",
    "monologue_text": "monologue_text.txt",
    "monologue_script": "monologue_script.txt",
    "podcast_text": "podcast_text.txt",
    "podcast_script": "podcast_script.txt",
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def slugify(text: str, fallback: str = "untitled", limit: int = 60) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"[^\w\u4e00-\u9fff\-]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    text = text[:limit].strip("-")
    return text or fallback


def _safe_id(value: str) -> bool:
    """目录 id 只允许字母数字、CJK、连字符、下划线，防止路径穿越。"""
    return bool(value) and not re.search(r"[^\w\u4e00-\u9fff\-]", value)


def _read_text(path: Path) -> str:
    if path.exists():
        try:
            return path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            return ""
    return ""


def _write_text(path: Path, content: str) -> None:
    path.write_text((content or "").strip() + "\n", encoding="utf-8")


# ---------------------------------------------------------------- topics

def topic_dir(topic_id: str) -> Path:
    if not _safe_id(topic_id):
        raise ValueError("非法的话题 id")
    return TOPICS_DIR / topic_id


def load_topic_name(tpath: Path) -> str:
    meta = tpath / "topic.json"
    if meta.exists():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            return data.get("name") or tpath.name
        except (json.JSONDecodeError, OSError):
            pass
    return tpath.name


def item_dirs(tpath: Path) -> list[Path]:
    items = tpath / "items"
    if not items.exists():
        return []
    return sorted([d for d in items.iterdir() if d.is_dir() and not d.name.startswith(".")])


def list_topics() -> list[dict]:
    with LIB_LOCK:
        result = []
        if not TOPICS_DIR.exists():
            return result
        for tpath in sorted(TOPICS_DIR.iterdir()):
            if not tpath.is_dir() or tpath.name.startswith("."):
                continue
            stats = {"total": 0, "empty": 0, "ready": 0, "generated": 0, "error": 0}
            total_sec = 0.0
            for d in item_dirs(tpath):
                stats["total"] += 1
                meta = load_meta(d)
                status = compute_status(d)  # 动态计算，兼容直接改文件
                if meta.get("error"):
                    stats["error"] += 1
                stats[status if status in ("empty", "ready", "generated") else "empty"] += 1
                total_sec += float(meta.get("duration_sec") or 0)
            result.append(
                {
                    "id": tpath.name,
                    "name": load_topic_name(tpath),
                    "stats": stats,
                    "total_sec": round(total_sec, 1),
                }
            )
        return result


def create_topic(name: str) -> dict:
    with LIB_LOCK:
        name = (name or "").strip() or "未命名话题"
        existing = {p.name for p in TOPICS_DIR.iterdir()} if TOPICS_DIR.exists() else set()
        order = 1
        while True:
            dirname = f"{order:02d}-{slugify(name)}"
            if dirname not in existing:
                break
            order += 1
        tpath = TOPICS_DIR / dirname
        tpath.mkdir(parents=True)
        (tpath / "items").mkdir()
        (tpath / "topic.json").write_text(
            json.dumps({"name": name, "created_at": now_iso()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {"id": dirname, "name": name}


def rename_topic(topic_id: str, name: str) -> None:
    with LIB_LOCK:
        tpath = topic_dir(topic_id)
        if not tpath.exists():
            raise FileNotFoundError("话题不存在")
        meta = {}
        meta_file = tpath / "topic.json"
        if meta_file.exists():
            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                meta = {}
        meta["name"] = (name or "").strip() or tpath.name
        meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_topic(topic_id: str) -> None:
    with LIB_LOCK:
        tpath = topic_dir(topic_id)
        if tpath.exists():
            shutil.rmtree(tpath)
        # 同步清理该话题已合成的剧集音频与清单，避免孤儿文件
        if EPISODES_DIR.exists():
            for p in EPISODES_DIR.iterdir():
                if p.is_file() and (
                    p.name.startswith(f"{topic_id}_") or p.name.startswith(f"{topic_id}.")
                ):
                    p.unlink(missing_ok=True)


def get_topic(topic_id: str) -> dict:
    with LIB_LOCK:
        tpath = topic_dir(topic_id)
        if not tpath.exists():
            raise FileNotFoundError("话题不存在")
        items = []
        for d in item_dirs(tpath):
            meta = load_meta(d)
            texts = read_item_texts(d)
            items.append(
                {
                    "id": d.name,
                    "title": item_title(texts, d.name),
                    "status": compute_status(d, texts),  # 动态计算，兼容直接改文件
                    "error": meta.get("error") or "",
                    "stale": bool(meta.get("stale")),
                    "duration_sec": meta.get("duration_sec"),
                    "updated_at": meta.get("updated_at") or "",
                }
            )
        return {"id": tpath.name, "name": load_topic_name(tpath), "items": items}


# ---------------------------------------------------------------- items

def item_path(topic_id: str, item_id: str) -> Path:
    ipath = topic_dir(topic_id) / "items" / item_id
    if not _safe_id(topic_id) or not _safe_id(item_id) or ipath.parent.name != "items":
        raise ValueError("非法路径")
    return ipath


def read_item_texts(d: Path) -> dict:
    return {field: _read_text(d / fname) for field, fname in FIELD_FILES.items()}


def item_title(texts: dict, fallback: str = "") -> str:
    q = (texts.get("question") or "").strip()
    if q:
        first_line = q.splitlines()[0].strip()
        return first_line or fallback
    zh = (texts.get("chinese") or "").strip()
    if zh:
        return zh.splitlines()[0].strip()[:40] or fallback
    en = (texts.get("natural_english") or "").strip()
    if en:
        return en.splitlines()[0].strip()[:40] or fallback
    return fallback


def get_track_source_text(texts: dict, track: str = "default") -> tuple[str, str]:
    """根据轨道选择合成文本及字段名。
    track: 'monologue' | 'podcast' | 'default'
    """
    if track == "monologue":
        for f in ("monologue_script", "monologue_text"):
            v = (texts.get(f) or "").strip()
            if v:
                return v, f
        for f in ("fish_script", "natural_english"):
            v = (texts.get(f) or "").strip()
            if v and not re.search(r"^\s*([ab])\s*[:：]", v, re.IGNORECASE | re.MULTILINE):
                return v, f
    elif track == "podcast":
        for f in ("podcast_script", "podcast_text"):
            v = (texts.get(f) or "").strip()
            if v:
                return v, f
        for f in ("fish_script", "natural_english"):
            v = (texts.get(f) or "").strip()
            if v and re.search(r"^\s*([ab])\s*[:：]", v, re.IGNORECASE | re.MULTILINE):
                return v, f

    for f in (
        "fish_script",
        "natural_english",
        "monologue_script",
        "monologue_text",
        "podcast_script",
        "podcast_text",
    ):
        v = (texts.get(f) or "").strip()
        if v:
            return v, f
    return "", ""


def tts_source_text(texts: dict) -> tuple[str, str]:
    """保持旧接口兼容。"""
    return get_track_source_text(texts, track="default")


def load_meta(d: Path) -> dict:
    meta_file = d / "meta.json"
    if meta_file.exists():
        try:
            return json.loads(meta_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_meta(d: Path, meta: dict) -> None:
    meta_file = d / "meta.json"
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def read_voices() -> list:
    """读取 data/voices.json 音色预设；缺失或损坏时返回空列表。"""
    voices_file = DATA_DIR / "voices.json"
    if voices_file.exists():
        try:
            data = json.loads(voices_file.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return []


def resolve_audio_file(d: Path, track: str = "default") -> Path | None:
    """按轨道优先级选出条目下可用的音频文件（存在且非空），没有则 None。

    track: 'monologue' → 独白版（缺则回退旧版 audio.mp3）
           'podcast'   → 播客版（缺则回退旧版 audio.mp3）
           其他/default → audio.mp3 → 独白 → 播客
    """
    if track == "monologue":
        candidates = ("audio_monologue.mp3", "audio.mp3")
    elif track == "podcast":
        candidates = ("audio_podcast.mp3", "audio.mp3")
    else:
        candidates = ("audio.mp3", "audio_monologue.mp3", "audio_podcast.mp3")
    for name in candidates:
        p = d / name
        try:
            if p.exists() and p.stat().st_size > 0:
                return p
        except OSError:
            continue
    return None


def compute_status(d: Path, texts: dict | None = None) -> str:
    if resolve_audio_file(d, "default") is not None:
        return "generated"
    texts = texts if texts is not None else read_item_texts(d)
    src, _ = tts_source_text(texts)
    return "ready" if src else "empty"


def _next_item_dir(tpath: Path, seed_text: str) -> Path:
    existing = {d.name for d in item_dirs(tpath)}
    max_order = 0
    for name in existing:
        m = re.match(r"(\d+)-", name)
        if m:
            max_order = max(max_order, int(m.group(1)))
    order = max_order + 1
    while True:
        dirname = f"{order:03d}-{slugify(seed_text, fallback='item')}"
        if dirname not in existing:
            return tpath / "items" / dirname
        order += 1


def create_item(topic_id: str, fields: dict) -> dict:
    with LIB_LOCK:
        tpath = topic_dir(topic_id)
        if not tpath.exists():
            raise FileNotFoundError("话题不存在")
        texts = {f: (fields.get(f) or "").strip() for f in TEXT_FIELDS}
        seed = texts["question"] or texts["chinese"] or "item"
        d = _next_item_dir(tpath, seed)
        d.mkdir(parents=True)
        for field, fname in FIELD_FILES.items():
            _write_text(d / fname, texts[field])
        meta = {
            "status": compute_status(d, texts),
            "error": "",
            "duration_sec": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "generated_at": None,
        }
        save_meta(d, meta)
        return {"id": d.name}


def update_item_texts(topic_id: str, item_id: str, fields: dict) -> dict:
    with LIB_LOCK:
        d = item_path(topic_id, item_id)
        if not d.exists():
            raise FileNotFoundError("条目不存在")
        texts = read_item_texts(d)
        texts_before = dict(texts)
        for field in TEXT_FIELDS:
            if field in fields:
                texts[field] = (fields.get(field) or "").strip()
        for field, fname in FIELD_FILES.items():
            _write_text(d / fname, texts[field])
        meta = load_meta(d)
        source_changed = any(texts[f] != texts_before[f] for f in STALE_TEXT_FIELDS)
        if source_changed:
            # 文本变了：时间轴/对齐缓存立即失效（指纹校验之外的双保险，修审计 A2）
            for p in d.glob("timeline_*.json"):
                p.unlink(missing_ok=True)
            for p in d.glob("alignment_*.json"):
                p.unlink(missing_ok=True)
        # 只有轨道源文本真的变化时，旧音频才视为过期
        if meta.get("status") == "generated":
            if source_changed:
                meta["stale"] = True
        meta["status"] = compute_status(d, texts)
        meta["updated_at"] = now_iso()
        if meta["status"] != "generated":
            meta["stale"] = False
        save_meta(d, meta)
        return {"id": d.name, "status": meta["status"]}


def update_item_meta(topic_id: str, item_id: str, **updates) -> None:
    with LIB_LOCK:
        d = item_path(topic_id, item_id)
        meta = load_meta(d)
        meta.update(updates)
        meta["status"] = compute_status(d)
        save_meta(d, meta)


def delete_item(topic_id: str, item_id: str) -> None:
    with LIB_LOCK:
        d = item_path(topic_id, item_id)
        if d.exists():
            shutil.rmtree(d)


def get_item_full(topic_id: str, item_id: str) -> dict:
    with LIB_LOCK:
        d = item_path(topic_id, item_id)
        if not d.exists():
            raise FileNotFoundError("条目不存在")
        texts = read_item_texts(d)
        meta = load_meta(d)
        mono = d / "audio_monologue.mp3"
        pod = d / "audio_podcast.mp3"
        has_mono = mono.exists() and mono.stat().st_size > 0
        has_pod = pod.exists() and pod.stat().st_size > 0
        has_legacy = (d / "audio.mp3").exists() and (d / "audio.mp3").stat().st_size > 0
        return {
            "topic_id": topic_id,
            "id": d.name,
            "title": item_title(texts, d.name),
            **texts,
            "status": compute_status(d, texts),  # 动态计算，兼容直接改文件
            "error": meta.get("error") or "",
            "stale": bool(meta.get("stale")),
            "duration_sec": meta.get("duration_sec"),
            "duration_sec_monologue": meta.get("duration_sec_monologue"),
            "duration_sec_podcast": meta.get("duration_sec_podcast"),
            "updated_at": meta.get("updated_at") or "",
            "has_audio": has_mono or has_pod or has_legacy,
            "has_audio_monologue": has_mono or (has_legacy and not meta.get("dialogue")),
            "has_audio_podcast": has_pod or (has_legacy and meta.get("dialogue")),
            "tts_mode": meta.get("tts_mode") or "",
            "qa_monologue": meta.get("qa_monologue"),
            "qa_podcast": meta.get("qa_podcast"),
            "qa_default": meta.get("qa_default"),
        }


def generated_items(topic_id: str, track: str = "default") -> list[dict]:
    """按顺序返回已生成音频的条目（播放器 / 合成用）。
    track: 'default' | 'monologue' | 'podcast'
    """
    with LIB_LOCK:
        tpath = topic_dir(topic_id)
        result = []
        for d in item_dirs(tpath):
            audio_target = resolve_audio_file(d, track)
            if audio_target:
                meta = load_meta(d)
                texts = read_item_texts(d)
                dur = meta.get(f"duration_sec_{track}") or meta.get("duration_sec")
                result.append(
                    {
                        "id": d.name,
                        "title": item_title(texts, d.name),
                        "audio": audio_target,
                        "duration_sec": dur,
                        "question": texts["question"],
                        "chinese": texts["chinese"],
                        "natural_english": texts["natural_english"],
                        "fish_script": texts["fish_script"],
                        "monologue_text": texts.get("monologue_text", ""),
                        "monologue_script": texts.get("monologue_script", ""),
                        "podcast_text": texts.get("podcast_text", ""),
                        "podcast_script": texts.get("podcast_script", ""),
                    }
                )
        return result
