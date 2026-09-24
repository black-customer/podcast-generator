"""Bruce 雅思口语 41 题全量定制 5 大主题神经闭环音频生成套件。

涵盖 5 大主题专辑：
1. 具象物品与生活常识词穷大解救 (Physical Objects & Everyday Senses)
2. 科技、职业野心与掌控力 (Tech, Ambition & Executive Agency)
3. 人际、家庭羁绊与习惯心理 (Habits, Family & Social Psychology)
4. 艺术、幽默与代际精神世界 (Art, Comedy & Generational Depth)
5. 地理水土、城市变迁与浩瀚宇宙 (Cities, Environment & Astrophysics)

纯单语行多说话人：
- A: Mia（中文讲解教练 / 英文考官）
- B: Ethan（8.5分母语者模范回答）
内嵌 8 秒强制检索留白（带提示音），最后进行 -16 LUFS 广播级母带处理。
完全独立运行，不改动项目核心与既有前端。
"""
import sys
import uuid
from pathlib import Path

# 将项目根目录加入 sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from server.audio import _concat_line, _run, make_silence, probe_duration
from server.config import TMP_DIR, load_settings
from server.tts import fish_tts_dialogue

OUTPUT_DIR = BASE_DIR / "bruce_study_suite" / "audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def make_beep(freq: int = 880, duration: float = 0.25) -> Path:
    """生成柔和提示音。"""
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


