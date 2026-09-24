"""实验音频生成脚本：雅思 8-9 分神经闭环训练音频。

基于用户对 01-shoes / 001 题目的真实回答，生成一份高能训练音频：
1. 纯单语行多说话人（A: Mia 教练/考官，B: Ethan 母语者模范）
2. 痛点破除 + 8.5分母语者示范
3. 2 个通用语块特写
4. 8 秒强制检索与张嘴输出窗口（带提示音）
5. 核心答句神经固化
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
    """生成一个短促柔和的提示音（带淡入淡出）。"""
    out = TMP_DIR / f"beep_{freq}_{duration}s.mp3"
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"sine=frequency={freq}:duration={duration}",
        "-af", f"afade=t=in:ss=0:d=0.03,afade=t=out:st={duration-0.05}:d=0.05,volume=0.4",
        "-ar", "44100", "-ac", "1", "-b:a", "128k",
        str(out)
    ]
    _run(cmd)
    return out

def main():
    settings = load_settings()

    # 阶段 1：引导 + 考官提问 + 母语者回答 + 语块精讲 + 考官再提问
    part1_lines = [
        ("a", "雅思口语高频题：买鞋与购买频率。"),
        ("a", "Do you like buying shoes? How often do you buy them?"),
        ("a", "当你想表达家里不富裕、鞋穿坏了才换、两三年才买一双，别再说家里没钱。先听听母语者怎么说。"),
        ("b", "To be honest, not really. I wouldn't say I'm big on shoe shopping, mostly because my family has always been pretty frugal. I usually just wear a pair into the ground—like, until they start showing real signs of wear and tear, usually after a couple of years. It's not like they're completely falling apart, but once the soles give out or the leather scuffs up, that's when I'll get a replacement. So yeah, I only pick up a new pair maybe once every two or three years."),
        ("a", "注意刚才回答里的两个神仙语块：第一个，代替穿烂了，母语者用了："),
        ("b", "Wear a pair into the ground."),
        ("a", "把鞋穿到彻底报废。第二个，代替有些损坏，母语者用了："),
        ("b", "Wear and tear."),
        ("a", "日常磨损。衣服、手机、数码产品，任何话题都能通用。"),
        ("a", "现在，激活大脑输出回路。考官马上问你，你有八秒时间，必须张嘴用上刚才的两个语块之一。准备好了吗？"),
        ("a", "So, do you like buying shoes? How often do you buy them?"),
    ]

    # 阶段 3：收尾与神经回路固化
    part3_lines = [
        ("a", "做得好！最后闭上眼睛，再听一遍母语者的核心答句，固化你的发音肌肉记忆。"),
        ("b", "I'm not big on shopping, so I usually just wear a pair into the ground until there's visible wear and tear."),
    ]

    print("正在合成 Part 1 (引导 + 示范 + 语块特写 + 考官提问)...")
    part1_bytes = fish_tts_dialogue(part1_lines, settings)
    part1_file = TMP_DIR / f"exp_part1_{uuid.uuid4().hex[:8]}.mp3"
    part1_file.write_bytes(part1_bytes)
    print(f"Part 1 完成，文件大小: {len(part1_bytes)} bytes，时长: {probe_duration(part1_file):.1f}s")

    print("正在合成 Part 3 (收尾复盘 + 核心句强化)...")
    part3_bytes = fish_tts_dialogue(part3_lines, settings)
    part3_file = TMP_DIR / f"exp_part3_{uuid.uuid4().hex[:8]}.mp3"
    part3_file.write_bytes(part3_bytes)
    print(f"Part 3 完成，文件大小: {len(part3_bytes)} bytes，时长: {probe_duration(part3_file):.1f}s")

    # 阶段 2：输出窗口（起始提示音 + 7.5 秒静音 + 结束提示音）
    beep_start = make_beep(freq=660, duration=0.25)
    silence = make_silence(7.5)
    beep_end = make_beep(freq=880, duration=0.25)

    # 拼接清单
    concat_list = [
        part1_file,
        beep_start,
        silence,
        beep_end,
        part3_file
    ]

    target_dir = Path("data/topics/01-shoes/items/001-do-you-like-buying-shoes-how-often")
    out_file = target_dir / "audio_experimental.mp3"

    # 生成 concat 清单
    list_file = TMP_DIR / f"concat_{uuid.uuid4().hex[:8]}.txt"
    lines = [_concat_line(p) for p in concat_list]
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print("正在拼接全段音频并做 -16 LUFS 响度归一...")
    _run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", "44100", "-ac", "1", "-b:a", "128k",
        str(out_file)
    ])
    list_file.unlink(missing_ok=True)

    # 也拷贝一份到仓库根目录，方便用户一眼看到和直接用播放器点开
    root_sample = Path("audio_experimental_sample.mp3")
    root_sample.write_bytes(out_file.read_bytes())

    duration = probe_duration(out_file)
    print("\n==========================================")
    print("实验音频生成成功！")
    print(f"输出文件 1: {out_file.resolve()}")
    print(f"输出文件 2: {root_sample.resolve()}")
    print(f"总时长: {duration:.1f} 秒")
    print("==========================================")

if __name__ == "__main__":
    main()
