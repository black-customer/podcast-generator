"""Bruce 定制学习包的唯一内容源。

内容全部来自 Bruce 自己的三份雅思口语音频转文字稿（11,332 词），
每一条示范句都锚定他真实说过的经历，利用自我参照效应提升记忆留存。
音频、卡片、视频三种产物共用这一份数据，保证内容永不漂移。

量化依据（对三份文稿做的词频统计）：
- "you know" 219 次 = 1.9 次/100 词（母语者 casual 口语约 0.2–0.5）
- "like" 作填充词 156 次
- "stuff / stuff like that / things / and so on" 模糊占位词 54 次
- "however / although / on the other hand / moreover" 让步与推进连接词 ≈ 0 次
- "in my opinion / the way I see it" 观点标记 0 次，"I think" 125 次
- 平均小句 15.1 词，最长 87 词（run-on 结构）
"""
# ruff: noqa: E501  # 语料与 HTML 模板是数据，折行会让内容不可核对


from __future__ import annotations

# ---------------------------------------------------------------- 训练剂量参数
# 强制输出窗口：Bruce 的天花板远高于实时地板，所以窗口设计为
# 第一轮 10 秒（建立映射）→ 第二轮 5 秒（压缩到考试节奏）。
WINDOW_FIRST = 10.0
WINDOW_FAST = 5.0
WINDOW_SHADOW = 1.2
GAP_NORMAL = 0.45

LEARNER_NAME = "Bruce"

# ---------------------------------------------------------------- 诊断结论
DIAGNOSIS = {
    "estimated_band": "6.0（修订后可达 7.5）",
    "core_finding": (
        "你的问题不是不会，而是知道的东西还没变成张嘴就有的肌肉。"
        "同一个问题你录第二遍时，能说出 \"they were my deliberate choice, not imposed by the school\" "
        "这种 7.5 分的句子——这说明语法和词汇都在仓库里，缺的只是实时检索通道。"
    ),
    "metrics": [
        {"key": "you know", "yours": "219 次 / 1.9 次每百词", "native": "0.2–0.5 次每百词", "note": "填充词挤占了本应用来组织句子的脑力"},
        {"key": "like", "yours": "156 次", "native": "约 20–40 次", "note": "和 you know 叠加后约每 30 词一次卡顿"},
        {"key": "stuff / things / and so on", "yours": "54 次", "native": "母语者会命名类别", "note": "用模糊名词掩盖词检索失败，是 6 分最典型标志"},
        {"key": "however / that said / on the other hand", "yours": "0 次", "native": "Part 3 必备", "note": "没有让步与转折，逻辑层次上不去"},
        {"key": "in my opinion / the way I see it", "yours": "0 次（只有 I think ×125）", "native": "多种观点标记", "note": "考官听不到你切换立场的能力"},
        {"key": "平均小句长度", "yours": "15.1 词，最长 87 词", "native": "口语 8–14 词后收句", "note": "and 叠加 305 次 → 句子不落地"},
    ],
    "strengths": [
        "会自我修正并且愿意重录——这是少数人有的元认知能力，本包全部训练都利用这一点",
        "有真实想法：你主动说出了 choice overload 的现象、\"AI 会像空气一样无处不在\" 这种比喻",
        "已经掌握 double-edged sword、deliberate choice、financial independence 等高阶词块",
        "内容不跑题，愿意给理由——流利度和连贯性的地基是好的",
    ],
    "error_families": [
        "可数/不可数与量词（much/many、a lot of persons、such a huge knowledge）",
        "主谓一致与三单 -s（technology have、these things has、every students）",
        "时态与体（have + 原形、used to using、in 2016 用完成时）",
        "使役与动词框架（suggest sb to do、let me to say、motivate you to thinking）",
        "比较级修饰（very worse、mornings is quiet than）",
        "中式直译（broaden my horizon、high-paid、do a choice、identity symbol、peaceful emotion）",
        "词义反向（get rid of 说成离不开）与形近词（sceneries→situations、organ→senses、controller→steering wheel）",
        "话语层：没有让步/推进连接词，靠 and 与 so 串到底",
    ],
}

