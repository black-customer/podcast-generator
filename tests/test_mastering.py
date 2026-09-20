"""M18：母带处理测试（对合成音调文件跑 mastering 链路）。"""
import subprocess
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server import audio, mastering


def _ffmpeg_ok() -> bool:
    try:
        proc = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=15)
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


FFMPEG = _ffmpeg_ok()


@pytest.mark.skipif(not FFMPEG, reason="需要 ffmpeg")
def test_mastering_produces_valid_audio(tmp_path):
    src = tmp_path / "tone.mp3"
    audio.make_tone(3.0, src)
    out = tmp_path / "mastered.mp3"
    dur = mastering.apply_mastering(src, out, is_dialogue=False)
    assert out.exists() and out.stat().st_size > 5000
    assert dur > 2.0
    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=channels", "-of", "csv=p=0", str(out),
        ],
        capture_output=True, text=True, timeout=30,
    )
    assert probe.stdout.strip() == "1"


@pytest.mark.skipif(not FFMPEG, reason="需要 ffmpeg")
def test_mastering_targets_learning_audio_loudness(tmp_path):
    src = tmp_path / "tone.mp3"
    audio.make_tone(4.0, src)
    out = tmp_path / "mastered.mp3"
    mastering.apply_mastering(src, out, is_dialogue=True)

    measured = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(out), "-af", "ebur128", "-f", "null", "-"],
        capture_output=True, text=True, timeout=60,
    )
    import re
    matches = re.findall(r"I:\s*(-?[\d.]+) LUFS", measured.stderr or "")
    assert matches, measured.stderr[-1000:]
    assert abs(float(matches[-1]) - (-16.0)) <= 1.0


@pytest.mark.skipif(not FFMPEG, reason="需要 ffmpeg")
def test_mastering_failure_is_raised(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio at all")
    out = tmp_path / "out.mp3"
    with pytest.raises(mastering.FFmpegError):
        mastering.apply_mastering(bad, out, is_dialogue=False)
