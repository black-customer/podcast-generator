"""M02 验收脚本：抽样句级 span，用 ffmpeg 切听验证对齐精度。

判据（每条采样句）：
  1. 切出的片段时长与 span 时长差 < 0.15s
  2. 片段不是纯静音（mean_volume > -45dB，即确有语音/内容落在 span 内）
  3. 相邻 span 无缝隙/重叠异常（|next.start - cur.end| < 0.05s，允许拼接 gap）

用法：
  .venv/Scripts/python scripts/verify_alignment_ac.py <topic_id> <item_id> [track] [sample_n]
"""
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import alignment, library

TOLERANCE_S = 0.15
SILENCE_DB = -45.0


def probe_cut_mean_db(path: Path) -> float:
    r = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, timeout=60,
    )
    for line in (r.stderr or "").splitlines():
        if "mean_volume:" in line:
            return float(line.split("mean_volume:")[1].replace("dB", "").strip())
    return -99.0


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    topic_id, item_id = sys.argv[1], sys.argv[2]
    track = sys.argv[3] if len(sys.argv) > 3 else "podcast"
    sample_n = int(sys.argv[4]) if len(sys.argv) > 4 else 5

    ipath = library.item_path(topic_id, item_id)
    audio_path = library.resolve_audio_file(ipath, track)
    if not audio_path:
        print(f"FAIL: 轨道 {track} 无音频")
        return 1
    doc = alignment.load_alignment(
        ipath / f"alignment_{track}.json",
        expect_audio=audio_path,
    )
    if not doc:
        print(f"FAIL: alignment_{track}.json 缺失或失效")
        return 1
    segs = [s for s in doc["segments"] if s["end"] - s["start"] > 0.3]
    if len(segs) < 2:
        print("FAIL: 可采样句不足")
        return 1

    print(f"track={track} mode={doc['mode']} segments={len(doc['segments'])} 采样 {sample_n} 条")
    sample = random.sample(segs, min(sample_n, len(segs)))
    tmp = Path("data/.tmp") / "ac-check"
    tmp.mkdir(parents=True, exist_ok=True)

    failures = []
    for i, s in enumerate(sample):
        cut = tmp / f"cut-{i}.mp3"
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{s['start']}", "-to", f"{s['end']}",
             "-i", str(audio_path), "-c:a", "libmp3lame", "-b:a", "64k", str(cut)],
            capture_output=True, timeout=60,
        )
        if not cut.exists():
            failures.append(f"[{i}] 切割失败")
            continue
        dur_probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(cut)],
            capture_output=True, text=True, timeout=30,
        )
        try:
            actual = float(dur_probe.stdout.strip())
        except ValueError:
            actual = 0.0
        expected = s["end"] - s["start"]
        mean_db = probe_cut_mean_db(cut)
        ok_dur = abs(actual - expected) < TOLERANCE_S
        ok_speech = mean_db > SILENCE_DB
        status = "OK " if (ok_dur and ok_speech) else "FAIL"
        print(f"[{status}] span {s['start']:.2f}-{s['end']:.2f} "
              f"期望 {expected:.2f}s 实际 {actual:.2f}s ({'ok' if ok_dur else '超差'}) "
              f"能量 {mean_db:.1f}dB ({'有内容' if ok_speech else '疑似静音'})")
        if not (ok_dur and ok_speech):
            failures.append(
                f"[{i}] dur {actual:.2f} vs {expected:.2f}, db {mean_db:.1f}, text={s['text'][:30]}"
            )
        cut.unlink(missing_ok=True)

    # 相邻接续性
    ordered = sorted(doc["segments"], key=lambda x: x["start"])
    for a, b in zip(ordered, ordered[1:], strict=False):
        gap = b["start"] - a["end"]
        if gap < -0.05:
            failures.append(f"重叠异常: {a['end']:.2f} > {b['start']:.2f}")

    if failures:
        print("\n=== AC FAIL ===")
        for f in failures:
            print(" -", f)
        return 1
    print("\n=== AC PASS（模式: %s）===" % doc["mode"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
