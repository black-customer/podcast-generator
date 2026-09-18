"""M03 音频 QA 门禁测试：时长比 + 静音孤岛 + 标签白名单 + 决策逻辑。"""
import subprocess
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server import audioqa


def _ffmpeg_ok() -> bool:
    try:
        return subprocess.run(["ffmpeg", "-version"], capture_output=True,
        timeout=15).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


FFMPEG = _ffmpeg_ok()


# ---------------------------------------------------------------- 时长比

def test_duration_ratio_pass():
    r = audioqa.check_duration_ratio("Hello there friend, how are you today?", 3.2)
    assert r["ok"] is True


def test_duration_ratio_flags_excess():
    # 文本约 2s，实际 8s（笑声/失控）→ 超比
    r = audioqa.check_duration_ratio("Hi there friend.", 8.0)
    assert r["ok"] is False
    assert r["ratio"] > audioqa.MAX_RATIO


def test_duration_ratio_flags_too_short():
    r = audioqa.check_duration_ratio("x" * 200, 1.0)
    assert r["ok"] is False


# ---------------------------------------------------------------- 标签白名单

def test_tag_whitelist():
    src = "Well [slight pause] I mean [chuckle] that is [long pause] fine [mad laughter] ok."
    cleaned, removed = audioqa.strip_disallowed_tags(src)
    assert "[slight pause]" in cleaned
    assert "[chuckle]" in cleaned
    assert "[mad laughter]" not in cleaned
    assert "[mad laughter]" in removed


def test_tag_whitelist_no_tags():
    cleaned, removed = audioqa.strip_disallowed_tags("plain text")
    assert cleaned == "plain text" and removed == []


# ---------------------------------------------------------------- 决策逻辑

def test_decide_pass():
    report = {"issues": []}
    assert audioqa.decide(report) == "pass"


def test_decide_retry_on_flag():
    report = {"issues": [{"kind": "duration_ratio", "severity": "high"}]}
    assert audioqa.decide(report) == "retry"


def test_decide_warn_low_severity():
    report = {"issues": [{"kind": "silence_island", "severity": "low"}]}
    assert audioqa.decide(report) == "keep_warn"


# ---------------------------------------------------------------- ffmpeg 实测

@pytest.mark.skipif(not FFMPEG, reason="需要 ffmpeg")
def test_silence_island_detection(tmp_path):
    f = tmp_path / "has_silence.mp3"
    subprocess.run(
        ["ffmpeg", "-y",
         "-f", "lavfi", "-i", "sine=frequency=300:duration=2",
         "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=4.5",
         "-f", "lavfi", "-i", "sine=frequency=300:duration=2",
         "-filter_complex", "[0][1][2]concat=n=3:v=0:a=1",
         "-ar", "44100", str(f)],
        capture_output=True, timeout=60,
    )
    assert f.exists() and f.stat().st_size > 1000
    r = audioqa.check_silence_islands(f)
    assert r["ok"] is False
    assert any(i["duration"] >= 3.0 for i in r["islands"])


@pytest.mark.skipif(not FFMPEG, reason="需要 ffmpeg")
def test_silence_pass_on_continuous_tone(tmp_path):
    f = tmp_path / "tone.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=5",
         "-ar", "44100", str(f)],
        capture_output=True, timeout=60,
    )
    r = audioqa.check_silence_islands(f, min_island=2.5)
    assert r["ok"] is True


# ---------------------------------------------------------------- 综合报告

@pytest.mark.skipif(not FFMPEG, reason="需要 ffmpeg")
def test_run_qa_report_shape(tmp_path):
    f = tmp_path / "tone.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=5",
         "-ar", "44100", str(f)],
        capture_output=True, timeout=60,
    )
    report = audioqa.run_qa(f, source_text="A reasonably long sentence to estimate duration.")
    assert report["verdict"] in ("pass", "keep_warn", "retry")
    assert "checks" in report and "issues" in report