# ---------------------------------------------------------------- 十号化石
# your_words 必须是 Bruce 原话（逐字），这是「注意到差异」的原料。
FOSSILS: list[dict] = [
    {
        "id": "01-many-options",
        "label_zh": "可数还是不可数",
        "your_words": "there are too much options",
        "fixed": "There are too many options, so it's hard to know which one to commit to.",
        "core": "There are too many options.",
        "rule_zh": "options、apps、methods、books 都能数，用 many；money、time、information、advice 不能数，用 much。",
        "prompt_zh": "选项太多了，所以很难决定该认真学哪一个。",
        "note_zh": "你在科技话题和学外语话题里各说错一次，同一个坑。",
    },
    {
        "id": "02-tech-has",
        "label_zh": "不可数主语配单数动词",
        "your_words": "technology have changed our life",
        "fixed": "Technology has completely changed the way we learn.",
        "core": "Technology has changed the way we learn.",
        "rule_zh": "technology、information、knowledge、the economy 是单数，配 has / is。反过来 these things 要配 have。",
        "prompt_zh": "科技彻底改变了我们学习的方式。",
        "note_zh": "你还说过 these things here has a higher price，两处刚好是同一个规则的两个方向。",
    },
    {
        "id": "03-used-to-use",
        "label_zh": "used to 后面接什么",
        "your_words": "I used to using the wired headphones",
        "fixed": "I used to use wired headphones, but now I've switched to wireless earphones.",
        "core": "I used to use wired headphones.",
        "rule_zh": "used to + 动词原形（过去常常）；be used to + doing（习惯于）。两个长得一样，意思完全不同。",
        "prompt_zh": "我过去常用有线耳机，但现在已经换成无线耳机了。",
        "note_zh": "同一类错误还有 I like to going to parks——like 后面直接加 doing。",
    },
    {
        "id": "04-have-taught",
        "label_zh": "完成时必须用过去分词",
        "your_words": "all these teachers that have teach me",
        "fixed": "I've got a good memory, so I can still remember every teacher who has taught me.",
        "core": "Every teacher who has taught me.",
        "rule_zh": "have 后面必须是过去分词：have taught / have done / have sung / have seen。你把原形塞进去了四次。",
        "prompt_zh": "我记性很好，所有教过我的老师我都还记得。",
        "note_zh": "同类原话：I haven't do that、I have sing some songs、I haven't know that。",
    },
    {
        "id": "05-in-2016",
        "label_zh": "具体过去时间配一般过去时",
        "your_words": "I have my own smartphone in 2016",
        "fixed": "I got my first smartphone in 2016, just as I was leaving primary school.",
        "core": "I got my first smartphone in 2016.",
        "rule_zh": "句子里出现 in 2016、last year、when I was ten 这类已经关掉的时间点，用一般过去时；现在完成时不能和它们同框。",
        "prompt_zh": "我 2016 年买了第一部智能手机，那时候我刚要小学毕业。",
        "note_zh": "这是 6 分到 7 分最容易丢的一项：时态一致性。",
    },
    {
        "id": "06-recommend-that",
        "label_zh": "suggest 不能接某人去做",
        "your_words": "I suggest everyone to learn a foreign language",
        "fixed": "I'd recommend that everyone learn a second language, but I wouldn't say they have to.",
        "core": "I'd recommend that everyone learn a second language.",
        "rule_zh": "suggest / recommend 后面不接 sb to do。三种安全写法：recommend that sb do、recommend + doing、advise sb to do。",
        "prompt_zh": "我建议每个人都学一门第二语言，但我不觉得他们非学不可。",
        "note_zh": "注意后半句的让步，正是你 Part 3 最缺的那个动作。",
    },
    {
        "id": "07-much-quieter",
        "label_zh": "比较级前不用 very",
        "your_words": "mornings is very quiet than afternoon",
        "fixed": "Mornings are much quieter than afternoons, but I sleep through most of them.",
        "core": "Mornings are much quieter than afternoons.",
        "rule_zh": "比较级前用 much / far / a bit，绝不用 very；quiet 的比较级是 quieter。还有 you said it's very worse——只能说 much worse。",
        "prompt_zh": "早晨比下午安静得多，可惜我几乎每次都睡过去了。",
        "note_zh": "原话里还有 it's very bad / it's very worse，同一族错误。",
    },
    {
        "id": "08-havent-been-in-touch",
        "label_zh": "持续到现在的状态用 for / since",
        "your_words": "It's about like 12 years of before, I didn't attach with them",
        "fixed": "I haven't been in touch with my primary school teachers for about twelve years.",
        "core": "I haven't been in touch for twelve years.",
        "rule_zh": "从过去一直持续到现在，用 haven't been + 状态 + for/since。\"没联系\" 是 be in touch with，不是 attach to。",
        "prompt_zh": "我和小学老师已经大概十二年没联系了。",
        "note_zh": "同类：I'm a lazy person from my child → since I was a kid。",
    },
    {
        "id": "09-uncountable-family",
        "label_zh": "永远不可数的那批词",
        "your_words": "such a huge knowledge, such a huge information",
        "fixed": "There's a huge amount of information on YouTube, and you pick up so much knowledge just by watching.",
        "core": "A huge amount of information.",
        "rule_zh": "knowledge、information、scenery、jewellery、equipment、feedback、progress 不加 s、不接 a/an。要量化就说 a lot of / a huge amount of。",
        "prompt_zh": "YouTube 上有海量信息，光是看着就能学到很多知识。",
        "note_zh": "你还有 many sceneries、some jewelleries 两处，同一族。",
    },
    {
        "id": "10-make-me-say",
        "label_zh": "使役动词后面不带 to",
        "your_words": "if you let me to say, I would say happy music",
        "fixed": "If you forced me to choose, I'd say happy music — but honestly it depends on my mood.",
        "core": "If you forced me to choose, I'd say it depends on my mood.",
        "rule_zh": "let / make / have + 人 + 动词原形（不带 to）；force / allow / encourage / advise + 人 + to do。motivate you to thinking 也错，只能 motivate you to think。",
        "prompt_zh": "如果你逼我选一个，我会说开心的音乐——但说实话，这取决于我当时的心情。",
        "note_zh": "这句话顺手把 emotion→mood 也修好了。",
    },
]

