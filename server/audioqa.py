"""音频 QA 门禁 (M03)：生成后自动体检，异常隔离重试。

检查项：
- duration_ratio：实际时长 vs 文本估算时长（失控笑声/空转的直接信号）
- silence_island：ffmpeg silencedetect 找长静音孤岛（死寂/截断）
- clipping：ffmpeg astats 查满格削波
- vad_island（可选）：Silero VAD 查"非语音孤岛"——笑声、音乐等有声无语言内容
  （依赖未安装时自动跳过并在报告中注明）

决策 decide(report)：pass / retry（高严重度，触发去标签重试一次）/ keep_warn。
"""
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

# 实际/估算时长可接受区间（真人语速浮动 + 表演层停顿）
MIN_RATIO, MAX_RATIO = 0.45, 2.3

# 静音孤岛阈值（秒）——正常停顿不会到这里
SILENCE_MIN_ISLAND = 2.5
SILENCE_NOISE_DB = -38.0

# 允许送往 TTS 的表演标签（M15 表演规范联动；列表外标签在重试时剔除）
TAG_ALLOWLIST = {
    "slight pause", "short pause", "pause", "long pause",
    "chuckle", "laughs", "laugh", "sigh", "inhale", "exhale",
    "softly", "thoughtful", "speaking slightly faster", "speaking slightly slower",
    "curious", "relaxed", "uncertain", "emphasis", "break", "long-break",
}

_TAG_RE = re.compile(r"\[([^\[\]]*)\]")

SEVERITY = {
    "duration_ratio": "high",
    "silence_island": "low",
    "clipping": "medium",
    "vad_island": "medium",
    "zero_duration": "high",
}


def estimate_seconds(text: str) -> float:
    """与 tts.estimate_seconds 相同的口径（14 字符/秒）。"""
    return max(1.0, len(text or "") / 14.0)


# ---------------------------------------------------------------- 各项检查

def check_duration_ratio(source_text: str, actual_sec: float) -> dict:
    expected = estimate_seconds(source_text)
    ratio = actual_sec / expected if expected > 0 else 0.0
    return {
        "kind": "duration_ratio",
        "ok": MIN_RATIO <= ratio <= MAX_RATIO,
        "expected_sec": round(expected, 2),
        "actual_sec": round(actual_sec, 2),
        "ratio": round(ratio, 2),
        "severity": SEVERITY["duration_ratio"],
    }