# 5 大专辑完整剧本设计
TRACKS_CONFIG = [
    {
        "id": "track_01",
        "filename": "bruce_track_01_objects_and_senses.mp3",
        "title": "具象物品与生活常识词穷大解救",
        "part1_lines": [
            ("a", "Bruce 专属训练专辑第一期：具象物品与生活常识。"),
            ("a", "你回忆一下，之前聊到手电筒、放大镜、耳机孔时，你是不是在考场上即兴造词，说出了 fresh spot, manifest mirror 和 entrance to headphones？"),
            ("a", "这就是典型的心理词汇断层。先听听考官这道经典题目："),
            ("a", "What kind of interesting things have you done with science?"),
            ("a", "现在，听八点五分母语者如何精准表达你拿放大镜聚焦阳光烧纸、拿手电筒照向夜空的经历。"),
            ("b", "Back in primary school, I was obsessed with hands-on experiments. I remember taking a magnifying glass outside to focus sunlight onto a dry piece of scrap paper until it actually caught fire. Another quirky memory was pointing a powerful flashlight beam straight up into the pitch-black sky, wondering how far those photons could actually travel into deep space. It was just pure childhood curiosity."),
            ("a", "注意刚才拯救你词穷车祸的三个灵魂语块：第一个，代替 manifest mirror，放大镜的准确地道说法是："),
            ("b", "Magnifying glass."),
            ("a", "第二个，代替 fresh ball to sky，手电筒光束母语者叫："),
            ("b", "Flashlight beam."),
            ("a", "第三个，聚焦阳光点燃纸张："),
            ("b", "Focus sunlight onto scrap paper."),
            ("a", "还有聊到手表时，代替 identity simple，表示身份象征叫 status symbol；说富豪带手表跑路，这是高密度便携资产："),
            ("b", "A portable store of value."),
            ("a", "现在激活你的主动提取回路。考官提问后有八秒静音，请务必用上 magnifying glass 或 flashlight beam 张嘴回答！"),
            ("a", "So Bruce, what kind of interesting things have you done with science?"),
        ],
        "silence_sec": 8.0,
        "part3_lines": [
            ("a", "太棒了！最后闭上眼睛，再听一遍母语者的核心答句，把精准物理语块固化进发音肌肉。"),
            ("b", "I focused sunlight through a magnifying glass and pointed a flashlight beam directly into space."),
        ]
    },
    {
        "id": "track_02",
        "filename": "bruce_track_02_tech_ambition_agency.mp3",
        "title": "野心、科技与个人掌控力",
        "part1_lines": [
            ("a", "Bruce 专属训练专辑第二期：野心、科技与个人掌控力。"),
            ("a", "你聊到转学计算机、搞 Vibe coding、早上早起学习带给你的执行力，你的底层逻辑非常深刻，但经常受限于 must to try 和 executive ability 这种中式直译。"),
            ("a", "听考官提问："),
            ("a", "Why do you prefer to study in the mornings, and how do you use technology in your studies?"),
            ("a", "听八点五分母语者如何把你的晨起掌控感与 AI 杠杆升华展现："),
            ("b", "For me, waking up early and diving straight into study gives me a profound sense of agency and discipline. The world is completely quiet, and there are zero distractions. When it comes to tech, AI is a non-negotiable imperative. I heavily rely on vibe coding and generative tools to debug my ideas, which streamlines my workflow and allows me to build real-world software without getting bogged down by boilerplate syntax."),
            ("a", "注意刚才两个展现认知维度的灵魂语块：第一个，代替中式 executive ability，早起给你的掌控感与自律叫："),
            ("b", "A profound sense of agency and discipline."),
            ("a", "自我主导权。第二个，代替 must to use AI，必须使用的时代必然叫："),
            ("b", "A non-negotiable imperative."),
            ("a", "时代不可逆的刚需。聊到职业时，你不想打工想赚钱，母语者会说：追求财务自主与创业尝试："),
            ("b", "Pursuing financial autonomy and entrepreneurial ventures."),
            ("a", "现在进入输出窗口。听到提示音后，你有八秒时间，用上 sense of agency 或 non-negotiable 张嘴回答。"),
            ("a", "Why do you prefer to study in the mornings, Bruce?"),
        ],
        "silence_sec": 8.0,
        "part3_lines": [
            ("a", "漂亮！最后闭上眼睛，再听一遍母语者的核心答句，刻进你的潜意识。"),
            ("b", "Studying early gives me a profound sense of agency, while AI has become a non-negotiable imperative."),
        ]
    },
    {
        "id": "track_03",
        "filename": "bruce_track_03_habits_family_psychology.mp3",
        "title": "人际、家庭羁绊与习惯心理",
        "part1_lines": [
            ("a", "Bruce 专属训练专辑第三期：家庭羁绊、习惯与避坑指南。"),
            ("a", "在聊到收拾房间时，你犯了一个考场致命的扣分错误：提到妈妈时连续出现 he kind of spoiled me, he will clean the room himself。中国考生经常把 he she 混淆，考官听了极其别扭。"),
            ("a", "同时在聊到社交媒体时，你把戒不掉错说成了 can get rid of。来听听母语考官的标准提问："),
            ("a", "Did you keep your room tidy as a child, and how do your friends interact with social media?"),
            ("a", "听八点五分母语者如何表达被母亲宠溺、以及年轻人无法自拔地沉迷手机："),
            ("b", "Honestly, I was pretty untidy as a kid. My room was usually chaotic, and my mom would lecture me, but she also coddled me a bit, so she often ended up cleaning it herself. As for social media, most of my friends are virtually glued to their screens. We just cannot tear ourselves away from endless feeds and short videos. It has become an inseparable part of modern social currency."),
            ("a", "注意刚才的纠错与语块亮点：第一，妈妈是女性，每一次都必须下意识输出："),
            ("b", "She coddled me, so she cleaned it herself."),
            ("a", "用 coddle 表达宠爱娇惯。第二，代替 can get rid of，表达无法自拔、离不开手机："),
            ("b", "Glued to their screens, cannot tear themselves away."),
            ("a", "第三，在聊到实体店购物时，代替 touch with different organ，触感体验叫："),
            ("b", "Tactile feedback and sensory experience."),
            ("a", "现在进入纠错实战。考官马上问你，务必用上正确代词 she 和 coddle，张嘴输出八秒！"),
            ("a", "So did you use to keep your room tidy as a child?"),
        ],
        "silence_sec": 8.0,
        "part3_lines": [
            ("a", "非常好，代词神经反射已经激活！再听一遍核心锚定句。"),
            ("b", "My mom scolded me, but she always coddled me and cleaned my room herself."),
        ]
    },
    {
        "id": "track_04",
        "filename": "bruce_track_04_art_humor_generations.mp3",
        "title": "艺术、幽默与代际精神世界",
        "part1_lines": [
            ("a", "Bruce 专属训练专辑第四期：艺术、幽默与代际深层思辨。"),
            ("a", "你在转写文本里对周星驰、演唱会以及代际心理的分析非常精彩！但你把大型场馆演唱会说成 sport museum, life show，把情绪不合时听欢快音乐的违和感说成了 very disgusting。"),
            ("a", "Disgusting 在英语里是恶心反胃，而你真正想表达的是格格不入、情绪割裂。听考官提问："),
            ("a", "Have you ever attended a live show, and how does music affect people across different generations?"),
            ("a", "听八点五分母语者如何用高阶语块演绎你的见解："),
            ("b", "I went to a massive live concert in an indoor arena during my freshman year, and the atmosphere was absolutely surreal. As for music across eras, I believe it mirrors societal shifts. The older generation dealt with material scarcity and focused on survival, whereas younger folks are grappling with emotional isolation and existential angst. For us, genres like hip-hop offer a raw emotional outlet and visceral resonance."),
            ("a", "注意刚才精准表达你思想的三个黄金语块：第一个，代替 sport museum，体育馆巨型演出现场母语者叫："),
            ("b", "A massive live concert in an indoor arena."),
            ("a", "氛围超现实震撼叫 absolutely surreal。第二个，代替 disgusting，悲伤时听欢快歌的违和与刺耳叫："),
            ("b", "A jarring and discordant mismatch."),
            ("a", "第三个，老一代面对物质匮乏，新一代面对情感焦虑与精神内耗："),
            ("b", "Material scarcity versus existential angst."),
            ("a", "这是能让考官眼前一亮的九分级对比。现在进行八秒即时输出，尝试用上 surreal, arena 或者 emotional outlet。"),
            ("a", "Have you ever watched a live show, Bruce?"),
        ],
        "silence_sec": 8.0,
        "part3_lines": [
            ("a", "思维深度完全打通！最后再听一遍核心句，刻进语感。"),
            ("b", "The arena concert was surreal, providing a raw emotional outlet for existential angst."),
        ]
    },
    {
        "id": "track_05",
        "filename": "bruce_track_05_cities_environment_cosmos.mp3",
        "title": "地理水土、城市变迁与浩瀚宇宙",
        "part1_lines": [
            ("a", "Bruce 专属训练专辑第五期：地理水土、生活环境与浩瀚宇宙。"),
            ("a", "你在文本里提到江西上饶小山城、青岛海滨冬天的干燥寒冷水土不服、以及对引力黑洞和外星生命的向往。"),
            ("a", "但在英语输出时，你用了 lived in a hill, didn't get well with Qingdao 以及 tools smell make me dizzy。来听考官提问："),
            ("a", "Where is your hometown, and how do you find living in your current city?"),
            ("a", "听八点五分母语者如何优雅描述你的两座城市与水土适应："),
            ("b", "My hometown is Shangrao, nestled in the scenic, hilly landscapes of Jiangxi, where life moves at a peaceful and relaxed pace. Currently, I'm based in Qingdao, a coastal metropolis in northern China. To be frank, it took me quite a while to acclimatize to the biting cold and dry winter air here, which was a sharp contrast to the humid south. But I love taking evening strolls in seaside parks just to decompress and indulge in people-watching."),
            ("a", "注意刚才极具画面感的三个高分语块：第一个，代替 lived in a hill，依山傍水的小城叫："),
            ("b", "Nestled in the hilly landscapes."),
            ("a", "第二个，代替 didn't get well with city，适应寒冷水土叫："),
            ("b", "Acclimatize to the biting cold."),
            ("a", "第三个，在公园看人间烟火与过往行人叫："),
            ("b", "Indulge in people-watching."),
            ("a", "提到父亲车里刺鼻的机油和粉尘味，可以讲：pungent motor grease and dust。聊到太空旅行价格太贵，可以讲：prohibitive expenses。"),
            ("a", "现在进入输出挑战。考官马上问你家乡与现住城市，八秒内张嘴用上 acclimatize 或 hilly landscapes！"),
            ("a", "Where is your hometown, and how do you like your current city?"),
        ],
        "silence_sec": 8.0,
        "part3_lines": [
            ("a", "恭喜你完成全套五部专辑的神经回路闭环！最后听一遍核心句。"),
            ("b", "My hometown is nestled in hilly landscapes, and I have gradually acclimatized to Qingdao's coastal climate."),
        ]
    }
]