# ---------------------------------------------------------------- 20 个语块
# wrong 是 Bruce 的真实说法（或他的中文思路），example_a 锚定他自己的生活。
CHUNKS: list[dict] = [
    {
        "id": "broaden-horizons",
        "chunk": "broaden my horizons",
        "stress": "broaden my hori-ZONS",
        "ipa": "/hɔːˈraɪzənz/",
        "zh": "打开眼界",
        "wrong": "broaden my horizon（你说了 4 次，永远单数）",
        "example_a": "Learning English has genuinely broadened my horizons — I can watch someone's whole life in another country and recognise it as ordinary.",
        "example_b": "Switching from Bilibili to YouTube broadened my horizons more than any textbook ever did.",
        "usage_zh": "horizons 永远用复数，配 broaden / widen / open。",
        "topics": "travel / study / internet / culture",
    },
    {
        "id": "well-paid-job",
        "chunk": "a well-paid job",
        "stress": "a WELL-PAID job",
        "ipa": "/ˌwel ˈpeɪd/",
        "zh": "薪水高的工作",
        "wrong": "a high-paid job（你说了 2 次）",
        "example_a": "Most people in China assume computer science leads to a well-paid job, and I won't pretend that wasn't part of my reason.",
        "example_b": "I'd trade a well-paid job I hate for a decent salary and work that's actually mine.",
        "usage_zh": "well-paid / high-paying 都对；high-paid 不存在。名词形式是 good pay, decent salary。",
        "topics": "work / study / future plans",
    },
    {
        "id": "make-a-choice",
        "chunk": "make a choice",
        "stress": "MAKE a CHOICE",
        "ipa": "/tʃɔɪs/",
        "zh": "做一个选择",
        "wrong": "do the same choice（你的原话）",
        "example_a": "A lot of my classmates made exactly the same choice I did and switched to computer science.",
        "example_b": "Once you've made a choice, stop re-litigating it — that's where the regret comes from.",
        "usage_zh": "英语里 choice 搭配 make / take / have，从不搭配 do。同类：make a decision, make an effort, make progress。",
        "topics": "study / shopping / life",
    },
    {
        "id": "status-symbol",
        "chunk": "a status symbol",
        "stress": "a STA-tus SYM-bol",
        "ipa": "/ˈsteɪtəs ˌsɒmbəl/",
        "zh": "身份象征",
        "wrong": "an identity simple（你的原话，考官完全听不懂）",
        "example_a": "Nobody spends ten thousand yuan on a watch to tell the time — it's a status symbol.",
        "example_b": "For my parents' generation a car was a status symbol; for mine it's just a way to avoid the bus.",
        "usage_zh": "symbol 是可数的，a status symbol / a national symbol。identity 指「我是谁」，status 指「别人怎么看我」。",
        "topics": "shopping / watches / money / clothing",
    },
    {
        "id": "sense-of-calm",
        "chunk": "a sense of calm",
        "stress": "a SENSE of CALM",
        "ipa": "/kɑːm/",
        "zh": "一种平静感",
        "wrong": "this peaceful emotion（你的原话）",
        "example_a": "I sit in a park and watch strangers live their lives, and it gives me a sense of calm that video games never gave me.",
        "example_b": "Waking up early gives me a sense of being in control of the day.",
        "usage_zh": "a sense of + 名词：a sense of calm / achievement / humour / direction。emotion 指具体情绪，feelings 指内心感受，mood 指某一时段的心情。",
        "topics": "parks / music / morning / wellbeing",
    },
    {
        "id": "depends-on-my-mood",
        "chunk": "it depends on my mood",
        "stress": "it de-PENDS on my MOOD",
        "ipa": "/muːd/",
        "zh": "看我当时什么心情",
        "wrong": "depends on my emotion（你的原话，说了 7 次 emotion）",
        "example_a": "How much I study really depends on my mood, which isn't exactly a compliment to my self-discipline.",
        "example_b": "In the mornings it depends on my mood; at night I always get something done.",
        "usage_zh": "心情好是 in a good mood，不是 in a good emotion。emotion 是愤怒、恐惧这类具体情绪。",
        "topics": "music / study habits / personality",
    },
    {
        "id": "cant-do-without",
        "chunk": "I can't do without it",
        "stress": "I can't DO withOUT it",
        "ipa": "/wɪˈðaʊt/",
        "zh": "我离不开它",
        "wrong": "people always can get rid of social media（你说反了！get rid of 是戒掉/甩掉）",
        "example_a": "We're Gen Z — we can't do without social media for even a single day.",
        "example_b": "I genuinely couldn't do without headphones on a bus.",
        "usage_zh": "get rid of = 摆脱（想扔的东西）；can't do without = 离不开。方向完全相反，这是全篇最危险的一次口误。",
        "topics": "social media / phones / music",
    },
    {
        "id": "filter-bubble",
        "chunk": "step outside my filter bubble",
        "stress": "step outSIDE my FIL-ter BUB-ble",
        "ipa": "/ˈfɪltə ˌbʌbl/",
        "zh": "跳出信息茧房",
        "wrong": "break the information barriers（你的中式直译）",
        "example_a": "I moved to YouTube to step outside my filter bubble and because I needed real English input, not subtitles.",
        "example_b": "Algorithms keep feeding you what you already like — that's the filter bubble doing its job.",
        "usage_zh": "barrier 是需要拆掉的障碍（语言障碍 language barrier），bubble 是把你包起来的环境。这个表达能直接用在科技、社交媒体、新闻三个话题上。",
        "topics": "technology / social media / news / study",
    },
    {
        "id": "decision-fatigue",
        "chunk": "decision fatigue",
        "stress": "de-CI-sion fa-TIGUE",
        "ipa": "/dɪˈsɪʒn fəˈtiːɡ/",
        "zh": "决策疲劳",
        "wrong": "make our brain have more things to think about（你自己发明的说法，其实很有想法）",
        "example_a": "Comparing fifty learning apps gave me more decision fatigue than actually studying ever did.",
        "example_b": "Having endless options is convenient for my hands and exhausting for my brain — that's decision fatigue.",
        "usage_zh": "你原话里的洞察是 8 分水平的，只是没有一个词能装住它。decision fatigue / choice overload 是一对。",
        "topics": "technology / shopping / study methods",
    },
    {
        "id": "once-in-a-blue-moon",
        "chunk": "once in a blue moon",
        "stress": "once in a BLUE MOON",
        "ipa": "",
        "zh": "极少，难得一次",
        "wrong": "very very seldom（你的原话，seldom 已经是否定含义不能加 very）",
        "example_a": "I go into an actual shop once in a blue moon — everything else I order online without thinking.",
        "example_b": "My dad calls his primary school friends once in a blue moon, and each time he puts the phone down happier.",
        "usage_zh": "频率阶梯：hardly ever < once in a blue moon < now and then < every other day。rarely / seldom 前面不加 very，用 very rarely。",
        "topics": "shopping / habits / friends",
    },
    {
        "id": "in-situations",
        "chunk": "in certain situations",
        "stress": "in CER-tain sit-u-A-tions",
        "ipa": "/sɪˈtjuːeɪʃnz/",
        "zh": "在某些场合",
        "wrong": "in specific sceneries（你说了 9 次 scenery，其中至少 5 次想说「场合」）",
        "example_a": "I keep it casual most of the time, but in certain situations — an interview, for instance — I dress up.",
        "example_b": "In a classroom it's disrespectful to wear headphones; in certain situations you simply don't.",
        "usage_zh": "scenery 只有自然风景这一个意思，且不可数。场合/情形用 situation 或 occasion。这是你出现频率最高的词义错位。",
        "topics": "clothing / headphones / parks / behaviour",
    },
    {
        "id": "other-senses",
        "chunk": "use your other senses",
        "stress": "use your OTH-er SEN-ses",
        "ipa": "/ˈsensɪz/",
        "zh": "调动你其他的感官",
        "wrong": "use your different organ（你的原话，organ 在英语里首先指内脏）",
        "example_a": "In a shop you can use more than your eyes — you touch the fabric, you try it on, you use your other senses.",
        "example_b": "Music works because it hits your senses before it reaches your reasoning.",
        "usage_zh": "感官是 senses（five senses）；organ 是器官/内脏，或者风琴。说 organ 考官会愣一下。",
        "topics": "shopping / music / technology",
    },
    {
        "id": "steering-wheel",
        "chunk": "both hands on the steering wheel",
        "stress": "both HANDS on the STEER-ing WHEEL",
        "ipa": "/ˈstɪərɪŋ wiːl/",
        "zh": "双手握着方向盘",
        "wrong": "put your hands on a controller（你的原话，controller 是游戏手柄）",
        "example_a": "Driving sounds dull to me: both hands on the steering wheel, eyes on the road, for hours, with no way out.",
        "example_b": "I'd rather be a passenger — I can scroll on my phone instead of watching the traffic.",
        "usage_zh": "车上的叫 steering wheel，游戏的是 controller / games controller。顺带修掉 play my phone——英语是 scroll (on) my phone 或 mess about on my phone。",
        "topics": "cars / travel / driving",
    },
    {
        "id": "kick-start-my-day",
        "chunk": "kick-start my day",
        "stress": "KICK-START my DAY",
        "ipa": "",
        "zh": "给一天开个好头",
        "wrong": "help me to begin a happy day（你的原话）",
        "example_a": "I put my earphones in, hit play on something loud, and let it kick-start my day.",
        "example_b": "Getting up before eight kick-starts my day better than any cup of coffee.",
        "usage_zh": "kick-start 比 begin 有画面感，考官会立刻注意到。同类：kick off a project, ease into a routine。",
        "topics": "morning / music / habits / study",
    },
    {
        "id": "resonate-with",
        "chunk": "it really resonates with people",
        "stress": "it RE-al-ly RES-o-nates with PEO-ple",
        "ipa": "/ˈrezəneɪts/",
        "zh": "特别能引起人们共鸣",
        "wrong": "people have the same feelings with you（你的原话）",
        "example_a": "J. Cole resonates with people because he raps about ordinary struggles rather than money he's already got.",
        "example_b": "When a lyric names something you felt but never said, it resonates.",
        "usage_zh": "共鸣 = resonate with sb，或者 it speaks to me。你原来那句是中文语法直译，with 的位置错了。",
        "topics": "music / films / books / people",
    },
    {
        "id": "older-generation",
        "chunk": "the older generation",
        "stress": "the OL-der gen-e-RA-tion",
        "ipa": "/ˌdʒenəˈreɪʃn/",
        "zh": "老一辈",
        "wrong": "the old generation / old people is a general concept（你的原话）",
        "example_a": "The older generation worries about putting food on the table; mine worries about feeling stuck.",
        "example_b": "Older people aren't bad with technology — they just stopped being curious first.",
        "usage_zh": "the old / the young 能指一类人，但谈代际用 the older / the younger generation，避免听起来不礼貌。",
        "topics": "technology / age / family / society",
    },
    {
        "id": "headphone-jack",
        "chunk": "a headphone jack",
        "stress": "a HEAD-phone JACK",
        "ipa": "/dʒæk/",
        "zh": "耳机孔",
        "wrong": "an entrance to wired headphones（你的原话）",
        "example_a": "My new phone doesn't even have a headphone jack, so I had to go wireless.",
        "example_b": "Wired headphones never run out of battery — that's the only reason I miss the jack.",
        "usage_zh": "entrance 是人或车进得的入口；插口是 jack / port / socket。这类小词最能暴露你是否真的用英语生活。",
        "topics": "technology / headphones / phones",
    },
    {
        "id": "burn-calories",
        "chunk": "how many calories I burned",
        "stress": "how MA-ny CAL-o-ries I BURNED",
        "ipa": "/ˈkæləriz/",
        "zh": "我烧掉了多少卡路里",
        "wrong": "what carry I actually spend（你的原话：calories 说成了 carry，spend 应为 burn）",
        "example_a": "I wear a watch to the gym so I can see how many calories I've actually burned — the number is always disappointing.",
        "example_b": "Sitting in traffic doesn't burn calories, it burns patience.",
        "usage_zh": "卡路里搭配 burn，不搭配 spend。calories 尾音 /z/ 必须发出来，否则听起来就是 carry。",
        "topics": "health / sport / watches",
    },
    {
        "id": "theme-park",
        "chunk": "a theme park",
        "stress": "a THEME PARK",
        "ipa": "/θiːm/",
        "zh": "主题乐园",
        "wrong": "the toy land, the toy park（你的原话）",
        "example_a": "As a kid I only wanted a theme park or a screen; a quiet green park bored me to tears.",
        "example_b": "Disneyland is the obvious example of a theme park that people pay to stand in a queue.",
        "usage_zh": "theme 不是 toy。顺带把 you bored me → bored me to tears 这种自然夸张拿走。",
        "topics": "childhood / parks / travel / entertainment",
    },
    {
        "id": "self-discipline",
        "chunk": "it comes down to self-discipline",
        "stress": "it comes DOWN to self-DIS-ci-pline",
        "ipa": "/ˌself ˈdɪsəplɪn/",
        "zh": "归根到底是自律问题",
        "wrong": "how the children self-disciplining ability developed（你的原话）；还有 executive ability",
        "example_a": "Whether a child should own a smartphone comes down to self-discipline, not age.",
        "example_b": "I don't lack a plan, I lack follow-through — that's the whole self-discipline problem for me.",
        "usage_zh": "come down to = 归根到底是，Part 3 万能收口。执行力的英语是 follow-through / discipline，不是 executive ability。",
        "topics": "children / phones / habits / study",
    },
]

