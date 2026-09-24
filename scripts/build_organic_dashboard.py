"""生成 Bruce 专属纯享沉浸式漫谈播客工作台与随行本 (Organic Flow Dashboard).

彻底摒弃任何考试、纠错、红绿叉与测验，回归生活对话的真实魅力。
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = BASE_DIR / "bruce_study_suite" / "index.html"
STUDY_GUIDE_FILE = BASE_DIR / "bruce_study_suite" / "STUDY_GUIDE.md"

EPISODES = [
    {
        "id": 1,
        "title": "Episode 01: The Midnight Beam & Playground Physics",
        "title_zh": "深夜光束与操场物理学",
        "audio_src": "audio/bruce_track_01_objects_and_senses.mp3",
        "image_src": "images/cinematic_01_cosmic_beam.jpg",
        "quote": "Shining photons into the infinite void — childhood curiosity.",
        "quote_zh": "把光子射入浩瀚虚空——那份未受污染的童真好奇。",
        "dialogue": [
            {"speaker": "Sarah", "text": "Hey Ethan, were you one of those nerdy kids who was totally obsessed with hands-on science experiments back in primary school?", "zh": "嘿 Ethan，你小时候也是那种小学时对动手做科学小实验着迷的狂热极客小孩吗？"},
            {"speaker": "Ethan", "text": "Oh, hundred percent! I still remember taking a magnifying glass out into the backyard at noon, angling it just right to focus intense sunlight onto a dry piece of scrap paper until it started smoldering and caught fire.", "zh": "哈哈绝对是！我到现在都记得，大中午拿着放大镜跑到后院，找准角度把强烈的阳光死死聚焦在一张干燥废纸上，直到它开始冒青烟然后猛然起火！"},
            {"speaker": "Sarah", "text": "Classic! We all tried that! Or taking a ridiculously powerful flashlight beam and pointing it straight up into the pitch-black night sky, wondering how far those photons could actually travel across deep space.", "zh": "太经典了！大家小时候绝对都试过！还有拿一支亮得离谱的强光手电筒，把笔直的光束直接射向漆黑的夜空，一边看一边发呆：这些光子到底能在深空里飞多远？"},
            {"speaker": "Ethan", "text": "Right? Like, are those photons gonna reach some alien civilization millions of light-years away? It's just pure, intuitive childhood curiosity. Same with natural wonders like the Dead Sea—the idea that the saline density is so high that you can literally float on the surface without sinking.", "zh": "对吧！心里总在想：这些光子会不会穿越几百万光年打到某个外星文明脸上？那就是最纯粹、直觉式的童年好奇。就像死海的神奇现象一样——盐度高到你整个人能完全浮在水面上，根本沉不下去。"},
            {"speaker": "Sarah", "text": "Speaking of physical objects, have you ever noticed how luxury wristwatches aren't even about telling time anymore? For wealthy collectors, a rare mechanical watch is basically a portable store of value.", "zh": "聊到具象物件，你有没有发现，高档手表现在根本不是拿来看时间的。对很多富豪藏家来说，一块稀有的机械表本质上是一笔高密度的随身便携避险资产。"},
            {"speaker": "Ethan", "text": "Exactly. It's a conspicuous status symbol, sure, but in extreme emergencies, it acts as concentrated liquidity you can literally wear on your wrist.", "zh": "太精辟了。它表面上是显赫的身份象征，但在极端危机时刻，它就是你戴在手腕上的高浓度流动性资金，随时能变现跑路。"},
            {"speaker": "Sarah", "text": "Totally. And then you have modern smartwatches where people just obsess over tracking their biometric data—like exactly how many calories they burned during an intense gym workout.", "zh": "没错！而另一边是现代智能手表，大家疯狂执念于追踪自己的生理体征数据——比如今天在健身房挥汗如雨到底精准烧了多少卡路里。"},
            {"speaker": "Ethan", "text": "It's wild how our relationship with simple tools has completely transformed over the years.", "zh": "想想真的很妙，这些年我们跟日常身边小工具之间的关系，竟然发生了这么大的蜕变。"}
        ],
        "chunks": [
            {"phrase": "focus intense sunlight onto scrap paper", "meaning": "将强烈阳光聚焦到废纸上"},
            {"phrase": "pointing a flashlight beam into the pitch-black sky", "meaning": "把手电筒光束笔直射向漆黑夜空"},
            {"phrase": "photons traveling across deep space", "meaning": "穿越深空宇宙飞行的光子"},
            {"phrase": "a portable store of value", "meaning": "高密度便携储值资产（富豪随身避险储备）"},
            {"phrase": "conspicuous status symbol", "meaning": "惹人瞩目的显赫身份象征"},
            {"phrase": "track biometric data and calories burned", "meaning": "监测身体生理体征与消耗的卡路里"}
        ]
    },
    {
        "id": 2,
        "title": "Episode 02: The 5 A.M. Stillness & The Vibe Coding Revolution",
        "title_zh": "清晨五点的掌控感与氛围感编程",
        "audio_src": "audio/bruce_track_02_tech_ambition_agency.mp3",
        "image_src": "images/cinematic_02_five_am_agency.jpg",
        "quote": "A profound sense of agency in the quiet dawn.",
        "quote_zh": "在全世界尚未苏醒的清晨，感受属于自我的绝对主导权。",
        "dialogue": [
            {"speaker": "Sarah", "text": "Ethan, are you a night owl or an early bird when you really need to get deep work done?", "zh": "Ethan，当你真想全身心投入深度工作时，你是熬夜修仙的夜猫子，还是天不亮就起的早鸟？"},
            {"speaker": "Ethan", "text": "Definitely an early bird. There is an unmatched, serene stillness around 5 a.m. before the rest of the world wakes up. Diving into challenging tasks at dawn gives me this profound sense of agency and proactive discipline that sets the tone for the entire day.", "zh": "绝对是早起党。早上五点那种全世界还在沉睡的静谧感是无可替代的。在破晓时刻一头扎进硬核任务，会给我一种强烈的自我主导权与自律掌控感，直接为全天的精神惯性定下基调。"},
            {"speaker": "Sarah", "text": "I know that feeling. Zero distractions, no incoming notifications—just pure cognitive clarity. And speaking of deep work, have you played around with vibe coding lately?", "zh": "我太懂那种感觉了。没有任何打扰，没有弹窗消息——只有纯粹清晰的认知空间。说到深度创造，你最近试过 Vibe coding 吗？"},
            {"speaker": "Ethan", "text": "Oh, it's completely revolutionary. Leveraging large language models using natural language prompts allows you to architect functional software without getting bogged down by tedious boilerplate code.", "zh": "天呐，那完全是一场革命。你直接用日常的自然语言提示词去调动大模型，就能迅速架构起能跑的完整软件，根本不需要被枯燥冗余的模板代码拖慢脚步。"},
            {"speaker": "Sarah", "text": "It makes AI feel like a non-negotiable imperative rather than just a trendy gimmick. Anyone with an idea can build real apps now.", "zh": "这让 AI 变成了不可逆转的时代刚需，而不再只是噱头。现在任何脑子里有想法的人，都能直接做出一款真正的产品。"},
            {"speaker": "Ethan", "text": "Precisely. And that's why so many young builders are rejecting the mundane nine-to-five corporate grind. People crave financial autonomy. They'd much rather pursue entrepreneurial ventures where their rewards are tied to creating tangible value.", "zh": "一点没错。这就是为什么现在的年轻人越来越反感在体制化大厂里做毫无意义的螺丝钉。大家渴望的是真正的财务自主，宁愿去尝试能够创造真实价值的独立商业探索。"},
            {"speaker": "Sarah", "text": "It reminds me of that first-principles mindset Elon Musk always talks about—stripping a problem down to its fundamental truths and building something audacious from the ground up.", "zh": "这就像马斯克常说的第一性原理——把问题剥离到最底层的物理本质，然后以惊人的胆魄从零搭建起天马行空的高楼。"},
            {"speaker": "Ethan", "text": "When you combine that kind of ambition with modern AI leverage, the possibilities are genuinely limitless.", "zh": "当这样的野心遇上如今强大的 AI 杠杆，未来真的没有任何天花板。"}
        ],
        "chunks": [
            {"phrase": "unmatched, serene stillness around 5 a.m.", "meaning": "清晨五点无可替代的万籁俱寂"},
            {"phrase": "profound sense of agency and proactive discipline", "meaning": "强烈的自我主导权与积极主动的自律惯性"},
            {"phrase": "vibe coding with natural language prompts", "meaning": "用纯英文自然语言指令进行氛围感开发"},
            {"phrase": "without getting bogged down by boilerplate code", "meaning": "不被枯燥死板的模板代码泥潭拖累"},
            {"phrase": "a non-negotiable imperative", "meaning": "不可妥协退让的时代必然要求"},
            {"phrase": "crave financial autonomy over corporate servitude", "meaning": "渴望财务自由与自主，拒绝大厂螺丝钉奴役"}
        ]
    },
    {
        "id": 3,
        "title": "Episode 03: Mothers, Clutter & The Scroll Trap",
        "title_zh": "母亲的偏爱、杂乱房间与刷屏陷阱",
        "audio_src": "audio/bruce_track_03_habits_family_psychology.mp3",
        "image_src": "images/cinematic_03_warmth_and_fabric.jpg",
        "quote": "Craving tactile warmth in a digital world.",
        "quote_zh": "在被冰冷像素包围的数字世界里，渴望指尖触摸真实的温度。",
        "dialogue": [
            {"speaker": "Sarah", "text": "Be honest with me, Ethan—was your childhood bedroom neat and tidy, or was it an absolute disaster zone?", "zh": "老实交代，Ethan——你小时候的卧室是干干净净，还是一整个灾难现场？"},
            {"speaker": "Ethan", "text": "Total chaotic disaster, without a doubt! My room was in perpetual disarray, and my mom would constantly lecture me about picking up after myself.", "zh": "毫无悬念，纯纯的混乱灾难！房间永远乱成一团，我妈每天追在屁股后面唠叨教育我，让我赶紧自己把东西收好。"},
            {"speaker": "Sarah", "text": "Did she ever give in and clean it up for you, though?", "zh": "那她最后有没有心软，还是忍不住替你收拾了？"},
            {"speaker": "Ethan", "text": "Oh, all the time! She definitely had a soft spot for me. She coddled me a bit, so she always ended up tidying the clutter herself while shaking her head.", "zh": "哈哈每次都是！她对我就是心太软。她打心底里宠溺我，所以每次叹着气摇着头念叨两句，最后还是忍不住亲手把杂物收拾得整整齐齐。"},
            {"speaker": "Sarah", "text": "Moms are the sweetest. But fast forward to our generation today, and our clutter is mostly digital. Everyone is virtually glued to their screens, scrolling endlessly through viral feeds.", "zh": "全天下妈妈都这么暖。但换到我们今天这一代人，我们的混乱大多转移到了数字世界。每个人都被屏幕死死吸住，没完没了地刷着算法推荐的信息流。"},
            {"speaker": "Ethan", "text": "It's frightening. People genuinely cannot tear themselves away from their phones. We're trapped in this algorithmic loop craving instant digital validation.", "zh": "仔细想想挺吓人的。大家是真的根本没办法把视线从手机上移开。我们被困在算法闭环里，饥渴地寻求即时的点赞认同感。"},
            {"speaker": "Sarah", "text": "Which is funny, because that's why I still love going to brick-and-mortar stores to shop for clothes. E-commerce is convenient, but you miss out on the tactile feedback—actually feeling the fabric texture and assessing the drape in person.", "zh": "所以讽刺的是，这恰恰是我依然热爱去实体店买衣服的原因。网购确实方便，但你彻底失去了触觉反馈——指尖摩挲面料纹理、在镜子前感受版型垂坠感的真实快乐。"},
            {"speaker": "Ethan", "text": "So true! Plus, endless online catalogs trigger serious decision fatigue and buyer's remorse. Sticking to a minimalist capsule wardrobe of comfortable essentials makes life infinitely simpler.", "zh": "太认同了！而且网上翻不完的商品目录只会引发严重的决策疲劳和买后后悔。保留一个由百搭舒适单品组成的极简胶囊衣橱，生活真的会轻松一万倍。"}
        ],
        "chunks": [
            {"phrase": "my room was in perpetual disarray", "meaning": "我的卧室永远乱作一团"},
            {"phrase": "she had a soft spot for me and coddled me", "meaning": "她（母亲）对我心太软，忍不住宠溺呵护我"},
            {"phrase": "she ended up tidying the clutter herself", "meaning": "她最后还是自己动手把杂物收拾干净"},
            {"phrase": "virtually glued to our screens", "meaning": "整个人几乎被手机屏幕死死吸住"},
            {"phrase": "cannot tear ourselves away from feeds", "meaning": "根本无法自拔、视线离不开信息流"},
            {"phrase": "tactile feedback of feeling the fabric drape", "meaning": "抚摸布料自然垂坠感带来的真实触觉反馈"},
            {"phrase": "decision fatigue and buyer's remorse", "meaning": "挑选过度带来的决策疲惫与买后懊恼"}
        ]
    },
    {
        "id": 4,
        "title": "Episode 04: Heartbreak Acoustics & The Arena Rush",
        "title_zh": "悲伤声学与万人体育馆的狂热",
        "audio_src": "audio/bruce_track_04_art_humor_generations.mp3",
        "image_src": "images/cinematic_04_arena_reverberation.jpg",
        "quote": "Twenty thousand voices, one surreal resonance.",
        "quote_zh": "两万道声音异口同声，汇聚成穿透身体的超现实共振。",
        "dialogue": [
            {"speaker": "Sarah", "text": "Ethan, what's your take on music and mood? When you're having a rough day, do you listen to upbeat happy tracks to cheer yourself up?", "zh": "Ethan，你觉得音乐和心情是什么关系？当你心情低落透顶时，你会听欢快洗脑的口水歌来让自己开心起来吗？"},
            {"speaker": "Ethan", "text": "Never! In fact, when I'm melancholic, listening to cheerful pop feels incredibly jarring and discordant. It almost insults your grief. I need contemplative, somber acoustics that are strictly mood-congruent to process my sorrow.", "zh": "绝不！事实上当我很丧的时候，强行听欢快流行歌只觉得刺耳、违和到了极点。那感觉就像在侮辱你的悲伤。我需要沉静、略带感伤的原声民谣，必须严格与情绪心境契合，我才能安静地去消化痛苦。"},
            {"speaker": "Sarah", "text": "I'm the exact same way. Music has to match where your head is at. But on the flip side, there's nothing quite like the collective euphoria of a massive live concert in an indoor arena.", "zh": "我也是一模一样。音乐必须懂你当下的脑回路。但反过来看，人生最爽的体验之一，莫过于在巨型室内体育馆万人现场感受那种集体狂喜！"},
            {"speaker": "Ethan", "text": "Oh, being in an arena with twenty thousand fans screaming the lyrics in unison is an electrifying, surreal sensory overload. The bass reverberating through your chest—it gives you full-body chills.", "zh": "天呐，在万人场馆里跟两万名狂热歌迷齐声大声嘶吼副歌，那种触电般的、超现实的感官过载……低音贝斯顺着地板直接轰击胸膛，整个人头皮发麻、浑身起鸡皮疙瘩！"},
            {"speaker": "Sarah", "text": "It's all about finding an authentic emotional outlet. Think about why hip-hop has blown up among young people globally, including across China. It's raw street poetry where people articulate real frustrations.", "zh": "说到底，都是在找一个真实的情感宣泄出口。想想为什么嘻哈说唱会在全球年轻人中包括在中国彻底爆火，因为它就是最接地气的粗粝街头诗歌，让人能毫无修饰地倾诉内心的真实郁闷。"},
            {"speaker": "Ethan", "text": "Exactly. While older generations grappled with material scarcity and focused on basic survival, our generation is wrestling with existential angst, burnout, and emotional isolation.", "zh": "太对了。老一辈人经历过匮乏年代，他们一辈子在与物质短缺搏斗，重心全在求生存上；而我们这一代人衣食无忧，却每天都在跟存在主义虚无、内卷倦怠与精神孤独互搏。"},
            {"speaker": "Sarah", "text": "And whether it's through witty slapstick comedies like Stephen Chow's films or introspective rap lyrics, humor and music give us the emotional fortitude to weather life's storms.", "zh": "所以不管是周星驰电影里那种带着讽刺底色的小人物无厘头喜剧，还是直击灵魂的深刻说唱，幽默与音乐赋予了我们扛过生活暴风雨的心灵力量。"},
            {"speaker": "Ethan", "text": "Couldn't have said it better myself.", "zh": "说得太棒了，简直说到心坎里。"}
        ],
        "chunks": [
            {"phrase": "incredibly jarring and discordant mismatch", "meaning": "极其刺耳割裂、格格不入的违和感"},
            {"phrase": "strictly mood-congruent to process sorrow", "meaning": "严格与心境契合以消化内心的悲伤"},
            {"phrase": "a massive live concert in an indoor arena", "meaning": "在巨型室内万人体育场举办的巡回演唱会"},
            {"phrase": "screaming lyrics in unison", "meaning": "全场观众异口同声齐声高歌"},
            {"phrase": "electrifying, surreal sensory overload", "meaning": "触电般、近乎超现实的强烈感官震撼"},
            {"phrase": "material scarcity versus existential angst", "meaning": "物质匮乏求生 vs 精神存在主义焦虑"},
            {"phrase": "emotional fortitude to weather life's storms", "meaning": "顶住生活风浪的心灵韧性与从容沉淀"}
        ]
    },
    {
        "id": 5,
        "title": "Episode 05: Southern Hills, Biting Winds & Space Dreams",
        "title_zh": "山野故土、北方海风与星际狂想",
        "audio_src": "audio/bruce_track_05_cities_environment_cosmos.mp3",
        "image_src": "images/cinematic_05_hills_and_tides.jpg",
        "quote": "From southern green hills to northern coastal winds.",
        "quote_zh": "从南方苍翠连绵的丘陵茶山，走向北方迎风拍浪的冷冽港湾。",
        "dialogue": [
            {"speaker": "Sarah", "text": "Ethan, you've moved around quite a bit. How do you deal with adjusting to a completely new climate?", "zh": "Ethan，你这几年走南闯北搬过不少地方。遇到一个气候完全颠覆的新城市，你是怎么适应的？"},
            {"speaker": "Ethan", "text": "It can be a brutal shock to the system! Imagine moving from a tranquil hometown nestled in the lush, verdant hills of the south, where life has a gentle pastoral rhythm, straight to a northern coastal city like Qingdao.", "zh": "那真的会对整个生理机能带来巨大震动！想象一下，你前二十年一直生活在南方连绵青翠、绿树成荫的宁静山城，享受着悠闲的田园慢生活；结果突然一头扎进像青岛这样的北方海滨城市！"},
            {"speaker": "Sarah", "text": "Oof, the biting coastal winds and harsh, arid winter chill must have been tough to acclimatize to.", "zh": "天呐，冬天刮在脸上像刀割一样的干冷海风，水土不服真的很难熬吧！"},
            {"speaker": "Ethan", "text": "It took me months to adapt! But once you settle in, coastal cities have this incredible charm. Taking evening strolls along seaside promenades, breathing in the fresh air, and just indulging in people-watching—it's the ultimate urban sanctuary.", "zh": "我花了好几个月才慢慢适应过来！但当你真正安顿下来，海滨城市有一种难以抗拒的魔力。黄昏沿着海滨栈道散步，吹着海风，看着过往散步的形形色色的人间烟火，那真是最治愈的心灵绿洲。"},
            {"speaker": "Sarah", "text": "It really is. Stepping outside gives you that much-needed sense of perspective. It makes you realize how vast the world is, from the depths of black holes in astrophysics to civilian space travel.", "zh": "真的。只要走出门，广阔的天地就会给你一种珍贵的超脱视角。你会突然意识到宇宙有多浩瀚——从天体物理里黑洞的引力坍缩，到未来的民用商业太空旅行。"},
            {"speaker": "Ethan", "text": "Speaking of space, would you ever board a commercial rocket to orbit Earth if you had the chance? ", "zh": "说到太空，要是有机会，你真的敢坐上商业火箭去绕着地球轨道飞一圈吗？"},
            {"speaker": "Sarah", "text": "In a heartbeat! Even though suborbital flights currently carry astronomical and cost-prohibitive price tags, beholding our pale blue dot suspended against the black void would be a life-altering epiphany.", "zh": "毫不犹豫！虽然现在的亚轨道旅行开销是天文数字、贵得让人望而却步，但只要能亲眼看到我们那颗悬挂在虚无黑暗中的暗淡蓝点，绝对是能彻底重塑人生的终极顿悟体验。"},
            {"speaker": "Ethan", "text": "An absolute once-in-a-lifetime journey. From our quiet hometown roots all the way to the cosmos.", "zh": "绝对是一生难逢的旅程。从我们最初宁静温存的山城故土，一路延伸到浩瀚无垠的星空。"}
        ],
        "chunks": [
            {"phrase": "nestled in lush, verdant hills", "meaning": "依偎在南方连绵苍翠的山峦怀抱中"},
            {"phrase": "gentle pastoral rhythm", "meaning": "舒缓宁静的田园生活节奏"},
            {"phrase": "struggle to acclimatize to biting coastal winds", "meaning": "极力去克服适应刺骨凛冽的海风"},
            {"phrase": "indulging in people-watching along the promenade", "meaning": "在海滨栈道漫步、悠闲观察人间百态烟火"},
            {"phrase": "ultimate urban sanctuary", "meaning": "治愈内耗的终极都市心灵避风港"},
            {"phrase": "astronomical and cost-prohibitive price tags", "meaning": "天文数字般昂贵得让人望而却步的开销"},
            {"phrase": "beholding our pale blue dot against the black void", "meaning": "在无尽虚空中亲眼注视那颗孤悬的暗淡蓝点"},
            {"phrase": "a life-altering epiphany", "meaning": "一次改变人生世界观的精神顿悟"}
        ]
    }
]

HTML_CONTENT = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Organic Stream · Bruce 纯享漫谈播客生活馆</title>
    <style>
        :root {
            --bg-body: #0b0f17;
            --bg-surface: #141b26;
            --bg-elevated: #1d2636;
            --border-subtle: rgba(255, 255, 255, 0.08);
            --border-accent: rgba(245, 158, 11, 0.3);
            --text-title: #f8fafc;
            --text-body: #cbd5e1;
            --text-muted: #64748b;
            --accent-warm: #f59e0b;
            --accent-blue: #38bdf8;
            --accent-green: #34d399;
        }

        [data-theme="light"] {
            --bg-body: #f8fafc;
            --bg-surface: #ffffff;
            --bg-elevated: #f1f5f9;
            --border-subtle: rgba(0, 0, 0, 0.08);
            --border-accent: rgba(217, 119, 6, 0.3);
            --text-title: #0f172a;
            --text-body: #334155;
            --text-muted: #94a3b8;
            --accent-warm: #d97706;
            --accent-blue: #0284c7;
            --accent-green: #059669;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
        }

        body {
            background-color: var(--bg-body);
            color: var(--text-body);
            line-height: 1.7;
            padding-bottom: 100px;
            transition: background 0.3s ease, color 0.3s ease;
        }

        header {
            padding: 40px 24px 20px;
            max-width: 1080px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            border-bottom: 1px solid var(--border-subtle);
        }

        .hero-badge {
            display: inline-block;
            background: rgba(245, 158, 11, 0.12);
            color: var(--accent-warm);
            border: 1px solid rgba(245, 158, 11, 0.3);
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            letter-spacing: 1px;
            text-transform: uppercase;
            margin-bottom: 10px;
        }

        .hero-title {
            font-size: 32px;
            font-weight: 800;
            color: var(--text-title);
            letter-spacing: -0.8px;
        }

        .hero-subtitle {
            font-size: 15px;
            color: var(--text-muted);
            margin-top: 6px;
            max-width: 680px;
        }

        .theme-toggle-btn {
            background: var(--bg-elevated);
            border: 1px solid var(--border-subtle);
            color: var(--text-title);
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.2s;
        }

        .theme-toggle-btn:hover {
            border-color: var(--accent-warm);
        }

        .container {
            max-width: 1080px;
            margin: 30px auto;
            padding: 0 24px;
        }

        /* 顶部导航专辑栏 */
        .playlist-scroller {
            display: flex;
            gap: 12px;
            overflow-x: auto;
            padding-bottom: 16px;
            margin-bottom: 30px;
            border-bottom: 1px solid var(--border-subtle);
        }

        .playlist-tab {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            color: var(--text-muted);
            padding: 12px 20px;
            border-radius: 12px;
            cursor: pointer;
            white-space: nowrap;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.2s;
            display: flex;
            flex-direction: column;
            gap: 4px;
            text-align: left;
        }

        .playlist-tab .tab-idx {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--accent-warm);
        }

        .playlist-tab.active {
            background: var(--bg-elevated);
            color: var(--text-title);
            border-color: var(--accent-warm);
            box-shadow: 0 4px 15px rgba(245, 158, 11, 0.15);
        }

        /* 核心展示区：左右分栏 */
        .main-stage {
            display: grid;
            grid-template-columns: 380px 1fr;
            gap: 36px;
            align-items: start;
        }

        @media (max-width: 860px) {
            .main-stage {
                grid-template-columns: 1fr;
            }
        }

        /* 左侧视觉与播放器 */
        .stage-left {
            position: sticky;
            top: 30px;
            display: flex;
            flex-direction: column;
            gap: 20px;
        }

        .cinematic-poster {
            width: 100%;
            height: 480px;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: 0 15px 35px rgba(0, 0, 0, 0.35);
            border: 1px solid var(--border-subtle);
            position: relative;
        }

        .cinematic-poster img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
            transition: transform 0.5s ease;
        }

        .cinematic-poster:hover img {
            transform: scale(1.03);
        }

        .poster-overlay {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            padding: 24px 20px 20px;
            background: linear-gradient(to top, rgba(11, 15, 23, 0.95), rgba(11, 15, 23, 0.4) 60%, transparent);
            color: #ffffff;
        }

        .poster-quote {
            font-size: 15px;
            font-weight: 600;
            font-style: italic;
            line-height: 1.4;
            color: #f1f5f9;
        }

        .poster-quote-zh {
            font-size: 13px;
            color: #94a3b8;
            margin-top: 6px;
        }

        /* 随身听播放器 */
        .player-card {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 14px;
            padding: 20px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
        }

        .player-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }

        .player-status {
            font-size: 12px;
            color: var(--accent-green);
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .player-status::before {
            content: "";
            width: 8px;
            height: 8px;
            background: var(--accent-green);
            border-radius: 50%;
            display: inline-block;
            box-shadow: 0 0 8px var(--accent-green);
        }

        audio {
            width: 100%;
            border-radius: 8px;
            outline: none;
        }

        /* 右侧双语随行对话 */
        .stage-right {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            border-radius: 18px;
            padding: 32px 28px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        }

        .episode-header {
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border-subtle);
        }

        .episode-header h2 {
            font-size: 22px;
            font-weight: 800;
            color: var(--text-title);
        }

        .episode-header h3 {
            font-size: 15px;
            color: var(--accent-warm);
            margin-top: 4px;
            font-weight: 500;
        }

        .conversation-flow {
            display: flex;
            flex-direction: column;
            gap: 20px;
            margin-bottom: 30px;
        }

        .dialogue-bubble {
            display: flex;
            flex-direction: column;
            gap: 6px;
            padding: 14px 18px;
            border-radius: 12px;
            background: var(--bg-elevated);
            border-left: 3px solid transparent;
            transition: all 0.2s;
        }

        .dialogue-bubble.sarah {
            border-left-color: var(--accent-blue);
        }

        .dialogue-bubble.ethan {
            border-left-color: var(--accent-warm);
        }

        .dialogue-speaker {
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .dialogue-bubble.sarah .dialogue-speaker {
            color: var(--accent-blue);
        }

        .dialogue-bubble.ethan .dialogue-speaker {
            color: var(--accent-warm);
        }

        .dialogue-en {
            font-size: 15px;
            color: var(--text-title);
            font-weight: 500;
            line-height: 1.6;
        }

        .dialogue-zh {
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 2px;
            line-height: 1.5;
        }

        /* 沉浸式灵魂语块卡片 */
        .chunks-panel {
            background: var(--bg-body);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 20px;
            margin-top: 24px;
        }

        .chunks-panel h4 {
            font-size: 14px;
            font-weight: 700;
            color: var(--accent-warm);
            margin-bottom: 14px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .chunks-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 12px;
        }

        .chunk-card {
            background: var(--bg-surface);
            border: 1px solid var(--border-subtle);
            padding: 10px 14px;
            border-radius: 8px;
        }

        .chunk-phrase {
            font-size: 14px;
            font-weight: 700;
            color: var(--text-title);
        }

        .chunk-meaning {
            font-size: 12px;
            color: var(--text-muted);
            margin-top: 3px;
        }
    </style>
</head>
<body>

    <header>
        <div>
            <span class="hero-badge">Organic Flow Podcast</span>
            <h1 class="hero-title">The Organic Stream</h1>
            <p class="hero-subtitle">没有考试，没有说教，没有打断。两位母语好友，把你的真实想法行云流水般聊出来。让知识在共鸣中自然浸润。</p>
        </div>
        <button class="theme-toggle-btn" onclick="toggleTheme()">🌓 切换明暗</button>
    </header>

    <div class="container">
        <!-- 顶部选择专辑栏 -->
        <div class="playlist-scroller" id="playlistTabs">
            <!-- 动态生成 5 个选项卡 -->
        </div>

        <div class="main-stage">
            <!-- 左侧：视觉海报与随身听播放器 -->
            <div class="stage-left">
                <div class="cinematic-poster">
                    <img id="posterImg" src="" alt="Cinematic Concept">
                    <div class="poster-overlay">
                        <div class="poster-quote" id="posterQuote"></div>
                        <div class="poster-quote-zh" id="posterQuoteZh"></div>
                    </div>
                </div>

                <div class="player-card">
                    <div class="player-header">
                        <span class="player-status">Streaming Quality</span>
                        <span style="font-size: 12px; color: var(--text-muted);">-16 LUFS Stereo</span>
                    </div>
                    <audio id="mainAudio" controls preload="metadata">
                        <source id="audioSource" src="" type="audio/mpeg">
                        您的浏览器不支持音频。
                    </audio>
                </div>
            </div>

            <!-- 右侧：双语闲聊对读与核心语块 -->
            <div class="stage-right">
                <div class="episode-header">
                    <h2 id="epTitle"></h2>
                    <h3 id="epTitleZh"></h3>
                </div>

                <div class="conversation-flow" id="conversationFlow">
                    <!-- 对话气泡 -->
                </div>

                <div class="chunks-panel">
                    <h4>✨ 漫谈中自然流淌出的母语核心语块 (Organic Chunks)</h4>
                    <div class="chunks-grid" id="chunksGrid">
                        <!-- 核心语块卡片 -->
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const EPISODES = """ + json.dumps(EPISODES, ensure_ascii=False) + """;

        let currentIdx = 0;

        function renderPlaylist() {
            const container = document.getElementById('playlistTabs');
            container.innerHTML = EPISODES.map((ep, i) => `
                <div class="playlist-tab ${i === currentIdx ? 'active' : ''}" onclick="switchEpisode(${i})">
                    <span class="tab-idx">Part ${i + 1}</span>
                    <span>${ep.title_zh}</span>
                </div>
            `).join('');
        }

        function switchEpisode(idx) {
            currentIdx = idx;
            renderPlaylist();

            const ep = EPISODES[idx];

            // 更新海报与金句
            document.getElementById('posterImg').src = ep.image_src;
            document.getElementById('posterQuote').innerText = `"${ep.quote}"`;
            document.getElementById('posterQuoteZh').innerText = ep.quote_zh;

            // 更新播放器
            const audio = document.getElementById('mainAudio');
            const source = document.getElementById('audioSource');
            source.src = ep.audio_src;
            audio.load();
            audio.play().catch(() => {});

            // 更新标题
            document.getElementById('epTitle').innerText = ep.title;
            document.getElementById('epTitleZh').innerText = ep.title_zh;

            // 渲染对话流
            const flow = document.getElementById('conversationFlow');
            flow.innerHTML = ep.dialogue.map(d => {
                const speakerClass = d.speaker.toLowerCase();
                return `
                    <div class="dialogue-bubble ${speakerClass}">
                        <div class="dialogue-speaker">${d.speaker}</div>
                        <div class="dialogue-en">${d.text}</div>
                        <div class="dialogue-zh">${d.zh}</div>
                    </div>
                `;
            }).join('');

            // 渲染核心语块
            const chunksDiv = document.getElementById('chunksGrid');
            chunksDiv.innerHTML = ep.chunks.map(c => `
                <div class="chunk-card">
                    <div class="chunk-phrase">🔑 ${c.phrase}</div>
                    <div class="chunk-meaning">${c.meaning}</div>
                </div>
            `).join('');
        }

        function toggleTheme() {
            const current = document.documentElement.getAttribute('data-theme');
            const target = current === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', target);
        }

        // 初始化
        renderPlaylist();
        switchEpisode(0);
    </script>
</body>
</html>
"""

