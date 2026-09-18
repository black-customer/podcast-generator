"""字幕与 RSS 导出 (M12)：VTT / LRC / 局域网 RSS feed。"""
import html
import re

from . import library
from .assemble import episode_path, load_manifest
from .config import EPISODES_DIR, atomic_write_text


def _ts_vtt(sec: float) -> str:
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _ts_lrc(sec: float) -> str:
    ms = int(round(sec * 1000))
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"[{m:02d}:{s:02d}.{ms // 10:02d}]"


def _strip_tags(text: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", text or "").strip()


def _load_doc(topic_id: str, item_id: str, track: str) -> dict | None:
    from . import alignment

    ipath = library.item_path(topic_id, item_id)
    doc = alignment.load_alignment(
        ipath / f"alignment_{track}.json",
        expect_audio=ipath / f"audio_{track}.mp3",
    )
    if not doc and (ipath / "audio.mp3").exists():
        alt = "podcast" if track != "podcast" else "monologue"
        doc = alignment.load_alignment(
            ipath / f"alignment_{alt}.json", expect_audio=ipath / "audio.mp3"
        )
    return doc


def _write_export(filename: str, content: str) -> dict:
    out_dir = EPISODES_DIR.parent / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / filename
    atomic_write_text(out, content)
    return {"file": str(out)}


def export_vtt(topic_id: str, item_id: str, track: str = "podcast") -> dict:
    """WebVTT 字幕：有逐词数据时输出词级 cue，否则句级。"""
    doc = _load_doc(topic_id, item_id, track)
    if not doc:
        raise RuntimeError("没有可用的对齐数据（请先生成音频）")
    cues = []
    if doc.get("words"):
        for w in doc["words"]:
            cues.append(f"{_ts_vtt(w['start'])} --> {_ts_vtt(w['end'])}\n{w['text']}")
    else:
        for seg in doc["segments"]:
            text = _strip_tags(seg.get("text", ""))
            if text:
                cues.append(f"{_ts_vtt(seg['start'])} --> {_ts_vtt(seg['end'])}\n{text}")
    content = "WEBVTT\n\n" + "\n\n".join(cues) + "\n"
    out = _write_export(f"{topic_id}_{item_id}_{track}.vtt", content)
    return {**out, "cues": len(cues)}


def export_lrc(topic_id: str, item_id: str, track: str = "podcast") -> dict:
    """LRC 歌词：句级时间标签，可供音乐播放器滚动歌词。"""
    doc = _load_doc(topic_id, item_id, track)
    if not doc:
        raise RuntimeError("没有可用的对齐数据（请先生成音频）")
    lines = [
        f"{_ts_lrc(seg['start'])}{_strip_tags(seg.get('text', ''))}" for seg in doc["segments"]
    ]
    content = "\n".join(lines) + "\n"
    out = _write_export(f"{topic_id}_{item_id}_{track}.lrc", content)
    return {**out, "lines": len(lines)}


def export_srt(topic_id: str, item_id: str, track: str = "podcast") -> dict:
    """SRT 字幕（句级）。"""
    doc = _load_doc(topic_id, item_id, track)
    if not doc:
        raise RuntimeError("没有可用的对齐数据（请先生成音频）")

    def _ts_srt(sec: float) -> str:
        ms = int(round(sec * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    blocks = []
    for i, seg in enumerate(doc["segments"], start=1):
        text = _strip_tags(seg.get("text", ""))
        if not text:
            continue
        blocks.append(
            f"{i}\n{_ts_srt(seg['start'])} --> {_ts_srt(seg['end'])}\n{text}\n"
        )
    content = "\n".join(blocks)
    out = _write_export(f"{topic_id}_{item_id}_{track}.srt", content)
    return {**out, "blocks": len(blocks)}


def build_rss(base_url: str) -> str:
    """局域网 RSS：全部话题整集（podcast→monologue→default 顺序取第一个可用）。"""
    topics = library.list_topics()
    items_xml = []
    for t in topics:
        for track in ("podcast", "monologue", "default"):
            manifest = load_manifest(t["id"], track=track)
            if manifest:
                break
        else:
            continue
        audio_file = episode_path(t["id"], track=track)
        if not audio_file.exists():
            continue
        guid = f"bruce-corpus-{t['id']}-{manifest.get('generated_at', '')}"
        title = html.escape(manifest.get("topic_name") or t["id"])
        enclosure = html.escape(
            f"{base_url}/api/topics/{t['id']}/episode/audio?track={track}"
        )
        size = audio_file.stat().st_size
        dur_min = int((manifest.get("total_sec") or 0) / 60) + 1
        items_xml.append(
            "    <item>\n"
            f"      <title>{title}</title>\n"
            "      <description>Bruce English Corpus episode</description>\n"
            f'      <enclosure url="{enclosure}" length="{size}" type="audio/mpeg"/>\n'
            f'      <guid isPermaLink="false">{html.escape(guid)}</guid>\n'
            f"      <pubDate>{html.escape(manifest.get('generated_at', ''))}</pubDate>\n"
            f"      <itunes:duration>{dur_min}</itunes:duration>\n"
            "    </item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">\n'
        "  <channel>\n"
        "    <title>Bruce English Corpus</title>\n"
        "    <description>Personal English input materials (LAN only)</description>\n"
        "    <language>en</language>\n"
        + "\n".join(items_xml)
        + "\n  </channel>\n</rss>\n"
    )