# ---------------------------------------------------------------- 模糊名词升级
VAGUE_UPGRADES: list[dict] = [
    {"vague": "the actual things", "better": "physical goods", "zh": "实物商品", "his": "I don't have much craving about the actual things except food"},
    {"vague": "these things here", "better": "day-to-day essentials", "zh": "日常用品", "his": "these things here has a higher price"},
    {"vague": "some interesting thing", "better": "something worth trying", "zh": "值得一试的东西", "his": "I just buy something interesting"},
    {"vague": "the thing that helps me most", "better": "the tool I rely on most", "zh": "我最依赖的工具", "his": "recently the thing that helps me the most is AI"},
    {"vague": "different scenery", "better": "a different setting", "zh": "不同的场合/环境", "his": "sometimes in specific sceneries"},
    {"vague": "many things", "better": "a lot of detail", "zh": "很多细节", "his": "he just think about much things"},
    {"vague": "some stuff", "better": "the relevant material", "zh": "相关材料", "his": "there are lots of material which material should I use"},
]

# ---------------------------------------------------------------- 脚手架
SCAFFOLDS: list[dict] = [
    {
        "name": "Part 3 四步骨架",
        "moves": [
            {"move": "表态", "en": "The way I see it, …", "zh": "换掉你的第 126 个 I think"},
            {"move": "给理由", "en": "… and the main reason is that …", "zh": "一句就够，别叠 because"},
            {"move": "落到自己身上", "en": "Take my own case — …", "zh": "你其实很会举例，只是没标记"},
            {"move": "让步收口", "en": "That said, it depends on the person.", "zh": "你最缺的一步，加上就是 7 分门槛"},
        ],
    },
    {
        "name": "Part 1 三拍",
        "moves": [
            {"move": "直接答", "en": "Not really, to be honest.", "zh": "先给立场，别铺垫"},
            {"move": "一点理由", "en": "mostly because …", "zh": "10–15 词以内"},
            {"move": "一个细节", "en": "— like last week, I …", "zh": "细节是 Part 1 的全部加分点"},
        ],
    },
    {
        "name": "争取时间的高级说法",
        "moves": [
            {"move": "代替 you know", "en": "Well, it's one of those things where …", "zh": "沉默 0.5 秒 + 这个句型，比 you know 高级十倍"},
            {"move": "代替 how to say", "en": "What I'm trying to say is …", "zh": "自我修正时用它，不要 i mean i mean"},
            {"move": "代替 I don't know", "en": "I've never really thought about it, but off the top of my head …", "zh": "Part 3 抽到生题的救命句"},
        ],
    },
]