def generate_study_guide_markdown():
    lines = [
        "# The Organic Stream · Bruce 专属生活漫谈双语随行本",
        "",
        "> 本册是纯英文生活漫谈播客的官方双语随行手册。没有任何考试题目，也没有红绿纠错分析。",
        "> 戴上耳机，把它当成一档讲你自己人生故事的精品播客去听。每当听到母语者用丝滑的语言把你脑海中的意图表达出来时，请享受那份由内而外的共鸣与自然流淌。",
        "",
        "---",
        ""
    ]

    for ep in EPISODES:
        lines.append(f"## {ep['title']}（{ep['title_zh']}）")
        lines.append(f"> *{ep['quote']}*  ")
        lines.append(f"> *{ep['quote_zh']}*")
        lines.append("")
        lines.append("### 完整对谈文稿（中英双语对读）")
        lines.append("")
        for d in ep["dialogue"]:
            lines.append(f"**{d['speaker']}**:")
            lines.append(f"> {d['text']}")
            lines.append(f"> *{d['zh']}*")
            lines.append("")
        lines.append("### 漫谈中自然流出的母语核心语块")
        lines.append("")
        for c in ep["chunks"]:
            lines.append(f"- **{c['phrase']}**：{c['meaning']}")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)

def main():
    OUTPUT_FILE.write_text(HTML_CONTENT, encoding="utf-8")
    print(f"Bruce 纯享漫谈播客工作台已生成: {OUTPUT_FILE.resolve()}")

    STUDY_GUIDE_FILE.write_text(generate_study_guide_markdown(), encoding="utf-8")
    print(f"Bruce 纯享漫谈双语随行手册已生成: {STUDY_GUIDE_FILE.resolve()}")

if __name__ == "__main__":
    main()
