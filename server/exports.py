"""M11 导出：整集 MP3 → 带 ffmetadata 章节的 M4B（供任意播放器/每日英语听力导入）。"""
import subprocess

from .assemble import episode_path, load_manifest
from .config import EPISODES_DIR, atomic_write_text


def _fmt_timestamp(ms: int) -> str:
    """ffmetadata 章节时间戳：毫秒整数。"""
    return str(max(0, ms))


def _escape_metadata(text: str) -> str:
    """ffmetadata 特殊字符转义（; # = \\ 与换行）。"""
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace("#", "\\#")
        .replace("=", "\\=")
        .replace("\n", "\\n")
    )


def build_ffmetadata(manifest: dict) -> str:
    lines = [";FFMETADATA1", f"title={_escape_metadata(manifest.get('topic_name') or 'Episode')}"]
    lines.append("artist=Bruce English Corpus")
    lines.append("album=Bruce English Corpus")
    cur_ms = 0
    for i, it in enumerate(manifest.get("items", [])):
        dur = float(it.get("duration_sec") or 0)
        start_ms = int(round(float(it.get("offset_sec") or cur_ms) * 1000))
        end_ms = start_ms + int(round(dur * 1000))
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={_fmt_timestamp(start_ms)}")
        lines.append(f"END={_fmt_timestamp(end_ms)}")
        lines.append(f"title={_escape_metadata(it.get('title') or f'Chapter {i + 1}')}")

        cur_ms = end_ms
    return "\n".join(lines) + "\n"


def export_m4b(topic_id: str, track: str = "podcast") -> dict:
    """把整集 MP3（含清单章节）转成带章节的 M4B。输出 data/exports/。"""
    manifest = load_manifest(topic_id, track=track)
    if not manifest:
        raise RuntimeError("本集尚未合成，请先合成整集")
    src = episode_path(topic_id, track=track)
    if not src.exists():
        raise RuntimeError("整集音频文件缺失，请重新合成")

    out_dir = EPISODES_DIR.parent / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{topic_id}_{track}.m4b"
    meta_file = out.with_suffix(".ffmeta.txt")

    atomic_write_text(meta_file, build_ffmetadata(manifest))
    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-i", str(meta_file),
        "-map", "0:a", "-map_metadata", "1",
        "-map_chapters", "1",
        "-c:a", "aac", "-b:a", "128k",
        str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(f"M4B 导出失败: {(proc.stderr or '')[-300:]}")
    meta_file.unlink(missing_ok=True)

    return {
        "file": str(out),
        "size": out.stat().st_size,
        "item_count": manifest.get("item_count"),
    }