def generate_suite():
    settings = load_settings()
    print("=" * 60)
    print("开始生成 Bruce 雅思 41 题全量定制 5 大主题音频套件...")
    print(f"输出目录: {OUTPUT_DIR.resolve()}")
    print("=" * 60)

    beep_start = make_beep(freq=660, duration=0.25)
    beep_end = make_beep(freq=880, duration=0.25)

    manifest = []

    for idx, cfg in enumerate(TRACKS_CONFIG, 1):
        track_id = cfg["id"]
        out_name = cfg["filename"]
        title = cfg["title"]
        out_file = OUTPUT_DIR / out_name

        if out_file.exists() and probe_duration(out_file) > 10.0:
            dur = probe_duration(out_file)
            print(f"\n[{idx}/5] {title} ({out_name}) 已存在，跳过重新合成 (时长: {dur:.1f}s)")
            manifest.append({
                "track_id": track_id,
                "filename": out_name,
                "title": title,
                "duration": dur,
                "path": str(out_file)
            })
            continue

        print(f"\n[{idx}/5] 正在生成: {title} ({out_name})...")

        # 合成 Part 1
        print("  - 合成 Part 1 (痛点剖析 + 示范 + 语块精讲 + 考官提问)...")
        part1_bytes = fish_tts_dialogue(cfg["part1_lines"], settings)
        part1_tmp = TMP_DIR / f"{track_id}_p1_{uuid.uuid4().hex[:6]}.mp3"
        part1_tmp.write_bytes(part1_bytes)

        # 合成 Part 3
        print("  - 合成 Part 3 (复盘鼓励 + 核心答句肌肉固化)...")
        part3_bytes = fish_tts_dialogue(cfg["part3_lines"], settings)
        part3_tmp = TMP_DIR / f"{track_id}_p3_{uuid.uuid4().hex[:6]}.mp3"
        part3_tmp.write_bytes(part3_bytes)

        # 静音留白
        silence = make_silence(cfg.get("silence_sec", 8.0))

        concat_list = [
            part1_tmp,
            beep_start,
            silence,
            beep_end,
            part3_tmp,
        ]

        list_file = TMP_DIR / f"concat_{track_id}_{uuid.uuid4().hex[:6]}.txt"
        lines = [_concat_line(p) for p in concat_list]
        list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

        print("  - 拼接并进行 -16 LUFS 广播级母带处理...")
        _run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(list_file),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "44100", "-ac", "1", "-b:a", "128k",
            str(out_file)
        ])

        # 清理临时文件
        part1_tmp.unlink(missing_ok=True)
        part3_tmp.unlink(missing_ok=True)
        list_file.unlink(missing_ok=True)

        dur = probe_duration(out_file)
        print(f"  [OK] {title} 生成成功！时长: {dur:.1f} 秒")
        manifest.append({
            "track_id": track_id,
            "filename": out_name,
            "title": title,
            "duration": dur,
            "path": str(out_file)
        })

    print("\n" + "=" * 60)
    print("5 大主题定制音频套件全部生成完毕！")
    for m in manifest:
        print(f"  * {m['title']} | {m['filename']} ({m['duration']:.1f}s)")
    print("=" * 60)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    generate_suite()