# ---------------------------------------------------------------- 影子跟读示范
MODELS: list[dict] = [
    {
        "id": "model-habits",
        "title_zh": "Part 1｜你的学习时长（把「我看心情」说到 8 分）",
        "sentences": [
            "Honestly, how much I study depends on my mood, which isn't exactly a compliment to my self-discipline.",
            "Some days I put in four focused hours, and other days I get nothing done at all.",
            "So I'm trying to fix it — I wake up, put my earphones in, and let hip-hop kick-start my day.",
            "The rhythm does something that a to-do list never could.",
        ],
        "focus_zh": "重音落在 depends / mood / four / nothing / fix / kick-START 这些实词上，虚词一带而过。",
    },
    {
        "id": "model-jcole",
        "title_zh": "Part 2｜J. Cole（把你的原答案重做一遍）",
        "sentences": [
            "The creative person I'd pick is J. Cole, who's strictly a rapper rather than a singer.",
            "What I admire most is that he's brutally honest — his lyrics are drawn from his own life.",
            "He grew up with very little, and he never pretends otherwise, which is why he resonates with people.",
            "He gives you something to think about and something to feel at the same time, and that combination is rare.",
        ],
        "focus_zh": "破折号处停一拍，让考官跟上你的转折。brutally / honest / life / resonate 是重音位。",
    },
    {
        "id": "model-tradeoff",
        "title_zh": "Part 3｜科技让生活更轻松还是更累（你那个洞察的正确打开方式）",
        "sentences": [
            "There's a real trade-off here.",
            "Technology has taken the grunt work out of daily life, but it has dumped an overwhelming number of choices on us instead.",
            "Ten years ago you picked one app and got on with it; now you spend an hour comparing fifty of them and study none.",
            "So the tools are sharper, but the thinking behind them has become heavier — that's decision fatigue.",
        ],
        "focus_zh": "分号处停满一拍。最后一句之前留 0.4 秒再放慢说 decision fatigue，这是考官记分的瞬间。",
    },
]

