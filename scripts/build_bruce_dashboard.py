"""生成 Bruce 专属 41 题交互式学习工作台 (Standalone HTML).

特性：
- 零外部依赖，纯单文件 HTML/CSS/JS，支持 file:// 本地双击直接打开
- 内置 5 大主题闭环音频播放器（带时间点跳转控制与 8 秒倒计时视觉展示）
- 5 幅高清视觉图谱图片画廊（支持点击大图预览与要点批注）
- 41 道真题全量智能检索与筛选工作台（中式痛点 vs 8.5分重构 vs 灵魂语块）
- 支持浏览器内置 Web Speech API 发音试听
- 适配夜间深色 / 日间浅色主题
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = BASE_DIR / "bruce_study_suite" / "index.html"

# 41 道题目结构化数据
TOPICS_DATA = [
    # 模块 1: 具象物品与生活常识
    {
        "id": 1,
        "module": 1,
        "module_name": "具象物品与生活常识",
        "question": "What kind of interesting things have you done with science?",
        "bruce_raw": "I use, you know, mirror that could manifest something, you know, it's manifest mirror. I use it to concentrate a. Sunlight, concentrate a sunshine, and to try to burn, try to burn a paper.",
        "trap": "词穷造词：把放大镜硬译为 manifest mirror，聚焦阳光错说成 concentrate a sunshine。",
        "native_model": "Back in primary school, I was captivated by hands-on physics experiments. I vividly remember taking a magnifying glass outside to focus intense sunlight onto scrap paper until it actually started smoldering and caught fire.",
        "chunks": [
            {"en": "magnifying glass", "zh": "放大镜（避免自创 manifest mirror）"},
            {"en": "focus intense sunlight onto scrap paper", "zh": "将强烈阳光聚焦到废纸上"},
            {"en": "hands-on physics experiments", "zh": "亲自动手做的物理实验"}
        ]
    },
    {
        "id": 2,
        "module": 1,
        "module_name": "具象物品与生活常识",
        "question": "Do you like science? Why?",
        "bruce_raw": "when you use your fresh, you know, the fresh spot, you just release a fresh, and you use your fresh ball to towards the sky, and where did it go, you know? you know that the fresh is cons- in-is consist of some you know. Some tiny things and when you use a fresh to point to the sky. So where are they go?",
        "trap": "严重词穷车祸：手电筒光束不会说，连续使用 fresh / fresh spot / fresh ball，光子说成 tiny things。",
        "native_model": "Science has always fascinated me because it answers intuitive childhood curiosities. I used to shine a powerful flashlight beam straight up into the pitch-black night sky, wondering how far those photons would travel across the cosmos.",
        "chunks": [
            {"en": "flashlight beam", "zh": "手电筒光束"},
            {"en": "photons traveling across the cosmos", "zh": "穿越宇宙的光子"},
            {"en": "intuitive childhood curiosities", "zh": "童年朴素直觉的好奇心"}
        ]
    },
    {
        "id": 3,
        "module": 1,
        "module_name": "具象物品与生活常识",
        "question": "Do Chinese people often visit science museums?",
        "bruce_raw": "parents they think it can help their children to be smart, I can say help you grow their IQ, and the teachers or school will also lead the students to visit the science museum... maybe can make you more logic",
        "trap": "中式句式堆叠：help you grow their IQ（人称混乱），make you more logic（logic 为名词）。",
        "native_model": "Definitely. Visiting science museums has become a staple weekend activity for Chinese families because modern parents believe hands-on exhibits foster critical thinking and stimulate intellectual curiosity rather than mechanical memorization.",
        "chunks": [
            {"en": "foster critical thinking", "zh": "培养批判性思辨能力"},
            {"en": "stimulate intellectual curiosity", "zh": "激发求知欲与探索欲"},
            {"en": "mechanical memorization", "zh": "机械死记硬背"}
        ]
    },
    {
        "id": 4,
        "module": 1,
        "module_name": "具象物品与生活常识",
        "question": "Why do some people wear expensive watches?",
        "bruce_raw": "maybe it's because it's a identity, you know, identity simple like... some men just buy some expensive watches to show their identity, and I also hear... when something bad happen, they could just carry them easily and run away. It's kind of gold, and much expensive than gold in the same volume.",
        "trap": "观点极其深刻（避险高密度资产），但词汇单薄：identity simple 应为 status symbol，much expensive 语法残缺。",
        "native_model": "Beyond functioning as a conspicuous status symbol, luxury timepieces often serve as a portable store of value. High-net-worth individuals appreciate that an ultra-rare wristwatch concentrates enormous financial liquidity into a compact, easily transportable asset during turbulent times.",
        "chunks": [
            {"en": "conspicuous status symbol", "zh": "显赫醒目的身份象征"},
            {"en": "portable store of value", "zh": "高密度便携储值资产（富人避险逃难资产）"},
            {"en": "concentrate enormous financial liquidity", "zh": "汇聚高流动性资金"}
        ]
    },
    {
        "id": 5,
        "module": 1,
        "module_name": "具象物品与生活常识",
        "question": "Do you wear a watch? What type?",
        "bruce_raw": "Do some mechanical watch or some electricity ones? Just for watching time... but now I wear watch, because the different function... when I do some exercise in gym. I will know what carry I actually spend, although it's not that accurate.",
        "trap": "词汇错位：智能手表说成 electricity ones，消耗卡路里说成 what carry I actually spend。",
        "native_model": "I transitioned from traditional analog watches to a smartwatch. My primary motivation is tracking health metrics—whenever I hit the gym, it monitors my heart rate and calculates the calories burned throughout my workout.",
        "chunks": [
            {"en": "track health metrics", "zh": "追踪生理健康指标"},
            {"en": "calories burned throughout my workout", "zh": "整个锻炼过程中燃烧的卡路里"},
            {"en": "transition from analog to smartwatch", "zh": "从传统机械表过渡到智能手表"}
        ]
    },
    {
        "id": 6,
        "module": 1,
        "module_name": "具象物品与生活常识",
        "question": "What type of headphones do you use?",
        "bruce_raw": "I used to using, I used to use the, you know, the wired headphones. but these days, most phones they just don't have you know have a entrance to wired headphones. so I just used earphone, wireless earphones through the bluetooth...",
        "trap": "词穷借代：把手机耳机孔说成 entrance to wired headphones。",
        "native_model": "I used to be an avid user of wired earphones, but ever since major smartphone brands ditched the 3.5mm headphone jack, I switched to noise-canceling wireless earbuds for their sheer portability.",
        "chunks": [
            {"en": "ditch the 3.5mm headphone jack", "zh": "取消 3.5mm 耳机孔"},
            {"en": "noise-canceling wireless earbuds", "zh": "降噪无线蓝牙耳机"},
            {"en": "sheer portability", "zh": "无可比拟的便携性"}
        ]
    },
    {
        "id": 7,
        "module": 1,
        "module_name": "具象物品与生活常识",
        "question": "In what conditions would you not use headphones?",
        "bruce_raw": "When I can just let this phone's voice out. Like when I'm in a dormitory... Like when you are in a classroom, there are a teacher doing a lecture... then you wear headphones. Very. Disrespectful, I think.",
        "trap": "中式外放直译：let this phone's voice out。",
        "native_model": "I only ever play audio on loudspeaker in private spaces like my dorm room. Wearing earbuds while a university lecturer is speaking in class would be blatantly disrespectful, so I make sure my phone remains on silent.",
        "chunks": [
            {"en": "play audio on loudspeaker", "zh": "手机扬声器外放声音"},
            {"en": "blatantly disrespectful", "zh": "公然不敬、极其冒犯"},
            {"en": "remain on silent mode", "zh": "保持静音状态"}
        ]
    },
    {
        "id": 8,
        "module": 1,
        "module_name": "具象物品与生活常识",
        "question": "Do you like looking at yourself in the mirror? Would you decorate with mirrors?",
        "bruce_raw": "when I put some, you know, cream, facial cream on my face, I need to see that if I, you know, just put them very clearly. It means that he should, shouldn't remain some white thing on my face... would you use mirrors to decorate your room? no, absolutely not... in China, there are a lot of like fengshui... tales that if you put a mirror open in your room, and maybe there are some bad thing just come out... it's very terrified...",
        "trap": "中式硬译：remain some white thing on my face，terrified（误用形容人害怕的词形容事情吓人）。",
        "native_model": "I rarely gaze into mirrors except for functional grooming—like making sure my moisturizer hasn't left any unabsorbed white residue. When it comes to interior decor, I strictly adhere to traditional feng shui conventions; positioning a mirror directly opposite one's bed is said to invite eerie vibes and negative energy.",
        "chunks": [
            {"en": "unabsorbed white residue", "zh": "未吸收的护肤品白茬残留"},
            {"en": "feng shui conventions", "zh": "风水民俗禁忌"},
            {"en": "eerie vibes and negative energy", "zh": "诡异惊悚的氛围与负面气场"}
        ]
    },

    # 模块 2: 科技、职业野心与掌控力
    {
        "id": 9,
        "module": 2,
        "module_name": "科技、职业野心与掌控力",
        "question": "What is your major and what do you study?",
        "bruce_raw": "My major is computer science... like AI-assisted coding, also known as white coding... Vibe coding, V-I-B-E coding. It's a new term. It's just kind of AI-assisted coding... you don't need to just use the compiler language. You just need to use English.",
        "trap": "词汇听读混淆：将 Vibe coding 念成 white coding，compiler language 表达生硬。",
        "native_model": "I'm pursuing a degree in computer science. Lately, I've been fascinated by the emerging paradigm of vibe coding—where engineers harness natural language prompts and generative AI to architect and deploy functional applications without writing tedious boilerplate code.",
        "chunks": [
            {"en": "emerging paradigm of vibe coding", "zh": "Vibe coding 这一新兴开发范式"},
            {"en": "natural language prompts", "zh": "自然语言提示词"},
            {"en": "tedious boilerplate code", "zh": "枯燥繁琐的模板代码"}
        ]
    },
    {
        "id": 10,
        "module": 2,
        "module_name": "科技、职业野心与掌控力",
        "question": "Why did you choose your subject?",
        "bruce_raw": "I was a chemical student when I was a freshman in a university. And then I choose to switch my major. I choose computer science because in Chinese, everybody would think computer science can get a high-paid job than other majors.",
        "trap": "专业词性错误：chemical student（应为 chemistry major），get a high-paid job than（语法残缺）。",
        "native_model": "I began my undergraduate journey as a chemistry major, but I quickly realized my true calling lay in technology. I made a calculated pivot to computer science, partly driven by genuine passion, and partly because software engineering promises a substantially more lucrative career trajectory.",
        "chunks": [
            {"en": "chemistry major", "zh": "化学专业"},
            {"en": "make a calculated pivot to...", "zh": "深思熟虑后主动转轨/转向..."},
            {"en": "lucrative career trajectory", "zh": "高回报率、前景优渥的职业发展轨迹"}
        ]
    },
    {
        "id": 11,
        "module": 2,
        "module_name": "科技、职业野心与掌控力",
        "question": "Do you have any plans for your study in the next five years?",
        "bruce_raw": "my plan is to study English to improve my English speaking from like IELTS speaking band 6 to IELTS speaking band 8 or 8.5, and then I will just choose my job as an IELTS teacher... and then to earning by these jobs... in the meantime, AI is developing very rapidly... become an AI expert",
        "trap": "动名词与句式杂糅：to earning by these jobs，缺乏高级规划动词。",
        "native_model": "My strategic goal over the next three years is to propel my spoken English from a Band 6 to an 8.5 or higher, which will qualify me to mentor other test-takers and gain financial independence. Parallel to that, I'm relentlessly upskilling in artificial intelligence to position myself at the forefront of the technological frontier.",
        "chunks": [
            {"en": "propel my spoken English to Band 8.5", "zh": "推动口语能力跃升至 8.5 分"},
            {"en": "gain financial independence", "zh": "实现财务自主与经济独立"},
            {"en": "at the forefront of the technological frontier", "zh": "立于科技前沿浪尖"}
        ]
    },
    {
        "id": 12,
        "module": 2,
        "module_name": "科技、职业野心与掌控力",
        "question": "Do you prefer to study in the mornings or in the afternoons?",
        "bruce_raw": "actually I prefer studying in the morning because mornings is very quiet, actually, than afternoon. So a quiet space and wake up early to study can give me a sense of I'm a better person. I'm a, I have better execution, executive ability, you know.",
        "trap": "中式思维卡壳：give me a sense of I'm a better person... executive ability。",
        "native_model": "I do my most profound thinking in the early mornings. The serene quietude before dawn creates an uninterrupted cognitive space. Getting an early start provides an empowering sense of agency and proactive discipline that sets a positive momentum for the remainder of the day.",
        "chunks": [
            {"en": "serene quietude before dawn", "zh": "拂晓前的宁静与静谧"},
            {"en": "empowering sense of agency and proactive discipline", "zh": "赋能般的自我把控感与积极自律"},
            {"en": "set a positive momentum", "zh": "建立全天的正向行动惯性"}
        ]
    },
    {
        "id": 13,
        "module": 2,
        "module_name": "科技、职业野心与掌控力",
        "question": "How much time do you spend on your studies each week?",
        "bruce_raw": "I'm not a really regular person. I study time depends on my emotion... maybe I think it's around 30 hours a day. So it's 30 hours a week, so.",
        "trap": "严重口误：30 hours a day（一天学30小时？），depends on my emotion 表述不专业。",
        "native_model": "My study schedule doesn't conform to a rigid nine-to-five routine; rather, it is largely driven by inspiration and flow state. On average, I dedicate around thirty hours weekly to coursework, but when an intriguing programming problem hooks me, I can easily lose all track of time.",
        "chunks": [
            {"en": "driven by inspiration and flow state", "zh": "由灵感迸发与深度心流状态驱动"},
            {"en": "dedicate around thirty hours weekly", "zh": "每周投入约 30 小时"},
            {"en": "lose all track of time", "zh": "全情投入浑然不知时间流逝"}
        ]
    },
    {
        "id": 14,
        "module": 2,
        "module_name": "科技、职业野心与掌控力",
        "question": "Are you looking forward to working?",
        "bruce_raw": "Actually, I'm not looking forward to working, but I'm looking forward to earning money, you know. I'm not like, I don't want to work for others... I anticipate the outcomes work enables.",
        "trap": "口语过于直白：I don't want to work for others, I'm looking forward to earning money。",
        "native_model": "To be perfectly frank, the prospect of corporate servitude in a bureaucratic office doesn't appeal to me whatsoever. What truly excites me is achieving financial autonomy through entrepreneurial ventures where my compensation is directly tied to the tangible value I create.",
        "chunks": [
            {"en": "corporate servitude", "zh": "体制化大厂打工/公司牛马"},
            {"en": "financial autonomy", "zh": "财务自主与财务独立"},
            {"en": "entrepreneurial ventures", "zh": "商业创业与自我探索"}
        ]
    },
    {
        "id": 15,
        "module": 2,
        "module_name": "科技、职业野心与掌控力",
        "question": "What technology do you use when you study?",
        "bruce_raw": "AI, like ChatGPT and Doubao in China as well. So AI is very, very useful. It's widely used... I think it's must use AI, not should, must to try AI... to solve all these problems I met",
        "trap": "句式断裂破损：it's must use AI, not should, must to try AI。",
        "native_model": "AI platforms like ChatGPT and Doubao are the bedrock of my academic workflow. Leveraging large language models for instant debugging, concept breakdown, and language drilling has ceased to be an optional luxury; it is a non-negotiable imperative in modern technical education.",
        "chunks": [
            {"en": "bedrock of my academic workflow", "zh": "学术与学习工作流的基石"},
            {"en": "non-negotiable imperative", "zh": "不可妥协的刚需、时代必然要求"},
            {"en": "instant debugging and concept breakdown", "zh": "即时代码排错与复杂概念拆解"}
        ]
    },
    {
        "id": 16,
        "module": 2,
        "module_name": "科技、职业野心与掌控力",
        "question": "Describe a famous person you would like to meet.",
        "bruce_raw": "The famous person I would like to meet is Elon Musk... he is the richest people in the world... I think I'd like to meet him just in a road or in a restaurant... and he just covers himself up, like nobody could tell him to see him is Elon Musk, but I tell him... I would like to see how he thought, how he thinks",
        "trap": "语病：richest people（单复数不分），covers himself up nobody could tell him。",
        "native_model": "If given the opportunity, I'd relish a casual encounter with Elon Musk in a quiet bistro while he's keeping a low profile. Rather than inquiring about his net worth, I'd want to pick his brain regarding his first-principles thinking and how he maintains conviction when executing audacity-driven moonshot projects.",
        "chunks": [
            {"en": "keeping a low profile", "zh": "保持低调微服出行"},
            {"en": "pick his brain regarding...", "zh": "向他当面请教学习...的思维"},
            {"en": "first-principles thinking", "zh": "第一性原理思考法"},
            {"en": "audacity-driven moonshot projects", "zh": "胆魄驱动的登月级宏伟狂想"}
        ]
    },

    # 模块 3: 人际、家庭羁绊与习惯心理
    {
        "id": 17,
        "module": 3,
        "module_name": "人际、家庭羁绊与习惯心理",
        "question": "Do your friends use social media?",
        "bruce_raw": "we are Gen Z, and people's always can, you know, get rid of social media. we have to share in memes, videos, feelings with others... addicted to it, I would say.",
        "trap": "严重逻辑反义说反：people always can get rid of social media（想说戒不掉，却说成总能摆脱）。",
        "native_model": "As quintessential Gen Z digital natives, virtually all my peers are incurably hooked on social platforms. We simply cannot tear ourselves away from our screens—algorithmic feeds and instant viral memes have essentially become our primary medium for emotional validation and peer connectivity.",
        "chunks": [
            {"en": "incurably hooked on social platforms", "zh": "对社交网络不可救药地上瘾"},
            {"en": "cannot tear ourselves away from our screens", "zh": "根本无法将视线从屏幕移开（取代说反的 can get rid of）"},
            {"en": "primary medium for emotional validation", "zh": "寻求情感认同的主要媒介"}
        ]
    },
    {
        "id": 18,
        "module": 3,
        "module_name": "人际、家庭羁绊与习惯心理",
        "question": "Did you use to keep your room tidy as a child?",
        "bruce_raw": "I'm a lazy person from my child, so I just keep my room messy, and my mom will come and scold at me. But he kind of spoiled me, so he just scolded me, but he will clean the room himself. Herself.",
        "trap": "致命考场扣分点！指代母亲连续使用 he, himself，中国考生典型的第三人称混淆石化！",
        "native_model": "I was an incorrigibly messy child. My bedroom was perpetually disorganized, which frequently drew exasperated scoldings from my mother. However, she had a soft spot for me and undeniably coddled me, so she inevitably ended up tidying the clutter herself.",
        "chunks": [
            {"en": "she had a soft spot for me", "zh": "她（母亲）对我心软格外宠溺（注意代词必须下意识用 she/her）"},
            {"en": "she undeniably coddled me", "zh": "她毫无疑问娇惯溺爱着我"},
            {"en": "tidying the clutter herself", "zh": "亲自把杂乱房间收拾干净"}
        ]
    },
    {
        "id": 19,
        "module": 3,
        "module_name": "人际、家庭羁绊与习惯心理",
        "question": "Do you prefer online shopping or in-store shopping?",
        "bruce_raw": "instore shopping, you can see them and touch them. I think the most important thing is you can touch them. And also there are a lot of you know different experience, you can use your different organ... but online shopping is very achieve, accessible...",
        "trap": "中式惊人表达：use your different organ（直译“使用不同器官”太可怕！应为 multi-sensory experience）。",
        "native_model": "Although e-commerce boasts undeniable convenience, I still prefer brick-and-mortar retail when purchasing apparel. Nothing rivals the tactile feedback of assessing garment craftsmanship and drape in person—it delivers a rich, multi-sensory shopping experience that pixels on a smartphone simply cannot emulate.",
        "chunks": [
            {"en": "tactile feedback", "zh": "真实的触觉质感反馈"},
            {"en": "rich, multi-sensory shopping experience", "zh": "丰富多感官维度的沉浸购物体验"},
            {"en": "brick-and-mortar retail", "zh": "线下实体零售门店"}
        ]
    },
    {
        "id": 20,
        "module": 3,
        "module_name": "人际、家庭羁绊与习惯心理",
        "question": "Do you spend a lot of time choosing clothes?",
        "bruce_raw": "no, I haven't spent a lot on choosing clothes, because I hate to do this thing... maybe after the choice made, I will still regret that oh, maybe there are some better choice... so I just overlook and to see the best one at the moment from my feeling.",
        "trap": "词汇误用：overlook 表示忽视遗漏，想表达扫视浏览却用错词。",
        "native_model": "I deliberately keep my wardrobe streamlined to eliminate decision fatigue. Second-guessing apparel choices often induces buyer's remorse, so I rely on a versatile capsule collection of neutral basics that allow me to get dressed in under two minutes.",
        "chunks": [
            {"en": "eliminate decision fatigue", "zh": "消灭决策疲劳与精神内耗"},
            {"en": "induce buyer's remorse", "zh": "诱发买后犹豫后悔情绪"},
            {"en": "capsule collection of neutral basics", "zh": "中性百搭基础款胶囊衣橱"}
        ]
    },
    {
        "id": 21,
        "module": 3,
        "module_name": "人际、家庭羁绊与习惯心理",
        "question": "Do you prefer casual clothes or smart clothes?",
        "bruce_raw": "I prefer to wear comfortable clothes... like wearing t-shirts. it's very easy, you just grab and go, and when you do sports, it's very chilling... but if there are some specific scenery, like you are trying to get a job... wearing a smart clothes is also very important.",
        "trap": "词汇乱套：chilling 是吓人发怵（想表达 chill 放松惬意），scenery 是大自然风景（场合应为 setting/occasion）。",
        "native_model": "In my day-to-day routine, I swear by relaxed casual wear—a crisp, well-fitted white tee is virtually effortless to style. However, in formal professional contexts such as job interviews, dressing sharply in tailored attire is non-negotiable for projecting competence and respect.",
        "chunks": [
            {"en": "virtually effortless to style", "zh": "穿搭搭配极其轻松省心"},
            {"en": "dressing sharply in tailored attire", "zh": "身着利落得体的合身正装"},
            {"en": "projecting competence and respect", "zh": "展现出专业干练与对场合的尊重"}
        ]
    },
    {
        "id": 22,
        "module": 3,
        "module_name": "人际、家庭羁绊与习惯心理",
        "question": "What changes would you like to see in your school?",
        "bruce_raw": "my school didn't offer a place to place our takeout. It just hand out in the gates, and hand out or just put down in the gates. So some people just go there and pick up some takeout. He didn't order any takeout, he just stole others' takeout. So I wish my school will just have a like takeout cupboard...",
        "trap": "词穷借代：place to place our takeout，takeout cupboard（外卖橱柜？应为 thermal lockers）。",
        "native_model": "A pressing upgrade our campus requires is the installation of secure thermal parcel lockers for meal deliveries. Leaving student orders completely unattended on open benches near the entrance invites petty theft and sanitation hazards during rush hours.",
        "chunks": [
            {"en": "secure thermal parcel lockers", "zh": "安全保温外卖自提柜"},
            {"en": "invites petty theft", "zh": "引发小偷小摸顺手牵羊"},
            {"en": "sanitation hazards during rush hours", "zh": "高峰期的食品卫生隐患"}
        ]
    },
    {
        "id": 23,
        "module": 3,
        "module_name": "人际、家庭羁绊与习惯心理",
        "question": "Please describe the room you are living in.",
        "bruce_raw": "now I'm living in a dormitory. So it's a six-room dormitory, which lives about six people. So I just have a desk. It's two floors. The first floor is a desk, and the second floor is my bed.",
        "trap": "中式房间直译：six-room dormitory（误说成有六个房间），two floors desk bed（上下铺描述不清）。",
        "native_model": "I reside in a standard six-person communal dorm. Space is maximized through loft beds with integrated workstations underneath, giving each student a dedicated personal study nook while fostering camaraderie in the shared quarters.",
        "chunks": [
            {"en": "standard six-person communal dorm", "zh": "标准六人间集体宿舍"},
            {"en": "loft beds with integrated workstations underneath", "zh": "上床下桌一体化定制组合床"},
            {"en": "dedicated personal study nook", "zh": "独立的个人学习小空间"}
        ]
    },
    {
        "id": 24,
        "module": 3,
        "module_name": "人际、家庭羁绊与习惯心理",
        "question": "Are you still in touch with your primary school teacher?",
        "bruce_raw": "Yeah, absolutely not. it's been a long time. It's about like 12 years of before, I didn't attach with them, and I don't have a deep relationship with them.",
        "trap": "时态与搭配杂糅：12 years of before，didn't attach with them（直译没粘在他们身上）。",
        "native_model": "Not in the slightest. Over twelve years have elapsed since I graduated from elementary school, and we've completely lost touch. As one transitions through different life stages, maintaining connections with childhood instructors inevitably fades into distant memories.",
        "chunks": [
            {"en": "completely lost touch", "zh": "彻底断联失去联系"},
            {"en": "over twelve years have elapsed", "zh": "十二年时光已经匆匆流逝"},
            {"en": "inevitably fades into distant memories", "zh": "不可避免地淡化为远去的记忆"}
        ]
    },

    # 模块 4: 艺术、幽默与代际精神世界
    {
        "id": 25,
        "module": 4,
        "module_name": "艺术、幽默与代际精神世界",
        "question": "Are you good at telling jokes? Do you like comedies?",
        "bruce_raw": "I'm really really good at this thing. I think myself is very humorous person. I always made my friends just laugh out... if a person didn't take any jokes in their life, I think it's totally a mess, a boring mess, boring as hell person... I really into this kind of job like Friends...",
        "trap": "过量口头禅与俚语堆叠：laugh out, boring as hell person, this kind of job like Friends。",
        "native_model": "I consider myself naturally witty and quick with dry banter. Being able to crack a well-timed joke is essential for defusing awkward tension and breaking the ice. A life devoid of humor is thoroughly dreary, which is why I often unwind with classic sitcoms like Friends.",
        "chunks": [
            {"en": "quick with dry banter", "zh": "擅长冷幽默机智调侃"},
            {"en": "defuse awkward tension and break the ice", "zh": "化解尴尬紧绷、活跃破冰气氛"},
            {"en": "thoroughly dreary without humor", "zh": "缺少幽默的生活极其索然无味"}
        ]
    },
    {
        "id": 26,
        "module": 4,
        "module_name": "艺术、幽默与代际精神世界",
        "question": "What comedies do you enjoy watching?",
        "bruce_raw": "in Chinese, I watch a director or actor Zhou Xingchi's movie is very interesting. I like to laugh, you know? I like to see those videos that can help me laugh out.",
        "trap": "表达干瘪缺乏文化升华：Zhou Xingchi's movie is very interesting, help me laugh out。",
        "native_model": "I'm a fervent admirer of Stephen Chow's cinematic masterpieces. His trademark 'mo lei tau' slapstick absurdism, blended with poignant satirical undercurrents about ordinary underdogs, never fails to resonate with audiences across generations.",
        "chunks": [
            {"en": "slapstick absurdism", "zh": "无厘头闹剧与荒诞主义"},
            {"en": "poignant satirical undercurrents", "zh": "辛辣深刻的社会讽刺暗流"},
            {"en": "resonate with audiences across generations", "zh": "引起跨时代观众的强烈共鸣"}
        ]
    },
    {
        "id": 27,
        "module": 4,
        "module_name": "艺术、幽默与代际精神世界",
        "question": "Have you ever watched a live show?",
        "bruce_raw": "when I sit you know, on a like a, it's a ground, it's not a ground, I can say it's a sport museum, I can say it's not museum... very huge place... so when I sit them, I feel wow, it's really really unrealistic... Fancy thing... the vibe, the people around you, the singers...",
        "trap": "巨型场馆词穷：sport museum（体育博物馆？应为 arena/stadium），unrealistic（不切实际？应为 surreal）。",
        "native_model": "During my freshman year, I had the privilege of attending a stadium tour in a colossal indoor sports arena. Being amidst twenty thousand passionate fans screaming the lyrics in unison produced an electrifying, almost surreal sensory overload that live streaming can never replicate.",
        "chunks": [
            {"en": "colossal indoor sports arena", "zh": "巨型室内体育场馆/万人体育馆"},
            {"en": "screaming the lyrics in unison", "zh": "全场异口同声齐声高唱副歌"},
            {"en": "electrifying, almost surreal sensory overload", "zh": "电光火石般、近乎超现实的感官震撼"}
        ]
    },
    {
        "id": 28,
        "module": 4,
        "module_name": "艺术、幽默与代际精神世界",
        "question": "Do you prefer sad or happy music?",
        "bruce_raw": "when I'm sad, I want to listen to happy music, because it's, you know, it's very disgusting. I need to have the vibe to let me just be sad, be emotional... but when I'm happy, and then I listen to sad music, it will just feel wow so disgusting.",
        "trap": "词义严重偏离：disgusting 在英语里是恶心反胃想吐，你真正想表达的是“情绪违和刺耳”！",
        "native_model": "My music consumption is rigorously mood-congruent. If I'm emotionally downcast, forced cheerful pop feels incredibly jarring and discordant—it trivializes my sorrow. I need contemplative, melancholic acoustic tracks to properly process grief before I can embrace upbeat rhythms again.",
        "chunks": [
            {"en": "rigorously mood-congruent", "zh": "严格与心境和情绪状态高度契合"},
            {"en": "incredibly jarring and discordant", "zh": "极其刺耳刺眼、违和不协调（彻底取代误用的 disgusting）"},
            {"en": "trivialize my sorrow", "zh": "轻浮化、无视消解我的真实悲伤"}
        ]
    },
    {
        "id": 29,
        "module": 4,
        "module_name": "艺术、幽默与代际精神世界",
        "question": "Describe a singer or musician you admire.",
        "bruce_raw": "the singer I like is J. Cole... he's not a singer, he's a rapper... he's an honest, he's a kind and thoughtful person... his songs express so many deep thoughts... educate to some other people... give others powers to live on... just give you power to stress up, to not stress up...",
        "trap": "语言卡壳自相矛盾：educate to some other people，to stress up, to not stress up（加压又不加压？）。",
        "native_model": "I deeply revere the hip-hop visionary J. Cole. Unlike mainstream contemporaries who glorify material hedonism, Cole dissects human vulnerability, systemic inequities, and mental perseverance in his verses, providing his listeners with the emotional fortitude to decompress and weather life's storms.",
        "chunks": [
            {"en": "glorify material hedonism", "zh": "吹捧浮华的物质享乐主义"},
            {"en": "emotional fortitude to decompress", "zh": "自我解压沉淀的内心韧性与精神力量"},
            {"en": "weather life's storms", "zh": "抵御生活风浪与低谷"}
        ]
    },
    {
        "id": 30,
        "module": 4,
        "module_name": "艺术、幽默与代际精神世界",
        "question": "How does music shape people's identities and cultures? (Part 3)",
        "bruce_raw": "reading books or studying courses can shape people's identities and cultures. So I think listening to music is the same way... singers are conveying themselves... if you listen to more music... you can just get more styles that people live, get more thoughts that people think.",
        "trap": "词汇句式单薄：get more styles that people live, get more thoughts that people think。",
        "native_model": "Music acts as a conduit for cultural ethos. Immersion in eclectic genres allows listeners to absorb divergent philosophies, subcultural slang, and worldviews, thereby broadening emotional empathy and shaping personal identity far more organically than formal didactic schooling.",
        "chunks": [
            {"en": "conduit for cultural ethos", "zh": "文化精神与时代风骨的传导通道"},
            {"en": "absorb divergent philosophies", "zh": "汲取多元迥异的思想与哲学洞察"},
            {"en": "shape personal identity organically", "zh": "潜移默化、自然而然地塑造个人认同"}
        ]
    },
    {
        "id": 31,
        "module": 4,
        "module_name": "艺术、幽默与代际精神世界",
        "question": "Why do different generations prefer different kinds of music? (Part 3)",
        "bruce_raw": "different generations face different problems. Like the old generation may face a problem like earning money and to go to the bigger city to make a living. So the new generation may face a lot of problems about emotion, about private affairs... country is become better, so we face a different problems.",
        "trap": "社会学洞察极深，但语言受限严重：face a problem like earning money, problems about emotion。",
        "native_model": "Musical preferences are an accurate reflection of generational priorities. The older demographic, having navigated historical hardships, naturally prioritized economic security and material survival. In contrast, today's youth enjoy material abundance but wrestle with existential angst, digital alienation, and hyper-competitive burnout, necessitating music that validates inner emotional turmoil.",
        "chunks": [
            {"en": "material survival versus existential angst", "zh": "物质匮乏求生 vs 精神存在主义焦虑（神级学术级对比）"},
            {"en": "digital alienation and burnout", "zh": "数字时代的人际疏离与过度内卷耗竭"},
            {"en": "validate inner emotional turmoil", "zh": "确认并抚平内心的情感惊涛骇浪"}
        ]
    },
    {
        "id": 32,
        "module": 4,
        "module_name": "艺术、幽默与代际精神世界",
        "question": "Has globalization influenced local musical traditions? (Part 3)",
        "bruce_raw": "globalization will spread the culture... in Chinese with the economy development, so they also face the same needs. So the hip-hop music is coming to China and just developed because China has a better economy development... have the same needs to express",
        "trap": "economy development 机械重复三遍，缺少专业跨文化交流词汇。",
        "native_model": "Globalization has fostered profound cross-cultural cross-pollination. The explosive proliferation of hip-hop across China illustrates how imported Western subcultures can take root locally, satisfying the modern Chinese youth's appetite for an authentic, raw emotional outlet to articulate individuality.",
        "chunks": [
            {"en": "cross-cultural cross-pollination", "zh": "跨文化的深度交融互惠"},
            {"en": "explosive proliferation of hip-hop", "zh": "嘻哈说唱文化爆发式的普及裂变"},
            {"en": "raw emotional outlet to articulate individuality", "zh": "宣泄真实情感、表达独立个性的直率出口"}
        ]
    },

    # 模块 5: 地理水土、城市变迁与浩瀚宇宙
    {
        "id": 33,
        "module": 5,
        "module_name": "地理水土、城市变迁与浩瀚宇宙",
        "question": "Where is your hometown? Is it a big city or small place?",
        "bruce_raw": "my hometown is in Shangrao city in Jiangxi province. It's just a developing city... less of development, small town... people there just say in the accent or they just say the dialect... actual hometown, I have lived in a hill, you know, I've lived in a mountain",
        "trap": "生硬表达：less of development，say in the accent，lived in a hill。",
        "native_model": "My roots are in Shangrao, an inland city nestled in the rolling, verdant hills of Jiangxi province. Rather than being a bustling metropolis, it retains a tranquil pastoral rhythm, where residents converse in authentic regional dialects and maintain close-knit communal ties.",
        "chunks": [
            {"en": "nestled in rolling, verdant hills", "zh": "依偎在连绵青葱的苍翠丘陵之中"},
            {"en": "tranquil pastoral rhythm", "zh": "宁静祥和的田园生活节拍"},
            {"en": "close-knit communal ties", "zh": "紧密亲近的熟人社区纽带"}
        ]
    },
    {
        "id": 34,
        "module": 5,
        "module_name": "地理水土、城市变迁与浩瀚宇宙",
        "question": "What city do you live in now, and do you like it?",
        "bruce_raw": "I live in Qingdao, in Shandong province... not a city person... I didn't get well, you know. I didn't get used to this city because it's too cold in the winter and it's too dry... and it also have a higher price",
        "trap": "直译病句：didn't get well（误把不适应气候说成生病好不了），have a higher price。",
        "native_model": "I currently reside in Qingdao for university. Hailing from the subtropical humidity of southern China, I initially struggled to acclimatize to northern China's biting coastal winds and harsh, arid winters. Furthermore, the steeper cost of living initially posed an adjustment challenge.",
        "chunks": [
            {"en": "struggled to acclimatize to...", "zh": "极力去适应克服...的水土气候（替代 didn't get well）"},
            {"en": "biting coastal winds and harsh, arid winters", "zh": "刺骨凛冽的海风与干冷寒冬"},
            {"en": "steeper cost of living", "zh": "更高的日常生活开销成本"}
        ]
    },
    {
        "id": 35,
        "module": 5,
        "module_name": "地理水土、城市变迁与浩瀚宇宙",
        "question": "Do you still like going to parks now?",
        "bruce_raw": "as a child, I will say no... park is very boring... but I like to go to parks now, because I kind of really into this peaceful emotion... I could see a beautiful sceneries to watch those peoples, what are they doing to watch their lives",
        "trap": "词汇匮乏：peaceful emotion，watch those peoples what are they doing to watch their lives。",
        "native_model": "While my younger self viewed manicured parks as sterile and unstimulating, I now view public botanical gardens as indispensable urban sanctuaries. Taking a leisurely stroll along landscaped trails provides an ideal vantage point for people-watching and decompressing from academic rigor.",
        "chunks": [
            {"en": "indispensable urban sanctuaries", "zh": "不可或缺的都市心灵避风港绿洲"},
            {"en": "indulge in people-watching", "zh": "悠然惬意地观察过往形形色色的人间百态"},
            {"en": "decompress from academic rigor", "zh": "从高强度的学术学业压力中喘息解压"}
        ]
    },
    {
        "id": 36,
        "module": 5,
        "module_name": "地理水土、城市变迁与浩瀚宇宙",
        "question": "Did you enjoy traveling by car as a kid?",
        "bruce_raw": "I didn't enjoy it, because my father is a worker, and he put so many tools in his car. he is like you know the worker that who builds home, who construct house. So there are a lot of tools that is dirty, smelly... just dislike the smell of this tools, this car... make me dizzy",
        "trap": "生活细节极其真实！但语言卡壳：worker who construct house, smell of this tools make me dizzy。",
        "native_model": "I actually nurtured a dread of vehicular travel during my childhood. My father was involved in residential construction, and his vehicle was constantly laden with heavy power equipment. The suffocating stench of motor grease, gasoline vapors, and industrial dust unfailingly induced severe motion sickness in me.",
        "chunks": [
            {"en": "suffocating stench of motor grease and gasoline", "zh": "机油与汽油废气刺鼻窒息的恶臭"},
            {"en": "induced severe motion sickness", "zh": "不可避免地诱发严重的晕车与恶心反胃"},
            {"en": "laden with heavy power equipment", "zh": "装满了沉重的工程机械工具"}
        ]
    },
    {
        "id": 37,
        "module": 5,
        "module_name": "地理水土、城市变迁与浩瀚宇宙",
        "question": "Do you prefer to be a driver or a passenger?",
        "bruce_raw": "Of course, a passenger... driving a car is very boring... you need to sit in a same seat, and put your hands on aController andAlways focus on the road... what do you usually do when there is traffic jam? I just play my phone... hope the traffic jam will get through quickly.",
        "trap": "词穷借代：put hands on aController（把手放在控制器上？汽车方向盘是 steering wheel），get through quickly。",
        "native_model": "I'm unequivocally in favor of remaining a passenger. Gripping a steering wheel and maintaining unyielding concentration through tedious gridlock feels mentally taxing. As a passenger, a traffic bottleneck merely affords me bonus downtime to catch up on podcasts or respond to correspondence.",
        "chunks": [
            {"en": "gripping a steering wheel in tedious gridlock", "zh": "在枯燥龟速的堵车大军中紧握方向盘"},
            {"en": "traffic bottleneck", "zh": "交通拥堵瓶颈"},
            {"en": "bonus downtime to catch up on podcasts", "zh": "收听播客或处理琐事的宝贵闲暇时光"}
        ]
    },
    {
        "id": 38,
        "module": 5,
        "module_name": "地理水土、城市变迁与浩瀚宇宙",
        "question": "Do you think car colors are important?",
        "bruce_raw": "it's about the first impressions thing. If others in your car and he will just have some thoughts about your personality or your trace from your car's appearance.",
        "trap": "直译：first impressions thing，your personality or your trace（trace 词义错误）。",
        "native_model": "Exterior automotive hues carry understated psychological connotations. Opting for a subdued matte charcoal projects understated sophistication, whereas a blazing crimson signals boldness and assertiveness, quietly influencing how an owner's persona is initially perceived.",
        "chunks": [
            {"en": "understated psychological connotations", "zh": "含蓄低调的心理学隐喻与暗示"},
            {"en": "projects understated sophistication", "zh": "折射出低调内敛的高级沉稳气质"},
            {"en": "influence how an owner's persona is perceived", "zh": "潜移默化影响他人对车主性格特质的第一印象"}
        ]
    },
    {
        "id": 39,
        "module": 5,
        "module_name": "地理水土、城市变迁与浩瀚宇宙",
        "question": "Which science subject is interesting to you?",
        "bruce_raw": "how two stars have a gravity, and one just surrounded by another, and how the black hole just coming to being... I think like there is dead lake and people just float in the lake. They didn't just dive into this because of the salt...",
        "trap": "词汇残缺：dead lake（死湖？应为 the Dead Sea），two stars have a gravity，black hole coming to being。",
        "native_model": "I'm endlessly fascinated by astrophysics and fluid mechanics. Contemplating celestial bodies locked in gravitational orbits, or how dying stars experience gravitational collapse to birth black holes, alongside phenomena like the hyper-saline buoyancy of the Dead Sea, fills me with intellectual awe.",
        "chunks": [
            {"en": "gravitational collapse to birth black holes", "zh": "引力坍缩孕育出黑洞"},
            {"en": "hyper-saline buoyancy of the Dead Sea", "zh": "死海高含盐度带来的神奇漂浮力"},
            {"en": "intellectual awe", "zh": "对自然未知法则的理性敬畏与震颤"}
        ]
    },
    {
        "id": 40,
        "module": 5,
        "module_name": "地理水土、城市变迁与浩瀚宇宙",
        "question": "Do you like science fiction movies? Do you want to know about outer space?",
        "bruce_raw": "things that you haven't saw it about before... motivate something that you be hope about your future... spend much time on watching those videos. I'm very curious about aliens: are they really exist?",
        "trap": "时态与从句错误：things that you haven't saw it about before，are they really exist。",
        "native_model": "Hard sci-fi cinema captures my imagination because it extrapolates bold speculative realities. I frequently find myself falling down internet rabbit holes researching the Fermi Paradox, contemplating whether intelligent extraterrestrial civilizations inhabit the uncharted cosmos.",
        "chunks": [
            {"en": "the Fermi Paradox", "zh": "费米悖论（外星人在哪里的科学诘问）"},
            {"en": "intelligent extraterrestrial civilizations", "zh": "地外高级智慧文明"},
            {"en": "fall down internet rabbit holes", "zh": "在网上顺藤摸瓜入迷探索未知领域"}
        ]
    },
    {
        "id": 41,
        "module": 5,
        "module_name": "地理水土、城市变迁与浩瀚宇宙",
        "question": "Do you want to go into outer space in the future?",
        "bruce_raw": "Yes, if I had a choice... it's also it depends on it's in the price or it's safety, you know? because it's very a big thing going to outer space. I think if that's convenient, it's very safe and not that expensive, and I will go to into outer space.",
        "trap": "中式口癖：depends on it's in the price or safety，not that expensive，go to into outer space。",
        "native_model": "Given the chance, I'd embark on spaceflight without a second thought, assuming rigorous safety redundancies. While suborbital tourism currently incurs astronomical and cost-prohibitive expenditures, beholding our pale blue dot against the cosmic void would be an unparalleled, life-altering epiphany.",
        "chunks": [
            {"en": "astronomical and cost-prohibitive expenditures", "zh": "天文数字般令人望而却步的高昂代价"},
            {"en": "beholding our pale blue dot against the cosmic void", "zh": "在冰冷浩瀚的宇宙虚空中注视那颗暗淡蓝点"},
            {"en": "unparalleled, life-altering epiphany", "zh": "无可比拟、震撼并改变一生的精神顿悟"}
        ]
    }
]

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bruce 专属雅思口语 8.5 分定制学习大典与全功能工作台</title>
    <style>
        :root {
            --bg-primary: #0f172a;
            --bg-secondary: #1e293b;
            --bg-card: #1e293b;
            --border-color: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-gold: #f59e0b;
            --accent-blue: #38bdf8;
            --accent-emerald: #10b981;
            --accent-rose: #f43f5e;
            --chip-bg: #334155;
        }

        [data-theme="light"] {
            --bg-primary: #f8fafc;
            --bg-secondary: #ffffff;
            --bg-card: #ffffff;
            --border-color: #e2e8f0;
            --text-primary: #0f172a;
            --text-secondary: #64748b;
            --accent-gold: #d97706;
            --accent-blue: #0284c7;
            --accent-emerald: #059669;
            --accent-rose: #e11d48;
            --chip-bg: #f1f5f9;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }

        body {
            background-color: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            padding-bottom: 80px;
            transition: background-color 0.3s ease, color 0.3s ease;
        }

        header {
            background: linear-gradient(135deg, rgba(30, 41, 59, 0.95), rgba(15, 23, 42, 0.98));
            border-bottom: 1px solid var(--border-color);
            padding: 30px 20px;
            position: sticky;
            top: 0;
            z-index: 100;
            backdrop-filter: blur(10px);
        }

        .header-content {
            max-width: 1280px;
            margin: 0 auto;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
        }

        .header-title h1 {
            font-size: 24px;
            font-weight: 800;
            color: var(--text-primary);
            letter-spacing: -0.5px;
        }

        .header-title p {
            font-size: 14px;
            color: var(--text-secondary);
            margin-top: 4px;
        }

        .theme-btn {
            background: var(--chip-bg);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 600;
            transition: all 0.2s;
        }

        .theme-btn:hover {
            border-color: var(--accent-gold);
        }

        .container {
            max-width: 1280px;
            margin: 30px auto;
            padding: 0 20px;
        }

        /* SECTION HEADERS */
        .section-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
            border-left: 4px solid var(--accent-gold);
            padding-left: 12px;
        }

        .section-header h2 {
            font-size: 20px;
            font-weight: 700;
        }

        /* AUDIO SUITE SECTION */
        .audio-suite {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 40px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
        }

        .track-tabs {
            display: flex;
            gap: 10px;
            overflow-x: auto;
            padding-bottom: 12px;
            margin-bottom: 20px;
        }

        .track-tab {
            background: var(--chip-bg);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 10px 18px;
            border-radius: 10px;
            cursor: pointer;
            white-space: nowrap;
            font-size: 14px;
            font-weight: 600;
            transition: all 0.2s;
        }

        .track-tab.active {
            background: var(--accent-blue);
            color: #ffffff;
            border-color: var(--accent-blue);
        }

        .player-box {
            display: grid;
            grid-template-columns: 1fr;
            gap: 16px;
            background: var(--bg-primary);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
        }

        .player-info h3 {
            font-size: 18px;
            color: var(--accent-gold);
            margin-bottom: 6px;
        }

        .player-info p {
            font-size: 14px;
            color: var(--text-secondary);
            margin-bottom: 12px;
        }

        audio {
            width: 100%;
            border-radius: 8px;
            outline: none;
        }

        .audio-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }

        .tag-pill {
            background: rgba(56, 189, 248, 0.15);
            color: var(--accent-blue);
            border: 1px solid rgba(56, 189, 248, 0.3);
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }

        /* IMAGE GALLERY SECTION */
        .gallery-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }

        .gallery-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            overflow: hidden;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .gallery-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
            border-color: var(--accent-gold);
        }

        .gallery-card img {
            width: 100%;
            height: 280px;
            object-fit: cover;
            display: block;
        }

        .gallery-meta {
            padding: 12px 14px;
        }

        .gallery-meta h4 {
            font-size: 14px;
            font-weight: 700;
            color: var(--text-primary);
        }

        .gallery-meta p {
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 4px;
        }

        /* FILTER & SEARCH */
        .controls-bar {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            margin-bottom: 24px;
            align-items: center;
        }

        .search-input {
            flex: 1;
            min-width: 260px;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            color: var(--text-primary);
            padding: 12px 16px;
            border-radius: 10px;
            font-size: 14px;
            outline: none;
            transition: border-color 0.2s;
        }

        .search-input:focus {
            border-color: var(--accent-gold);
        }

        .filter-chips {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }

        .filter-chip {
            background: var(--chip-bg);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 8px 14px;
            border-radius: 8px;
            font-size: 13px;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.2s;
        }

        .filter-chip.active {
            background: var(--accent-gold);
            color: #0f172a;
            border-color: var(--accent-gold);
            font-weight: 700;
        }

        /* 41 TOPICS CARDS */
        .topics-grid {
            display: grid;
            grid-template-columns: 1fr;
            gap: 20px;
        }

        .topic-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 22px;
            transition: border-color 0.2s;
        }

        .topic-card:hover {
            border-color: rgba(245, 158, 11, 0.5);
        }

        .topic-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 12px;
            margin-bottom: 14px;
        }

        .topic-badge {
            background: var(--chip-bg);
            border: 1px solid var(--border-color);
            color: var(--accent-gold);
            font-size: 12px;
            font-weight: 700;
            padding: 4px 8px;
            border-radius: 6px;
            white-space: nowrap;
        }

        .topic-question {
            font-size: 16px;
            font-weight: 700;
            color: var(--text-primary);
            flex: 1;
        }

        .block-section {
            margin-top: 12px;
            padding: 12px;
            border-radius: 8px;
            font-size: 14px;
        }

        .bruce-block {
            background: rgba(244, 63, 94, 0.08);
            border-left: 3px solid var(--accent-rose);
        }

        .bruce-label {
            font-size: 12px;
            font-weight: 700;
            color: var(--accent-rose);
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .trap-text {
            color: var(--text-secondary);
            font-size: 13px;
            margin-top: 6px;
            font-style: italic;
        }

        .native-block {
            background: rgba(16, 185, 129, 0.08);
            border-left: 3px solid var(--accent-emerald);
        }

        .native-label {
            font-size: 12px;
            font-weight: 700;
            color: var(--accent-emerald);
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .listen-btn {
            background: transparent;
            border: none;
            color: var(--accent-emerald);
            cursor: pointer;
            font-size: 12px;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 4px;
        }

        .listen-btn:hover {
            text-decoration: underline;
        }

        .chunks-list {
            margin-top: 12px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 8px;
        }

        .chunk-item {
            background: var(--bg-primary);
            border: 1px solid var(--border-color);
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 13px;
        }

        .chunk-en {
            font-weight: 700;
            color: var(--accent-blue);
        }

        .chunk-zh {
            color: var(--text-secondary);
            font-size: 12px;
            margin-top: 2px;
        }

        /* MODAL */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.85);
            align-items: center;
            justify-content: center;
            backdrop-filter: blur(5px);
        }

        .modal-content {
            max-width: 90%;
            max-height: 90%;
            border-radius: 12px;
            box-shadow: 0 0 30px rgba(0, 0, 0, 0.5);
        }

        .modal-close {
            position: absolute;
            top: 20px;
            right: 30px;
            color: #ffffff;
            font-size: 32px;
            font-weight: bold;
            cursor: pointer;
        }
    </style>
</head>
<body>

    <header>
        <div class="header-content">
            <div class="header-title">
                <h1>Bruce 雅思口语 8.5 分定制全景工作台</h1>
                <p>基于你 41 道真题真实回答的全面母语级重构 · 5 部广播级双主持音频 · 5 套视觉认知图谱</p>
            </div>
            <button class="theme-btn" onclick="toggleTheme()">🌓 切换明暗主题</button>
        </div>
    </header>

    <div class="container">

        <!-- SECTION 1: 5 大音频专辑 -->
        <div class="section-header">
            <h2>🎧 5 部广播级“神经闭环”定制训练音频专辑</h2>
        </div>

        <div class="audio-suite">
            <div class="track-tabs" id="trackTabs">
                <button class="track-tab active" onclick="switchTrack(0)">Track 01: 具象物品大解救</button>
                <button class="track-tab" onclick="switchTrack(1)">Track 02: 科技野心掌控力</button>
                <button class="track-tab" onclick="switchTrack(2)">Track 03: 家庭习惯与代词</button>
                <button class="track-tab" onclick="switchTrack(3)">Track 04: 艺术幽默代际观</button>
                <button class="track-tab" onclick="switchTrack(4)">Track 05: 城市水土与宇宙</button>
            </div>

            <div class="player-box">
                <div class="player-info">
                    <h3 id="playerTitle">Track 01: 具象物品与生活常识词穷大解救</h3>
                    <p id="playerDesc">狙击痛点：手电筒光束、放大镜、耳机插孔、手表避险资产、面霜白茬残留。内嵌 8 秒强制张嘴检索输出静音区。</p>
                    <audio id="mainAudio" controls preload="metadata">
                        <source id="audioSource" src="audio/bruce_track_01_objects_and_senses.mp3" type="audio/mpeg">
                        您的浏览器不支持音频播放。
                    </audio>
                    <div class="audio-tags" id="playerTags">
                        <span class="tag-pill">🎯 magnifying glass</span>
                        <span class="tag-pill">🎯 flashlight beam</span>
                        <span class="tag-pill">🎯 status symbol</span>
                        <span class="tag-pill">🎯 headphone jack</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- SECTION 2: 视觉认知图谱画廊 -->
        <div class="section-header">
            <h2>🖼️ 5 套高清视觉认知图谱卡（点击大图查看）</h2>
        </div>

        <div class="gallery-grid">
            <div class="gallery-card" onclick="openModal('images/card_01_objects.jpg')">
                <img src="images/card_01_objects.jpg" alt="具象物品词穷急救手册">
                <div class="gallery-meta">
                    <h4>Card 01: 具象物品词穷急救</h4>
                    <p>手电筒/放大镜/场馆/耳机孔对撞</p>
                </div>
            </div>
            <div class="gallery-card" onclick="openModal('images/card_02_tech.jpg')">
                <img src="images/card_02_tech.jpg" alt="科技与野心表达矩阵">
                <div class="gallery-meta">
                    <h4>Card 02: 科技与商业野心</h4>
                    <p>Vibe coding/财务自主/晨起自律</p>
                </div>
            </div>
            <div class="gallery-card" onclick="openModal('images/card_03_habits.jpg')">
                <img src="images/card_03_habits.jpg" alt="人际家庭与语法避坑">
                <div class="gallery-meta">
                    <h4>Card 03: 人际家庭与代词避坑</h4>
                    <p>彻底根治母亲 he/she 混乱</p>
                </div>
            </div>
            <div class="gallery-card" onclick="openModal('images/card_04_music.jpg')">
                <img src="images/card_04_music.jpg" alt="艺术幽默代际思辨">
                <div class="gallery-meta">
                    <h4>Card 04: 艺术幽默代际思辨</h4>
                    <p>万人场馆演出/物质匮乏vs精神内耗</p>
                </div>
            </div>
            <div class="gallery-card" onclick="openModal('images/card_05_cities.jpg')">
                <img src="images/card_05_cities.jpg" alt="城市水土与宇宙科学">
                <div class="gallery-meta">
                    <h4>Card 05: 城市水土与宇宙科学</h4>
                    <p>上饶山城vs青岛海风/死海引力黑洞</p>
                </div>
            </div>
        </div>

        <!-- SECTION 3: 41 题全量逐题诊断与 8.5 分升维词典 -->
        <div class="section-header">
            <h2>📖 41 题全量母语级诊断与 8.5 分重构词典 (<span id="resultsCount">41</span> 题)</h2>
        </div>

        <div class="controls-bar">
            <input type="text" id="searchInput" class="search-input" placeholder="🔍 搜索任意关键词（如 flashlight, mom, vibe coding, 放大镜, 手表...）" oninput="filterTopics()">
            <div class="filter-chips">
                <button class="filter-chip active" onclick="setModuleFilter(0, this)">全部 (41)</button>
                <button class="filter-chip" onclick="setModuleFilter(1, this)">模块1: 具象物品 (8)</button>
                <button class="filter-chip" onclick="setModuleFilter(2, this)">模块2: 科技野心 (8)</button>
                <button class="filter-chip" onclick="setModuleFilter(3, this)">模块3: 家庭习惯 (8)</button>
                <button class="filter-chip" onclick="setModuleFilter(4, this)">模块4: 艺术音乐 (8)</button>
                <button class="filter-chip" onclick="setModuleFilter(5, this)">模块5: 水土宇宙 (9)</button>
            </div>
        </div>

        <div class="topics-grid" id="topicsContainer">
            <!-- 动态渲染 41 道题卡片 -->
        </div>

    </div>

    <!-- 图片放大弹窗 -->
    <div id="imageModal" class="modal" onclick="closeModal()">
        <span class="modal-close">&times;</span>
        <img class="modal-content" id="modalImg" src="">
    </div>

    <script>
        const TRACKS = [
            {
                title: "Track 01: 具象物品与生活常识词穷大解救",
                desc: "狙击痛点：手电筒光束 (flashlight beam)、放大镜 (magnifying glass)、耳机插孔 (headphone jack)、手表避险资产 (portable store of value)、面霜白茬残留 (unabsorbed residue)。内嵌 8 秒强制张嘴检索输出静音区。",
                src: "audio/bruce_track_01_objects_and_senses.mp3",
                tags: ["magnifying glass", "flashlight beam", "status symbol", "headphone jack", "portable store of value"]
            },
            {
                title: "Track 02: 野心、科技与个人掌控力",
                desc: "狙击痛点：Vibe coding、AI 时代必然 (non-negotiable imperative)、晨起自我把控感 (sense of agency and proactive discipline)、财务自主与创业 (financial autonomy)。内嵌 8 秒即时检索输出挑战。",
                src: "audio/bruce_track_02_tech_ambition_agency.mp3",
                tags: ["vibe coding", "sense of agency", "non-negotiable imperative", "financial autonomy", "first-principles"]
            },
            {
                title: "Track 03: 人际、家庭羁绊与习惯心理",
                desc: "重点战役：彻底纠正指代母亲时的 he/she 扣分错误！社交媒体戒不掉 (cannot tear ourselves away)、实体店触感体验 (tactile feedback)、胶囊衣橱消除决策疲劳 (decision fatigue)。",
                src: "audio/bruce_track_03_habits_family_psychology.mp3",
                tags: ["she coddled me (代词纠偏)", "glued to screens", "tactile feedback", "decision fatigue", "lost touch"]
            },
            {
                title: "Track 04: 艺术、幽默与代际精神世界",
                desc: "狙击痛点：体育馆演唱会震撼 (massive indoor arena / surreal)、情绪不对位违和感 (jarring and discordant)、老一代物质匮乏 vs 新一代精神内耗 (material scarcity vs existential angst)、说唱精神出口。",
                src: "audio/bruce_track_04_art_humor_generations.mp3",
                tags: ["indoor arena", "jarring mismatch", "material scarcity vs existential angst", "emotional outlet"]
            },
            {
                title: "Track 05: 地理水土、城市变迁与浩瀚宇宙",
                desc: "狙击痛点：江西上饶依偎山峦 (nestled in hilly landscapes)、青岛海风水土不服 (acclimatize to biting cold)、公园看人间烟火 (people-watching)、引力黑洞与死海浮力、太空旅行高昂造价。",
                src: "audio/bruce_track_05_cities_environment_cosmos.mp3",
                tags: ["nestled in hilly landscapes", "acclimatize", "people-watching", "astrophysics", "prohibitive costs"]
            }
        ];

        const TOPICS = """ + json.dumps(TOPICS_DATA, ensure_ascii=False) + """;

        let currentModuleFilter = 0;

        function switchTrack(idx) {
            const tabs = document.querySelectorAll('.track-tab');
            tabs.forEach((tab, i) => tab.classList.toggle('active', i === idx));

            const t = TRACKS[idx];
            document.getElementById('playerTitle').innerText = t.title;
            document.getElementById('playerDesc').innerText = t.desc;

            const audio = document.getElementById('mainAudio');
            const source = document.getElementById('audioSource');
            source.src = t.src;
            audio.load();
            audio.play().catch(() => {});

            const tagsDiv = document.getElementById('playerTags');
            tagsDiv.innerHTML = t.tags.map(tag => `<span class="tag-pill">🎯 ${tag}</span>`).join('');
        }

        function renderTopics(list) {
            const container = document.getElementById('topicsContainer');
            document.getElementById('resultsCount').innerText = list.length;

            if (list.length === 0) {
                container.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--text-secondary);">未找到匹配的题目</div>`;
                return;
            }

            container.innerHTML = list.map(item => `
                <div class="topic-card">
                    <div class="topic-header">
                        <span class="topic-badge">Topic ${item.id.toString().padStart(2, '0')} · ${item.module_name}</span>
                        <div class="topic-question">${item.question}</div>
                    </div>

                    <div class="block-section bruce-block">
                        <div class="bruce-label">
                            <span>❌ Bruce 原始回答切片（痛点暴露）</span>
                        </div>
                        <div style="font-family: monospace; color: var(--text-primary); font-size: 13px;">"${item.bruce_raw}"</div>
                        <div class="trap-text">⚠️ 诊断分析：${item.trap}</div>
                    </div>

                    <div class="block-section native-block" style="margin-top: 10px;">
                        <div class="native-label">
                            <span>✨ 8.5 分母语级重构示范 (Ethan Model)</span>
                            <button class="listen-btn" onclick="speakText('${encodeURIComponent(item.native_model)}')">🔊 发音朗读</button>
                        </div>
                        <div style="color: var(--text-primary); font-weight: 500; font-size: 14px;">"${item.native_model}"</div>
                    </div>

                    <div class="chunks-list">
                        ${item.chunks.map(c => `
                            <div class="chunk-item">
                                <div class="chunk-en">🔑 ${c.en}</div>
                                <div class="chunk-zh">${c.zh}</div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `).join('');
        }

        function filterTopics() {
            const query = document.getElementById('searchInput').value.trim().toLowerCase();
            const filtered = TOPICS.filter(item => {
                const matchModule = currentModuleFilter === 0 || item.module === currentModuleFilter;
                const matchQuery = !query ||
                    item.question.toLowerCase().includes(query) ||
                    item.bruce_raw.toLowerCase().includes(query) ||
                    item.native_model.toLowerCase().includes(query) ||
                    item.trap.toLowerCase().includes(query) ||
                    item.chunks.some(c => c.en.toLowerCase().includes(query) || c.zh.toLowerCase().includes(query));
                return matchModule && matchQuery;
            });
            renderTopics(filtered);
        }

        function setModuleFilter(mod, el) {
            currentModuleFilter = mod;
            document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
            el.classList.add('active');
            filterTopics();
        }

        function speakText(encodedText) {
            if ('speechSynthesis' in window) {
                window.speechSynthesis.cancel();
                const text = decodeURIComponent(encodedText);
                const utter = new SpeechSynthesisUtterance(text);
                utter.lang = 'en-US';
                utter.rate = 0.95;
                window.speechSynthesis.speak(utter);
            } else {
                alert('您的浏览器不支持 Web Speech API');
            }
        }

        function toggleTheme() {
            const current = document.documentElement.getAttribute('data-theme');
            const target = current === 'light' ? 'dark' : 'light';
            document.documentElement.setAttribute('data-theme', target);
        }

        function openModal(imgSrc) {
            const modal = document.getElementById('imageModal');
            const modalImg = document.getElementById('modalImg');
            modal.style.display = "flex";
            modalImg.src = imgSrc;
        }

        function closeModal() {
            document.getElementById('imageModal').style.display = "none";
        }

        // 初始化渲染
        renderTopics(TOPICS);
    </script>
</body>
</html>
"""

def main():
    OUTPUT_FILE.write_text(HTML_TEMPLATE, encoding="utf-8")
    print(f"Bruce 专属交互式工作台已生成: {OUTPUT_FILE.resolve()}")

if __name__ == "__main__":
    main()
