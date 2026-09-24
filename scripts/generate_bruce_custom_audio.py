"""Bruce 专属定制雅思口语强化音频生成脚本。

母题：Technology & Digital Life
针对 Bruce 原始回答中的“选择过多导致大脑疲劳”的高级思想进行 8.5 分母语化重构，
狙击其高频中式表达（there are too much options, make our brain think more），
植入心理学级通用语块：choice overload, decision fatigue, streamline。
"""
import sys
import uuid
from pathlib import Path

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.audio import _concat_line, _run, make_silence, probe_duration
from server.config import TMP_DIR, load_settings
from server.tts import fish_tts_dialogue


def make_beep(freq: int = 880, duration: float = 0.3) -> Path:
    out = TMP_DIR / f"beep_{freq}_{duration}s.mp3"
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"sine=frequency={freq}:duration={duration}",
        "-af", f"afade=t=in:ss=0:d=0.03,afade=t=out:st={duration-0.05}:d=0.05,volume=0.35",
        "-ar", "44100", "-ac", "1", "-b:a", "128k",
        str(out)
    ]
    _run(cmd)
    return out

def main():
    settings = load_settings()

    # Part 1: 认知启动 + 考官提问 + 8.5分母语者示范 + 语块精讲 + 考官再次提问
    part1_lines = [
        ("a", "雅思口语核心题：科技究竟让生活更轻松，还是更累？"),
        ("a", "Do you think technology has made our lives easier?"),
        ("a", "当你想表达“选项太多导致不知道选什么、大脑很疲惫”时，别再说 there are too much options。来听听八点五分母语者如何精准表达你的思想。"),
        ("b", "It's a bit of a double-edged sword, really. On the surface, technology definitely streamlines our daily routines. But on a deeper level, I'd say it has actually made life more overwhelming because of choice overload. When you're bombarded with endless options—like picking a language learning app—it triggers serious decision fatigue. So while physical tasks are easier, our cognitive load is heavier than ever."),
        ("a", "注意刚才把你的思想升华到八点五分的两个灵魂语块：第一个，代替 options are too many，母语者用了："),
        ("b", "Choice overload."),
        ("a", "选择过载。第二个，代替 make us tired of thinking，母语者用了："),
        ("b", "Decision fatigue."),
        ("a", "决策疲劳。聊购物、选专业、看视频，这两个表达都是降维打击的加分项。"),
        ("a", "现在，进行即时检索训练。考官马上问你，你有八秒时间，必须用上刚才的两个语块之一张嘴作答。Ready?"),
        ("a", "So, do you think technology has made our lives easier?"),
    ]

    # Part 3: 提示音收尾 + Coach 鼓励 + 核心答句肌肉固化
    part3_lines = [
        ("a", "非常棒！最后闭上眼睛，再听一遍母语者的核心答句，把它刻进你的潜意识肌肉里。"),
        ("b", "Technology streamlines our chores, but endless options trigger serious decision fatigue."),
    ]

    print("正在合成 Bruce 定制音频 Part 1...")
    part1_bytes = fish_tts_dialogue(part1_lines, settings)
    part1_file = TMP_DIR / f"bruce_part1_{uuid.uuid4().hex[:8]}.mp3"
    part1_file.write_bytes(part1_bytes)
    print(f"Part 1 完成，时长: {probe_duration(part1_file):.1f}s")

    print("正在合成 Bruce 定制音频 Part 3...")
    part3_bytes = fish_tts_dialogue(part3_lines, settings)
    part3_file = TMP_DIR / f"bruce_part3_{uuid.uuid4().hex[:8]}.mp3"
    part3_file.write_bytes(part3_bytes)
    print(f"Part 3 完成，时长: {probe_duration(part3_file):.1f}s")

    # 交互输出留白（起始音 + 8秒静音 + 结束音）
    beep_start = make_beep(freq=660, duration=0.25)
    silence = make_silence(8.0)
    beep_end = make_beep(freq=880, duration=0.25)

    concat_list = [
        part1_file,
        beep_start,
        silence,
        beep_end,
        part3_file
    ]

    out_file = Path("bruce_custom_mastery_audio.mp3")
    list_file = TMP_DIR / f"concat_{uuid.uuid4().hex[:8]}.txt"
    lines = [_concat_line(p) for p in concat_list]
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("正在拼接全段音频并做 -16 LUFS 广播级响度归一...")
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", "44100", "-ac", "1", "-b:a", "128k",
        str(out_file)
    ])
    list_file.unlink(missing_ok=True)

    duration = probe_duration(out_file)
    print("\n==========================================")
    print("Bruce 定制训练音频生成完毕！")
    print(f"文件路径: {out_file.resolve()}")
    print(f"总时长: {duration:.1f} 秒")
    print("==========================================")

if __name__ == "__main__":
    main()