# ---------------------------------------------------------------- 考官快问快答
GAUNTLET: list[dict] = [
    {"part": 1, "q": "Do you like your subjects?", "window": 4, "must_use": "broaden my horizons"},
    {"part": 1, "q": "Why did you choose to study computer science?", "window": 5, "must_use": "a well-paid job"},
    {"part": 1, "q": "Do you prefer studying in the morning or in the afternoon?", "window": 4, "must_use": "kick-start my day"},
    {"part": 1, "q": "How much time do you spend on your studies each week?", "window": 4, "must_use": "depends on my mood"},
    {"part": 1, "q": "What technology do you use when you study?", "window": 4, "must_use": "the tool I rely on most"},
    {"part": 1, "q": "Do you use headphones a lot?", "window": 4, "must_use": "a headphone jack"},
    {"part": 1, "q": "Do you like going to parks?", "window": 4, "must_use": "a sense of calm"},
    {"part": 1, "q": "How often do you go shopping in a real shop?", "window": 4, "must_use": "once in a blue moon"},
    {"part": 1, "q": "Do you wear a watch?", "window": 4, "must_use": "a status symbol"},
    {"part": 1, "q": "Did you enjoy travelling by car as a child?", "window": 4, "must_use": "both hands on the steering wheel"},
    {"part": 3, "q": "Is it difficult for adults to learn a new language?", "window": 7, "must_use": "it comes down to self-discipline"},
    {"part": 3, "q": "Do you think everyone should learn a foreign language?", "window": 7, "must_use": "I'd recommend that everyone learn"},
    {"part": 3, "q": "Has technology made our lives easier or harder?", "window": 7, "must_use": "decision fatigue"},
    {"part": 3, "q": "Do people of different generations listen to different music?", "window": 7, "must_use": "the older generation"},
    {"part": 3, "q": "Does music shape people's identity and culture?", "window": 7, "must_use": "resonates with people"},
    {"part": 3, "q": "Should young people prefer physical shops or online ones?", "window": 7, "must_use": "use your other senses"},
]

