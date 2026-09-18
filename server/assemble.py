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

    entries = [
        {"path": it["audio"], "gap_before": gap_ms / 1000.0 if i else 0.0}
        for i, it in enumerate(items)
    ]
    out = episode_path(topic_id, track=track)
    audio.concat_mp3(entries, out)
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
            }
            for it in items
        ],
    }
    atomic_write_text(
        episode_manifest_path(topic_id, track=track),
        json.dumps(manifest, ensure_ascii=False, indent=2),
    )
    return manifest


def load_manifest(topic_id: str, track: str = "default") -> dict | None:
    f = episode_manifest_path(topic_id, track=track)
    if not f.exists() and track != "default":
        f = episode_manifest_path(topic_id, track="default")
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
    return None
