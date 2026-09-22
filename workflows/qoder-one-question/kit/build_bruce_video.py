"""把语块卡与 Track 02 音频同步，产出一支竖屏复习视频（手机上看不用盯屏幕找图）。

做法：读 audio_manifest.json 里每个 chunk 片段的起止时间 → 每张卡按真实时长停留
→ ffmpeg concat 图片序列 + 原音轨。图片先统一规格化到 1080x1350，避免不同尺寸
在 concat demuxer 下花屏。
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bruce_kit_content as C  # noqa: E402

from server.audio import _concat_line, _run, probe_duration  # noqa: E402

for _stream in (sys.stdout, sys.stderr):  # Windows 控制台默认 GBK，✓ 会崩掉整次构建
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

KIT = Path(__file__).resolve().parent / "learning_kit_bruce"
CARDS = KIT / "cards"
VIDEO = KIT / "video"
NORM = VIDEO / ".frames"
W, H = 1080, 1350


def normalize(src: Path, dst: Path) -> None:
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-vf", f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos,"
               f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=0x0b0e13",
        "-frames:v", "1", str(dst),
    ])


def build_reel(manifest: dict, track_id: str, prefix: str, card_map: dict[str, Path],
               title: str, out_name: str) -> Path | None:
    track = next((t for t in manifest["tracks"] if t["track"] == track_id), None)
    if not track:
        print(f"  跳过 {out_name}：清单里没有 Track {track_id}")
        return None

    marks = [m for m in track["markers"] if m["label"].startswith(prefix)]
    if not marks:
        print(f"  跳过 {out_name}：没有 {prefix} 标记")
        return None
    marks.sort(key=lambda m: m["start"])
    total = float(track["duration"])

    NORM.mkdir(parents=True, exist_ok=True)
    plan: list[tuple[Path, float]] = [
        (CARDS / "poster_05_chunk_sheet.png", marks[0]["start"]),
    ]
    for i, m in enumerate(marks):
        cid = m["label"].split(":", 1)[1]
        if cid not in card_map:
            continue
        end = marks[i + 1]["start"] if i + 1 < len(marks) else total
        plan.append((card_map[cid], max(3.0, end - m["start"])))

    audio = KIT / "audio" / track["file"]
    # 规格化到统一尺寸
    seq: list[Path] = []
    for i, (src, _dur) in enumerate(plan):
        dst = NORM / f"{i:03d}.png"
        normalize(src, dst)
        seq.append(dst)

    list_file = NORM / f"list-{uuid.uuid4().hex[:8]}.txt"
    lines = []
    for (_src, dur), dst in zip(plan, seq, strict=True):
        lines.append(_concat_line(dst))
        lines.append(f"duration {dur:.3f}")
    lines.append(_concat_line(seq[-1]))
    lines.append("duration 3")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out = VIDEO / out_name
    _run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-i", str(audio),
        "-vf", "fps=15,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "25",
        "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
        str(out),
    ])
    list_file.unlink(missing_ok=True)
    print(f"  ✓ {out.name}  {probe_duration(out):.0f}s  "
          f"标题：{title}")
    return out


def main() -> int:
    mpath = KIT / "audio_manifest.json"
    if not mpath.exists():
        print(f"缺少 {mpath}，请先跑 scripts/build_bruce_audio.py")
        return 1
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    card_map = {
        ch["id"]: CARDS / f"chunk_{i:02d}_{ch['id']}.png"
        for i, ch in enumerate(C.CHUNKS, 1)
    }
    missing = [k for k, p in card_map.items() if not p.exists()]
    if missing:
        print(f"缺卡片图：{missing[:5]}，请先跑 scripts/build_bruce_cards.py")
        return 1

    VIDEO.mkdir(parents=True, exist_ok=True)
    print("生成语块串烧视频…")
    made = build_reel(
        manifest, "02", "chunk:", card_map,
        "二十个语块 · 跟读版", "chunk_reel.mp4",
    )
    fossil_map = {
        f["id"]: CARDS / f"fossil_{i:02d}_{f['id']}.png"
        for i, f in enumerate(C.FOSSILS, 1)
    }
    print("生成化石纠错视频…")
    build_reel(
        manifest, "01", "fossil:", fossil_map,
        "十大化石 · 强制输出版", "repair_lab.mp4",
    )
    if made:
        print(f"\n完成 → {VIDEO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
