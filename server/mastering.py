"""面向跟读学习的近讲清晰母带：高通、轻压缩、统一响度。"""
import subprocess
from pathlib import Path

from .audio import FFmpegError, probe_duration

FFMPEG_TIMEOUT = 600


def apply_mastering(
    input_audio: Path,
    output_audio: Path,
    is_dialogue: bool = True,
) -> float:
    """执行克制的学习音频母带处理，返回处理后的音频时长。"""
    if not input_audio.exists() or input_audio.stat().st_size == 0:
        raise FFmpegError("输入音频不存在或为空")

    duration = probe_duration(input_audio)
    if duration <= 0:
        raise FFmpegError("无法探测音频时长")

    del is_dialogue  # 两种轨道都以清晰、居中的可模仿人声为目标
    filter_chain = ",".join([
        "highpass=f=70",
        "acompressor=threshold=-20dB:ratio=2:attack=15:release=180:makeup=1dB",
        "loudnorm=I=-16:TP=-1.5:LRA=7",
    ])

    output_audio.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = output_audio.with_suffix(".tmp.mp3")
    if tmp_out.exists():
        tmp_out.unlink()

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
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT)
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
                cmd_fallback, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT
            )
            if res2.returncode != 0:
                raise FFmpegError(f"FFmpeg 母带处理失败: {res2.stderr[:300]}")
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError(f"FFmpeg 母带处理超时: {exc}") from exc
    except OSError as exc:
        raise FFmpegError(f"执行 ffmpeg 失败: {exc}") from exc

    if tmp_out.exists():
        if output_audio.exists():
            output_audio.unlink()
        tmp_out.rename(output_audio)

    new_dur = probe_duration(output_audio)
    return new_dur
