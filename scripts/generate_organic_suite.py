"""Bruce 专属沉浸式漫谈播客音频生成脚本 (Organic Conversational Suite).

模式：
- 彻底摒弃说教、纠错与哔哔声小测验
- 模拟真实生活中的精品漫谈播客（如 Radiolab / NPR / Joe Rogan 风格）
- 两位极富磁性与幽默感的母语好友（Ethan & Sarah）
- 围绕 Bruce 真实的经历、奇思妙想与生活体悟展开自然、地道、机智的对话
- 语言 100% 纯母语口语，自然流淌，-16 LUFS 广播级母带
"""
import sys
import uuid
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from server.audio import _run, probe_duration
from server.config import TMP_DIR, load_settings
from server.tts import fish_tts_dialogue

OUTPUT_DIR = BASE_DIR / "bruce_study_suite" / "audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ORGANIC_EPISODES = [
    {
        "id": "episode_01",
        "filename": "bruce_track_01_objects_and_senses.mp3",
        "title": "The Midnight Beam & Playground Physics",
        "dialogue": [
            ("a", "Hey Ethan, were you one of those nerdy kids who was totally obsessed with hands-on science experiments back in primary school?"),
            ("b", "Oh, hundred percent! I still remember taking a magnifying glass out into the backyard at noon, angling it just right to focus intense sunlight onto a dry piece of scrap paper until it started smoldering and caught fire."),
            ("a", "Classic! We all tried that! Or taking a ridiculously powerful flashlight beam and pointing it straight up into the pitch-black night sky, wondering how far those photons could actually travel across deep space."),
            ("b", "Right? Like, are those photons gonna reach some alien civilization millions of light-years away? It's just pure, intuitive childhood curiosity. Same with natural wonders like the Dead Sea—the idea that the saline density is so high that you can literally float on the surface without sinking."),
            ("a", "Speaking of physical objects, have you ever noticed how luxury wristwatches aren't even about telling time anymore? For wealthy collectors, a rare mechanical watch is basically a portable store of value."),
            ("b", "Exactly. It's a conspicuous status symbol, sure, but in extreme emergencies, it acts as concentrated liquidity you can literally wear on your wrist."),
            ("a", "Totally. And then you have modern smartwatches where people just obsess over tracking their biometric data—like exactly how many calories they burned during an intense gym workout."),
            ("b", "It's wild how our relationship with simple tools has completely transformed over the years.")
        ]
    },
    {
        "id": "episode_02",
        "filename": "bruce_track_02_tech_ambition_agency.mp3",
        "title": "The 5 A.M. Stillness & The Vibe Coding Revolution",
        "dialogue": [
            ("a", "Ethan, are you a night owl or an early bird when you really need to get deep work done?"),
            ("b", "Definitely an early bird. There is an unmatched, serene stillness around 5 a.m. before the rest of the world wakes up. Diving into challenging tasks at dawn gives me this profound sense of agency and proactive discipline that sets the tone for the entire day."),
            ("a", "I know that feeling. Zero distractions, no incoming notifications—just pure cognitive clarity. And speaking of deep work, have you played around with vibe coding lately?"),
            ("b", "Oh, it's completely revolutionary. Leveraging large language models using natural language prompts allows you to architect functional software without getting bogged down by tedious boilerplate code."),
            ("a", "It makes AI feel like a non-negotiable imperative rather than just a trendy gimmick. Anyone with an idea can build real apps now."),
            ("b", "Precisely. And that's why so many young builders are rejecting the mundane nine-to-five corporate grind. People crave financial autonomy. They'd much rather pursue entrepreneurial ventures where their rewards are tied to creating tangible value."),
            ("a", "It reminds me of that first-principles mindset Elon Musk always talks about—stripping a problem down to its fundamental truths and building something audacious from the ground up."),
            ("b", "When you combine that kind of ambition with modern AI leverage, the possibilities are genuinely limitless.")
        ]
    },
    {
        "id": "episode_03",
        "filename": "bruce_track_03_habits_family_psychology.mp3",
        "title": "Mothers, Clutter & The Scroll Trap",
        "dialogue": [
            ("a", "Be honest with me, Ethan—was your childhood bedroom neat and tidy, or was it an absolute disaster zone?"),
            ("b", "Total chaotic disaster, without a doubt! My room was in perpetual disarray, and my mom would constantly lecture me about picking up after myself."),
            ("a", "Did she ever give in and clean it up for you, though?"),
            ("b", "Oh, all the time! She definitely had a soft spot for me. She coddled me a bit, so she always ended up tidying the clutter herself while shaking her head."),
            ("a", "Moms are the sweetest. But fast forward to our generation today, and our clutter is mostly digital. Everyone is virtually glued to their screens, scrolling endlessly through viral feeds."),
            ("b", "It's frightening. People genuinely cannot tear themselves away from their phones. We're trapped in this algorithmic loop craving instant digital validation."),
            ("a", "Which is funny, because that's why I still love going to brick-and-mortar stores to shop for clothes. E-commerce is convenient, but you miss out on the tactile feedback—actually feeling the fabric texture and assessing the drape in person."),
            ("b", "So true! Plus, endless online catalogs trigger serious decision fatigue and buyer's remorse. Sticking to a minimalist capsule wardrobe of comfortable essentials makes life infinitely simpler.")
        ]
    },
    {
        "id": "episode_04",
        "filename": "bruce_track_04_art_humor_generations.mp3",
        "title": "Heartbreak Acoustics & The Arena Rush",
        "dialogue": [
            ("a", "Ethan, what's your take on music and mood? When you're having a rough day, do you listen to upbeat happy tracks to cheer yourself up?"),
            ("b", "Never! In fact, when I'm melancholic, listening to cheerful pop feels incredibly jarring and discordant. It almost insults your grief. I need contemplative, somber acoustics that are strictly mood-congruent to process my sorrow."),
            ("a", "I'm the exact same way. Music has to match where your head is at. But on the flip side, there's nothing quite like the collective euphoria of a massive live concert in an indoor arena."),
            ("b", "Oh, being in an arena with twenty thousand fans screaming the lyrics in unison is an electrifying, surreal sensory overload. The bass reverberating through your chest—it gives you full-body chills."),
            ("a", "It's all about finding an authentic emotional outlet. Think about why hip-hop has blown up among young people globally, including across China. It's raw street poetry where people articulate real frustrations."),
            ("b", "Exactly. While older generations grappled with material scarcity and focused on basic survival, our generation is wrestling with existential angst, burnout, and emotional isolation."),
            ("a", "And whether it's through witty slapstick comedies like Stephen Chow's films or introspective rap lyrics, humor and music give us the emotional fortitude to weather life's storms."),
            ("b", "Couldn't have said it better myself.")
        ]
    },
    {
        "id": "episode_05",
        "filename": "bruce_track_05_cities_environment_cosmos.mp3",
        "title": "Southern Hills, Biting Winds & Space Dreams",
        "dialogue": [
            ("a", "Ethan, you've moved around quite a bit. How do you deal with adjusting to a completely new climate?"),
            ("b", "It can be a brutal shock to the system! Imagine moving from a tranquil hometown nestled in the lush, verdant hills of the south, where life has a gentle pastoral rhythm, straight to a northern coastal city like Qingdao."),
            ("a", "Oof, the biting coastal winds and harsh, arid winter chill must have been tough to acclimatize to."),
            ("b", "It took me months to adapt! But once you settle in, coastal cities have this incredible charm. Taking evening strolls along seaside promenades, breathing in the fresh air, and just indulging in people-watching—it's the ultimate urban sanctuary."),
            ("a", "It really is. Stepping outside gives you that much-needed sense of perspective. It makes you realize how vast the world is, from the depths of black holes in astrophysics to civilian space travel."),
            ("b", "Speaking of space, would you ever board a commercial rocket to orbit Earth if you had the chance?"),
            ("a", "In a heartbeat! Even though suborbital flights currently carry astronomical and cost-prohibitive price tags, beholding our pale blue dot suspended against the black void would be a life-altering epiphany."),
            ("b", "An absolute once-in-a-lifetime journey. From our quiet hometown roots all the way to the cosmos.")
        ]
    }
]