def check_silence_islands(audio_path: Path, min_island: float = SILENCE_MIN_ISLAND) -> dict:
    r = subprocess.run(
        ["ffmpeg", "-i", str(audio_path), "-af",
         f"silencedetect=noise={SILENCE_NOISE_DB}dB:d={min_island}", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    islands = []
    starts = []
    for line in (r.stderr or "").splitlines():
        if "silence_start:" in line:
            starts.append(float(line.split("silence_start:")[1].strip()))
        elif "silence_end:" in line:
            # 行格式: ... silence_end: <end> | silence_duration: <dur>
            tail = line.split("silence_end:")[1]
            parts = tail.split("|")
            try:
                end = float(parts[0].strip())
            except ValueError:
                end = 0.0
            dur = 0.0
            if len(parts) > 1 and "duration" in parts[1]:
                m = re.search(r"([\d.]+)", parts[1])
                dur = float(m.group(1)) if m else 0.0
            if starts:
                islands.append({"start": starts.pop(0), "end": end, "duration": round(dur, 2)})
    return {
        "kind": "silence_island",
        "ok": not islands,
        "islands": islands,
        "severity": SEVERITY["silence_island"],
    }


def check_clipping(audio_path: Path) -> dict:
    r = subprocess.run(
        ["ffmpeg", "-i", str(audio_path), "-af", "astats=metadata=1:reset=0", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    peak = None
    for line in (r.stderr or "").splitlines():
        if "Peak level dB" in line:
            try:
                peak = float(line.split(":")[-1].strip())
            except ValueError:
                continue
    ok = peak is None or peak < -0.1
    return {"kind": "clipping", "ok": ok, "peak_db": peak, "severity": SEVERITY["clipping"]}


def check_vad_islands(audio_path: Path, min_island: float = 3.0) -> dict:
    """Silero VAD：检测有声但非语音的孤岛（笑声等）。依赖缺失时优雅跳过。"""
    try:
        import torch  # noqa: F401
        from silero_vad import get_speech_timestamps, load_silero_vad, read_audio
    except ImportError:
        return {"kind": "vad_island", "ok": True, "skipped": "silero-vad 未安装", "severity": "low"}
    try:
        model = load_silero_vad()
        wav = read_audio(str(audio_path), sampling_rate=16000)
        ts = get_speech_timestamps(wav, model, sampling_rate=16000)
        total = len(wav) / 16000.0
        # 语音区间合并 → 反转得非语音区间
        speech = sorted([(s["start"] / 16000.0, s["end"] / 16000.0) for s in ts])
        gaps = []
        cur = 0.0
        for s, e in speech:
            if s - cur >= min_island:
                gaps.append({"start": round(cur, 2), "end": round(s, 2),
                "duration": round(s - cur, 2)})
            cur = max(cur, e)
        if total - cur >= min_island:
            gaps.append({"start": round(cur, 2), "end": round(total, 2),
            "duration": round(total - cur, 2)})
        return {
            "kind": "vad_island",
            "ok": not gaps,
            "islands": gaps,
            "total_sec": round(total, 2),
            "severity": SEVERITY["vad_island"],
        }
    except Exception as exc:  # VAD 失败不阻断主流程
        return {
            "kind": "vad_island",
            "ok": True,
            "skipped": f"VAD 执行失败: {exc}",
            "severity": "low",
        }


# ---------------------------------------------------------------- 决策与入口

def decide(report: dict) -> str:
    severities = {i["kind"]: i.get("severity", "low") for i in report.get("issues", [])}
    if any(s == "high" for s in severities.values()):
        return "retry"
    if severities:
        return "keep_warn"
    return "pass"


def run_qa(
    audio_path: Path,
    source_text: str,
    duration_sec: float | None = None,
    skip_vad: bool = False,
) -> dict:
    """综合体检。duration_sec 缺省时现场探测；skip_vad 用于 dry-run（占位音非语音）。"""
    from .audio import probe_duration

    if duration_sec is None:
        duration_sec = probe_duration(audio_path)
    checks = []
    issues = []
    if duration_sec <= 0:
        issues.append({"kind": "zero_duration", "severity": "high", "detail": "时长为 0"})
    else:
        c = check_duration_ratio(source_text, duration_sec)
        checks.append(c)
        if not c["ok"]:
            issues.append(c)
    for checker in (check_silence_islands, check_clipping):
        try:
            c = checker(audio_path)
        except Exception as exc:
            c = {"kind": checker.__name__, "ok": True, "skipped": f"{exc}", "severity": "low"}
        checks.append(c)
        if not c["ok"]:
            issues.append(c)
    if not skip_vad:
        try:
            c = check_vad_islands(audio_path)
        except Exception as exc:
            c = {"kind": "vad_island", "ok": True, "skipped": f"{exc}", "severity": "low"}
        checks.append(c)
        if not c["ok"]:
            issues.append(c)
    report = {
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "duration_sec": round(duration_sec, 2),
        "verdict": decide({"issues": issues}),
        "issues": issues,
        "checks": checks,
    }
    return report


def strip_disallowed_tags(text: str) -> tuple[str, list[str]]:
    """剔除白名单外的 [tag]，返回 (清理文本, 被移除标签列表)。"""
    removed: list[str] = []

    def _sub(m: re.Match) -> str:
        tag = m.group(1).strip().lower()
        if tag in TAG_ALLOWLIST:
            return m.group(0)
        removed.append(m.group(0))
        return ""

    cleaned = _TAG_RE.sub(_sub, text or "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned, removed


def strip_all_tags(text: str) -> tuple[str, list[str]]:
    """QA 重试路径用：剥离全部 [tag]（包括白名单内的 [chuckle] 等——
    重试是恢复路径，最干净文本成功率最高；正常音频不受影响）。"""
    removed = _TAG_RE.findall(text or "")
    cleaned = _TAG_RE.sub("", text or "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    return cleaned, removed


def save_qa_report(report: dict, file_path: Path) -> None:
    from .config import atomic_write_text

    atomic_write_text(file_path, json.dumps(report, ensure_ascii=False, indent=2))
