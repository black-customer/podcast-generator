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


@pytest.mark.skipif(not FFMPEG, reason="需要 ffmpeg")
def test_mastering_failure_is_raised(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio at all")
    out = tmp_path / "out.mp3"
    with pytest.raises(mastering.FFmpegError):
        mastering.apply_mastering(bad, out, is_dialogue=False)
