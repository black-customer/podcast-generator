"""面向跟读学习的近讲清晰母带：高通、轻压缩、统一响度。"""
import subprocess
from pathlib import Path
from uuid import uuid4

from .audio import FFmpegError, probe_duration
from .config import atomic_replace

FFMPEG_TIMEOUT = 600


def apply_mastering(
    input_audio: Path,
    output_audio: Path,
    is_dialogue: bool = True,
) -> float:
    """执行克制的学习音频母带处理，返回处理后的音频时长。"""
    if not input_audio.exists() or input_audio.stat().st_size == 0:
        raise FFmpegError("输入音频不存在或为空")

    del is_dialogue  # 两种轨道都以清晰、居中的可模仿人声为目标
    filter_chain = ",".join([
        "highpass=f=70",
        "acompressor=threshold=-20dB:ratio=2:attack=15:release=180:makeup=1dB",
        "loudnorm=I=-16:TP=-1.5:LRA=7",
    ])

    output_audio.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = output_audio.with_name(f".{output_audio.stem}.{uuid4().hex}.tmp.mp3")

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_audio),
        "-af",
        filter_chain,
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-ac",
        "1",
        str(tmp_out),
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace",
                             timeout=FFMPEG_TIMEOUT)
        if res.returncode != 0:
            # 极旧 ffmpeg 的压缩器参数若不兼容，至少保留响度归一与单声道输出。
            cmd_fallback = [
                "ffmpeg",
                "-y",
                "-i",
                str(input_audio),
                "-af",
                "highpass=f=70,loudnorm=I=-16:TP=-1.5:LRA=7",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "192k",
                "-ar",
                "44100",
                "-ac",
                "1",
                str(tmp_out),
            ]
            res2 = subprocess.run(
                cmd_fallback, capture_output=True, encoding="utf-8", errors="replace",
                timeout=FFMPEG_TIMEOUT,
            )
            if res2.returncode != 0:
                raise FFmpegError(f"FFmpeg 母带处理失败: {res2.stderr[:300]}")
        new_dur = probe_duration(tmp_out)
        if new_dur <= 0:
            raise FFmpegError("母带处理没有生成可用的音频")
        atomic_replace(tmp_out, output_audio)
        return new_dur
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"FFmpeg 母带处理超时: {exc}") from exc
    except OSError as exc:
        raise FFmpegError(f"执行 ffmpeg 失败: {exc}") from exc

    finally:
        tmp_out.unlink(missing_ok=True)