# ---------------------------------------------------------------- 训练协议
PROTOCOL: list[dict] = [
    {"day": "第 1–3 天", "task": "只听 01 纠错实验室，10 秒窗口里必须张嘴。别贪，先修 10 个化石。"},
    {"day": "第 4–7 天", "task": "02 语块健身房 + 03 影子跟读。每天把当天语块用在你自己的 Part 1 答案里说一遍，录音。"},
    {"day": "第 8–12 天", "task": "04 考官快问快答。窗口里说不出来就硬憋，憋出来的那半句比听十遍都有用。"},
    {"day": "每天睡前", "task": "05 睡前复习，不张嘴，躺着听。睡眠会替你完成最后一遍编码。"},
    {"day": "第 15 / 21 天", "task": "重录第一次那 10 道题，对比原稿。你要听的不是「我变好了」，是具体哪一句不再卡住。"},
]

IMPLEMENTATION_INTENTIONS: list[dict] = [
    {"when": "早上闹钟响第二次", "then": "不想起就戴上耳机播 03，让音乐替你把身体启动，别靠意志力。"},
    {"when": "坐上去市区的公交", "then": "这段时间只属于 02，你本来就离不开手机，换成它。"},
    {"when": "想说 you know 的时候", "then": "闭嘴半秒。沉默听起来像思考，you know 听起来像慌张。"},
]
