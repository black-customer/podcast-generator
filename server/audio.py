"""ffmpeg 工具：检测、时长探测、静音/占位音生成、mp3 拼接。"""
import subprocess
import uuid
from pathlib import Path

from .config import TMP_DIR


class FFmpegError(RuntimeError):
    pass


def check_ffmpeg() -> tuple[bool, str]:
    try:
        r = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0:
            first = (r.stdout or "").splitlines()[0][:80] if r.stdout else "ok"
            return True, first
        return False, "ffmpeg 返回了非零退出码"
    except FileNotFoundError:
        return False, "未找到 ffmpeg，请先安装并加入 PATH"
    except subprocess.TimeoutExpired:
        return False, "ffmpeg 命令超时"


def _run(args: list[str], timeout: float = 600) -> None:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise FFmpegError(f"ffmpeg 超时（>{timeout:.0f}s）: {args[0]} …")
    if proc.returncode != 0:
        tail = (proc.stderr or "")[-500:]
        raise FFmpegError(f"ffmpeg 失败: {tail}")


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "csv=p=0", str(path),
        ],
        capture_output=True, text=True, timeout=30,
    )
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def _concat_line(path: Path) -> str:
    posix = str(path.resolve()).replace("\\", "/")
    return "file '" + posix.replace("'", "'\\''") + "'"


def make_silence(seconds: float) -> Path:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    out = TMP_DIR / f"silence-{seconds:.2f}s.mp3"
    if not out.exists():
        # 先写临时文件再原子替换，避免并发任务同读同写同一缓存文件
        tmp = TMP_DIR / f"silence-{seconds:.2f}s.{uuid.uuid4().hex}.tmp.mp3"
        try:
            _run([
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "anullsrc=r=44100:cl=mono",
                "-t", f"{seconds:.3f}", "-ar", "44100", "-ac", "1",
                "-b:a", "64k", str(tmp),
            ])
            tmp.replace(out)
        finally:
            tmp.unlink(missing_ok=True)
    return out


def make_tone(seconds: float, out_path: Path) -> Path:
    """dry-run 占位音：低音量正弦音，时长按文本长度估算。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"sine=frequency=200:duration={max(0.8, seconds):.2f}",
        "-af", "volume=0.25", "-ar", "44100", "-ac", "1",
        "-b:a", "64k", str(out_path),
    ])
    return out_path


def concat_mp3(entries: list[dict], out_path: Path) -> None:
    """entries: [{path, gap_before}]，按顺序拼接、响度归一（-16 LUFS）并重编码为 44.1kHz 单声道 mp3。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for e in entries:
        gap = float(e.get("gap_before") or 0)
        if gap > 0:
            lines.append(_concat_line(make_silence(gap)))
        lines.append(_concat_line(e["path"]))
    list_file = TMP_DIR / f"concat-{uuid.uuid4().hex}.txt"
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "44100", "-ac", "1", "-b:a", "128k",
            str(out_path),
        ])
    finally:
        list_file.unlink(missing_ok=True)


def normalize_loudness(path: Path) -> None:
    """把已有音频文件原地响度归一到 -16 LUFS（不重新合成）。"""
    tmp = path.with_suffix(".norm.mp3")
    _run([
        "ffmpeg", "-y", "-i", str(path),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", "44100", "-ac", "1", "-b:a", "128k",
        str(tmp),
    ])
    tmp.replace(path)
