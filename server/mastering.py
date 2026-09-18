"""工业级广播声学母带处理流水线 (server/mastering.py)。

基于 FFmpeg 实现：
1. 录音棚空气微底噪注入 (Studio Room Tone at -54dBFS，消灭数字绝对死寂)；
2. 广播级人声温暖 EQ 塑形 (75Hz 切低频、220Hz 增暖、5.5kHz 柔化齿音、10kHz 提空气感)；
3. 广播级动态平滑压限 (Vocal Smooth Compression)；
4. 立体声声场空间增强 (Spatial Ambience)。
"""
import subprocess
from pathlib import Path

from .audio import FFmpegError, probe_duration

FFMPEG_TIMEOUT = 600


def apply_mastering(
    input_audio: Path,
    output_audio: Path,
    is_dialogue: bool = True,
    room_tone_level: float = 0.0018,  # 约 -55dBFS
) -> float:
    """对原始干音频执行广播级声学母带处理。返回母带处理后的音频时长。"""
    if not input_audio.exists() or input_audio.stat().st_size == 0:
        raise FFmpegError("输入音频不存在或为空")

    duration = probe_duration(input_audio)
    if duration <= 0:
        raise FFmpegError("无法探测音频时长")

    # 1. 广播级人声 EQ 与压限滤镜链
    # - highpass=f=75: 切除低频杂音与喷麦
    # - equalizer=f=220:g=2.0: 增强类似 Shure SM7B 的温暖胸腔感
    # - equalizer=f=5500:g=-2.5: 消刺耳齿音 (De-esser)
    # - equalizer=f=10500:g=1.5: 提升空气感与自然通透度
    # - acompressor: 广播级平滑压限，平衡音量动态
    vocal_filters = [
        "highpass=f=75",
        "equalizer=f=220:width_type=q:width=1.2:g=2.0",
        "equalizer=f=5500:width_type=q:width=2.0:g=-2.5",
        "equalizer=f=10500:width_type=q:width=1.0:g=1.5",
        "acompressor=threshold=-20dB:ratio=2.8:attack=15:release=220:makeup=2.2dB",
    ]
    if is_dialogue:
        # 对话模式增加轻度立体声场展宽，呈现圆桌面对面声学空间
        vocal_filters.append("extrastereo=m=1.22")

    vocal_filter_chain = ",".join(vocal_filters)

    # 2. Studio Room Tone (录音室温暖微底噪生成 + 高低切)
    # 使用粉红噪声经过 40-7000Hz 滤波，作为物理空间底噪垫底
    # 彻底抹除人类耳蜗对纯数字绝对死寂的生理排斥感
    room_tone_src = (
        f"anoisesrc=d={duration + 0.5}:c=pink:r=44100:a={room_tone_level},"
        "highpass=f=40,lowpass=f=7000"
    )

    # 3. 混合人声音轨与底噪声轨
    # normalize=0：amix 默认会把每个输入缩放 1/n（人声被拉低约 6dB），这里关闭归一，
    # 底噪振幅本身已压到 -55dBFS，直接相加即可保持人声原始响度
    filter_complex = (
        f"[0:a]{vocal_filter_chain}[vocal];"
        f"{room_tone_src}[ambience];"
        f"[vocal][ambience]amix=inputs=2:duration=first:dropout_transition=1:normalize=0[out]"
    )

    output_audio.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = output_audio.with_suffix(".tmp.mp3")
    if tmp_out.exists():
        tmp_out.unlink()

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_audio),
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        str(tmp_out),
    ]

    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT)
        if res.returncode != 0:
            # 降级：如果复杂的 filter_complex 失败（如旧版 ffmpeg 不支持 normalize），
            # 使用纯人声 EQ 链路，只损失底噪垫底
            cmd_fallback = [
                "ffmpeg",
                "-y",
                "-i",
                str(input_audio),
                "-af",
                vocal_filter_chain,
                "-c:a",
                "libmp3lame",
                "-b:a",
                "192k",
                "-ar",
                "44100",
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