def generate_all():
    settings = load_settings()
    print("=" * 60)
    print("正在启动 Bruce 专属沉浸式漫谈播客音频生成系统...")
    print(f"输出目录: {OUTPUT_DIR.resolve()}")
    print("模式: 纯母语生活化自然漫谈 (零说教 / 零测验 / 零突兀打断)")
    print("=" * 60)

    manifest = []

    for idx, ep in enumerate(ORGANIC_EPISODES, 1):
        ep_id = ep["id"]
        out_name = ep["filename"]
        title = ep["title"]
        out_file = OUTPUT_DIR / out_name

        print(f"\n[{idx}/5] 正在合成漫谈播客: {title} ({out_name})...")

        # 使用 Fish TTS 多说话人单次流式合成整段对话（模型具备完整上下文，接话语气最自然）
        raw_bytes = fish_tts_dialogue(ep["dialogue"], settings)
        tmp_raw = TMP_DIR / f"organic_{ep_id}_{uuid.uuid4().hex[:6]}.mp3"
        tmp_raw.write_bytes(raw_bytes)

        # 进行 -16 LUFS 广播级母带响度归一化
        print("  - 执行 -16 LUFS 广播级母带响度优化...")
        _run([
            "ffmpeg", "-y",
            "-i", str(tmp_raw),
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ar", "44100", "-ac", "1", "-b:a", "128k",
            str(out_file)
        ])
        tmp_raw.unlink(missing_ok=True)

        dur = probe_duration(out_file)
        print(f"  [OK] 《{title}》合成完成！时长: {dur:.1f} 秒")
        manifest.append({
            "id": ep_id,
            "filename": out_name,
            "title": title,
            "duration": dur,
            "path": str(out_file)
        })

    print("\n" + "=" * 60)
    print("5 期沉浸式自然漫谈播客全部录制制作完成！")
    for m in manifest:
        print(f"  * {m['title']} | {m['filename']} ({m['duration']:.1f}s)")
    print("=" * 60)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    generate_all()
