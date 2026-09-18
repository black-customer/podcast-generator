"""把一个话题下所有已生成音频合成为一集播客。"""
import json

from . import audio, library
from .config import EPISODES_DIR, atomic_write_text, load_settings


def episode_path(topic_id: str, track: str = "default"):
    if track == "monologue":
        return EPISODES_DIR / f"{topic_id}_monologue.mp3"
    elif track == "podcast":
        return EPISODES_DIR / f"{topic_id}_podcast.mp3"
    return EPISODES_DIR / f"{topic_id}.mp3"


def episode_manifest_path(topic_id: str, track: str = "default"):
    if track == "monologue":
        return EPISODES_DIR / f"{topic_id}_monologue.json"
    elif track == "podcast":
        return EPISODES_DIR / f"{topic_id}_podcast.json"
    return EPISODES_DIR / f"{topic_id}.json"


def assemble_episode(topic_id: str, track: str = "default") -> dict:
    topic = library.get_topic(topic_id)
    items = library.generated_items(topic_id, track=track)
    if not items:
        track_name = "独白" if track == "monologue" else ("播客" if track == "podcast" else "")
        raise RuntimeError(f"该话题下没有已生成{track_name}音频的条目")

    try:
        gap_ms = float(load_settings().get("episode_gap_ms") or 600)
    except (TypeError, ValueError):
        gap_ms = 600.0

    entries = []
    offsets = []
    cur = 0.0
    for i, it in enumerate(items):
        gap = gap_ms / 1000.0 if i else 0.0
        offsets.append(round(cur + gap, 2))
        cur += gap + float(it.get("duration_sec") or 0)
        entries.append({"path": it["audio"], "gap_before": gap})
    out = episode_path(topic_id, track=track)
    # 原子输出：先写临时文件再替换，读方永远看到完整旧版或完整新版
    tmp_out = out.with_name(out.name + ".assembling.mp3")
    try:
        audio.concat_mp3(entries, tmp_out)
        import os

        os.replace(tmp_out, out)
    finally:
        tmp_out.unlink(missing_ok=True)
    total = audio.probe_duration(out)

    manifest = {
        "topic_id": topic_id,
        "topic_name": topic["name"],
        "track": track,
        "file": out.name,
        "total_sec": round(total, 2),
        "item_count": len(items),
        "generated_at": library.now_iso(),
        "items": [
            {
                "id": it["id"],
                "title": it["title"],
                "duration_sec": it["duration_sec"],
                "offset_sec": offsets[i],
                "generated_at": it["generated_at"],
            }
            for i, it in enumerate(items)
        ],
    }
    atomic_write_text(
        episode_manifest_path(topic_id, track=track),
        json.dumps(manifest, ensure_ascii=False, indent=2),
    )
    return manifest


def load_manifest(topic_id: str, track: str = "default") -> dict | None:
    """精确轨道语义：请求 monologue/podcast 时绝不回退到 default 清单（审计 A19）。

    附带 stale 标记：条目重生成/增删后 manifest 即过期（修审计 A18 陈旧下载）。
    """
    f = episode_manifest_path(topic_id, track=track)
    if not f.exists():
        return None
    try:
        manifest = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(manifest, dict):
        return None
    manifest["stale"] = _is_stale(topic_id, manifest, track=track)
    return manifest


def _is_stale(topic_id: str, manifest: dict, track: str = "default") -> bool:
    try:
        items = library.get_topic(topic_id).get("items") or []
    except Exception:
        return False
    generated = [
        it for it in items
        if library.resolve_audio_file(library.item_path(topic_id, it["id"]), track=track)
    ]
    if len(generated) != manifest.get("item_count"):
        return True
    gen_at = manifest.get("generated_at") or ""
    return any(
        max((it.get("updated_at") or ""), (it.get("generated_at") or "")) > gen_at
        for it in generated
    )
