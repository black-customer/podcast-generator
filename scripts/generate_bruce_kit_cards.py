"""Bruce 个性化口语学习包：22 张学习卡生成器（PIL，1080x1350）。

A 系列 x10 错误修补卡（Bruce 原句 -> 母语者版 -> 一句规则）
B 系列 x8 语块卡（语块 + 中文 + 示范句 + 出处）
C 系列 x4 总览图（AREA 框架 / 十大伤口 / 14 天计划 / 使用指南）
输出：bruce_kit/cards/*.png。全部可由本脚本再生。
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "bruce_kit" / "cards"

W, H = 1080, 1350
MARGIN = 72
PAPER = "#FAF6EE"
INK = "#1F2937"
SUB = "#6B7280"
RED = "#C2410C"
RED_BG = "#FDEBE3"
GREEN = "#047857"
GREEN_BG = "#E2F3EC"
AMBER = "#B45309"
AMBER_BG = "#FBF0DC"
LINE = "#D9CFBC"

FONT_PATHS = {
    ("zh", False): [r"C:\Windows\Fonts\msyh.ttc"],
    ("zh", True): [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\msyh.ttc"],
    ("en", False): [r"C:\Windows\Fonts\consola.ttf", r"C:\Windows\Fonts\arial.ttf"],
    ("en", True): [r"C:\Windows\Fonts\consolab.ttf", r"C:\Windows\Fonts\arialbd.ttf"],
}


def font(kind: str, bold: bool, size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS[(kind, bold)]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)  # type: ignore[return-value]


def _units(text: str) -> list[str]:
    """分词单元：西文按空格成词（词内不拆），CJK 与全角标点逐字。"""
    import re

    units: list[str] = []
    for part in re.split(r"(\s+)", text):
        if not part:
            continue
        if part.isspace():
            units.append(part)
            continue
        cur = ""
        for ch in part:
            if ord(ch) < 0x2E80:
                cur += ch
            else:
                if cur:
                    units.append(cur)
                    cur = ""
                units.append(ch)
        if cur:
            units.append(cur)
    return units


def wrap(
    draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_w: int
) -> list[str]:
    lines: list[str] = []
    for raw in text.split("\n"):
        cur = ""
        for unit in _units(raw):
            trial = cur + unit
            if draw.textlength(trial, font=f) > max_w and cur:
                lines.append(cur.rstrip())
                cur = unit.lstrip()
            else:
                cur = trial
        lines.append(cur.rstrip())
    return lines


def draw_lines(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    f: ImageFont.FreeTypeFont,
    xy: tuple[int, int],
    fill: str,
    line_gap: int = 14,
) -> int:
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=f, fill=fill)
        y += f.size + line_gap
    return y


def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([36, 36, W - 36, H - 36], radius=28, outline=LINE, width=3)
    return img, d


def pill(
    draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fg: str, bg: str
) -> int:
    f = font("zh", True, 34)
    pad_x, pad_y = 22, 10
    tw = int(draw.textlength(text, font=f))
    x, y = xy
    draw.rounded_rectangle([x, y, x + tw + pad_x * 2, y + 34 + pad_y * 2], radius=30, fill=bg)
    draw.text((x + pad_x, y + pad_y - 2), text, font=f, fill=fg)
    return y + 34 + pad_y * 2


def footer(draw: ImageDraw.ImageDraw, label: str, idx: int, total: int) -> None:
    f = font("zh", False, 28)
    y = H - 116
    draw.text((MARGIN, y), label, font=f, fill=SUB)
    brand = "Bruce 专属口语强化包"
    bx = W - MARGIN - int(draw.textlength(brand, font=f))
    draw.text((bx, y), brand, font=f, fill=SUB)
    dot_r, gap = 7, 26
    x0 = (W - total * gap) // 2
    for i in range(total):
        cx = x0 + i * gap + dot_r
        color = INK if i == idx else LINE
        draw.ellipse([cx - dot_r, y - 2, cx + dot_r, y + 12], fill=color)


def card_error(idx: int, wrong: str, right: str, rule: str, src: str) -> Image.Image:
    img, d = canvas()
    d.text((MARGIN, 92), f"错误急诊室 · 第 {idx} 伤口", font=font("zh", True, 36), fill=INK)
    d.line([MARGIN, 150, W - MARGIN, 150], fill=LINE, width=2)

    f_en_b = font("en", True, 46)
    max_w = W - MARGIN * 2
    y = pill(d, (MARGIN, 200), "你说过的", "#FFFFFF", RED_BG)
    y = draw_lines(d, wrap(d, wrong, f_en_b, max_w), f_en_b, (MARGIN, y + 18), RED) + 34

    cx = W // 2
    d.polygon([(cx - 26, y), (cx + 26, y), (cx, y + 34)], fill=SUB)
    y += 62

    y = pill(d, (MARGIN, y), "母语者说的", "#FFFFFF", GREEN_BG)
    y = draw_lines(d, wrap(d, right, f_en_b, max_w), f_en_b, (MARGIN, y + 18), GREEN) + 48

    d.line([MARGIN, y, W - MARGIN, y], fill=LINE, width=2)
    y += 34
    d.text((MARGIN, y), "一句规则", font=font("zh", True, 40), fill=AMBER)
    y += 66
    f_rule = font("zh", False, 38)
    draw_lines(d, wrap(d, rule, f_rule, max_w), f_rule, (MARGIN, y), INK)

    footer(d, src, idx - 1, 10)
    return img


def card_chunk(idx: int, chunk: str, meaning: str, demo: str, src: str) -> Image.Image:
    img, d = canvas()
    d.text((MARGIN, 92), f"语块军火库 · No.{idx}", font=font("zh", True, 36), fill=INK)
    d.line([MARGIN, 150, W - MARGIN, 150], fill=LINE, width=2)

    max_w = W - MARGIN * 2
    f_chunk = font("en", True, 60)
    y = draw_lines(d, wrap(d, chunk, f_chunk, max_w), f_chunk, (MARGIN, 240), INK, 18) + 44
    f_zh = font("zh", False, 40)
    y = draw_lines(d, wrap(d, meaning, f_zh, max_w), f_zh, (MARGIN, y), AMBER) + 60

    d.line([MARGIN, y, W - MARGIN, y], fill=LINE, width=2)
    y += 40
    y = pill(d, (MARGIN, y), "母语者示范", "#FFFFFF", GREEN_BG)
    f_demo = font("en", False, 44)
    draw_lines(d, wrap(d, demo, f_demo, max_w), f_demo, (MARGIN, y + 20), GREEN)

    footer(d, src, idx - 1, 8)
    return img


def _box(d: ImageDraw.ImageDraw, x0: int, y0: int, x1: int, y1: int, r: int) -> None:
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill="#FFFFFF", outline=LINE, width=2)


def card_area() -> Image.Image:
    img, d = canvas()
    d.text((MARGIN, 92), "AREA 万能扩答框架", font=font("zh", True, 56), fill=INK)
    d.text((MARGIN, 172), "任何 Part 1 题，四句话，二十秒。", font=font("zh", False, 34), fill=SUB)
    d.line([MARGIN, 232, W - MARGIN, 232], fill=LINE, width=2)

    rows = [
        ("A", "Answer 先给答案", "第一句直接回答，别绕圈", "Happy music, no contest."),
        ("R", "Reason 给理由", "一句话说清为什么", "Music is how I set my mood."),
        ("E", "Example 给例子", "必须是自己的真实例子", "Every morning I put on something upbeat."),
        ("A", "Attitude 给态度", "加一句感受，收出个人味", "Music is a tool, not entertainment."),
    ]
    y = 258
    f_letter = font("en", True, 48)
    f_head = font("zh", True, 36)
    f_desc = font("zh", False, 28)
    f_demo = font("en", False, 30)
    for letter, head, desc, demo in rows:
        _box(d, MARGIN, y, W - MARGIN, y + 200, 20)
        d.rounded_rectangle([MARGIN + 24, y + 24, MARGIN + 118, y + 118], radius=18, fill=AMBER_BG)
        d.text((MARGIN + 71, y + 71), letter, font=f_letter, fill=AMBER, anchor="mm")
        d.text((MARGIN + 146, y + 28), head, font=f_head, fill=INK)
        d.text((MARGIN + 146, y + 76), desc, font=f_desc, fill=SUB)
        d.text((MARGIN + 146, y + 130), demo, font=f_demo, fill=GREEN)
        y += 216
    footer(d, "示范取自 EP4 你的音乐题答案", 0, 1)
    return img


def card_poster() -> Image.Image:
    img, d = canvas()
    d.text((MARGIN, 92), "你的十大高频伤口", font=font("zh", True, 52), fill=INK)
    d.text((MARGIN, 168), "全部来自你的真实转写，一伤口一修复。",
           font=font("zh", False, 32), fill=SUB)
    d.line([MARGIN, 226, W - MARGIN, 226], fill=LINE, width=2)

    rows = [
        ("可数名词", "too much options -> too many options"),
        ("三单漏 s", "technology have changed -> has changed"),
        ("完成时分词", "I have sing -> I've sung"),
        ("he/she 混淆", "he spoiled me(妈妈) -> she spoiled me"),
        ("sceneries 当情况", "in specific sceneries -> situations"),
        ("learn knowledge", "中式直译 -> pick up knowledge"),
        ("转折只有 but", "That said, ... 让一步再扳回来"),
        ("you know 依赖", "That's a good question. Let me think..."),
        ("suggest 句型", "suggest them to learn -> suggest they learn"),
        ("depends 从句", "depends how the... -> depends on how well..."),
    ]
    y = 246
    f_no = font("en", True, 34)
    f_head = font("zh", True, 34)
    f_fix = font("zh", False, 26)
    for i, (head, fix) in enumerate(rows, 1):
        _box(d, MARGIN, y, W - MARGIN, y + 84, 16)
        d.text((MARGIN + 30, y + 22), f"{i:02d}", font=f_no, fill=RED)
        d.text((MARGIN + 106, y + 12), head, font=f_head, fill=INK)
        d.text((MARGIN + 106, y + 50), fix, font=f_fix, fill=GREEN)
        y += 94
    footer(d, "EP1-EP5 每集狙击其中 2-3 个", 0, 1)
    return img


def card_plan() -> Image.Image:
    img, d = canvas()
    d.text((MARGIN, 92), "14 天间隔复习计划", font=font("zh", True, 52), fill=INK)
    d.text((MARGIN, 168), "1-2-4-7-14 间隔重现；8 秒窗口必须出声。",
           font=font("zh", False, 32), fill=SUB)
    d.line([MARGIN, 226, W - MARGIN, 226], fill=LINE, width=2)

    days = [
        ("D1", "EP1 + 卡A01-A02"),
        ("D2", "EP1 重听 + EP2 + 卡A03-A05"),
        ("D3", "EP2 重听 + EP3 + 卡B01-B02"),
        ("D4", "EP3 重听 + EP4 + 卡A06-A07"),
        ("D5", "EP4 重听 + EP5 + 卡B03-B05"),
        ("D6", "EP6 影子跟读（第一轮）"),
        ("D7", "EP7 热身 + EP1/EP2 检索自测"),
        ("D8", "EP6 第二轮 + 卡A08-A10"),
        ("D9", "EP7 热身 + 卡B06-B08"),
        ("D10", "EP3 重听（Part3 间隔重现）"),
        ("D11", "EP6 第三轮（目标：不看稿）"),
        ("D12", "EP7 + AREA 自测随机 3 题"),
        ("D13", "EP5 重听 + 跟读"),
        ("D14", "随机总复习 + 卡C2 自测"),
    ]
    col_w = (W - MARGIN * 2 - 40) // 2
    y0 = 258
    row_h = 128
    f_day = font("en", True, 40)
    f_task = font("zh", False, 31)
    for i, (day, task) in enumerate(days):
        col, row = divmod(i, 7)
        x = MARGIN + col * (col_w + 40)
        y = y0 + row * row_h
        _box(d, x, y, x + col_w, y + 108, 16)
        d.text((x + 24, y + 16), day, font=f_day, fill=AMBER)
        for j, line in enumerate(wrap(d, task, f_task, col_w - 48 - 96)[:2]):
            d.text((x + 118, y + 20 + j * 40), line, font=f_task, fill=INK)
    footer(d, "贴着遗忘曲线排的，别跳天", 0, 1)
    return img


def card_guide() -> Image.Image:
    img, d = canvas()
    d.text((MARGIN, 92), "这套材料怎么用", font=font("zh", True, 52), fill=INK)
    d.line([MARGIN, 170, W - MARGIN, 170], fill=LINE, width=2)
    steps = [
        ("1", "先读《00_START_HERE》", "3 分钟。了解自己的十大伤口，听的时候才有靶子。"),
        ("2", "每天一集正课（EP1-EP5）", "听完=学会是幻觉。8 秒提示音窗口必须开口出声。"),
        ("3", "影子跟读（EP6）", "一句一停，模仿节奏和连读，不是背单词。"),
        ("4", "出门前热身（EP7）", "11 连检索。考试当天早上必做。"),
        ("5", "图卡当壁纸轮播", "A 卡每天 2 张；B 卡隔天复看一次，看时读出声。"),
    ]
    y = 220
    f_no = font("en", True, 44)
    f_head = font("zh", True, 40)
    f_desc = font("zh", False, 32)
    for no, head, desc in steps:
        _box(d, MARGIN, y, W - MARGIN, y + 168, 20)
        d.ellipse([MARGIN + 28, y + 48, MARGIN + 108, y + 128], fill=AMBER_BG)
        d.text((MARGIN + 68, y + 88), no, font=f_no, fill=AMBER, anchor="mm")
        d.text((MARGIN + 136, y + 34), head, font=f_head, fill=INK)
        d.text((MARGIN + 136, y + 92), desc, font=f_desc, fill=SUB)
        y += 188
    d.text((W // 2, y + 8), "只听不开口 = 白听", font=font("zh", True, 40), fill=RED, anchor="ma")
    footer(d, "配套音频在 audio/ 目录", 0, 1)
    return img


ERRORS = [
    (
        "There are too much options.",
        "There are too many options.",
        "options 可数，用 many 不用 much；不可数（information/advice）才用 much。",
        "来自 EP1",
    ),
    (
        "every students will learn English",
        "every student learns English",
        "every 永远接单数名词，动词也跟着用单数。",
        "来自 EP1",
    ),
    (
        "technology have changed our life",
        "Technology has changed our lives.",
        "单数主语配 has/does/goes；泛指生活用 lives 更自然。",
        "来自 EP1",
    ),
    (
        "I have sing some songs",
        "I've sung some songs.",
        "完成时 = have/has + 过去分词（sing-sang-sung）。",
        "来自 EP1",
    ),
    (
        "he kind of spoiled me（说的是妈妈）",
        "She kind of spoiled me.",
        "妈妈、女老师、女歌手一律 she；讲故事前先想好性别。",
        "来自 EP1",
    ),
    (
        "in some specific sceneries",
        "in some specific situations",
        "scenery 只指自然风景；\"情况\"是 situation / scenario。",
        "来自 EP2",
    ),
    (
        "I learn knowledge from TV shows",
        "I pick up a lot from TV shows.",
        "learn knowledge 是中式直译；母语者说 pick up / acquire。",
        "来自 EP2",
    ),
    (
        "I'm not kind of shopping person",
        "I'm not much of a shopping person.",
        "not much of a...= 算不上……的人；一句话立住人设。",
        "来自 EP2",
    ),
    (
        "it depends how the children self-disciplining ability developed",
        "It depends on how well a kid can discipline themselves.",
        "depend on + how/whether + 完整从句，别往里塞名词短语。",
        "来自 EP3",
    ),
    (
        "computer science can get a high-paid job",
        "coding leads to well-paid jobs",
        "高薪工作 = well-paid / high-paying job。",
        "来自 EP5",
    ),
]

CHUNKS = [
    (
        "I'm not much of a ... person.",
        "算不上是……的人",
        "I'm not much of a city person.",
        "来自 EP2 · 人设句",
    ),
    (
        "Off the top of my head, ...",
        "不加思索地讲（体面买 5 秒）",
        "Off the top of my head, I'd say twice a year.",
        "来自 EP2 · 卡壳救星",
    ),
    (
        "That said, ...",
        "话虽如此（先让一步再扳回）",
        "That said, I don't think teachers will disappear.",
        "来自 EP3 · Part3 让步",
    ),
    (
        "I'd go as far as to say that...",
        "我甚至敢说（升级观点强度）",
        "I'd go as far as to say that AI will reshape education.",
        "来自 EP3 · 亮剑句",
    ),
    (
        "It really depends on how...",
        "这取决于……（Part3 收尾骨架）",
        "It really depends on how well a kid can discipline themselves.",
        "来自 EP3 · 思辨句",
    ),
    (
        "That's a good question. Let me think...",
        "买时间三件套",
        "That's a good question. How should I put this...",
        "来自 EP4 · 替代 you know",
    ),
    (
        "make the switch from A to B",
        "从 A 转型到 B",
        "I made the switch from chemistry to computer science.",
        "来自 EP5 · 转变万能句",
    ),
    (
        "It felt (completely) surreal.",
        "震撼到不真实",
        "The moment I walked in, it felt completely surreal.",
        "来自 EP5 · 震撼万能句",
    ),
]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files: list[tuple[Path, Image.Image]] = []
    for i, (wrong, right, rule, src) in enumerate(ERRORS, 1):
        files.append((OUT_DIR / f"A{i:02d}_伤口修补.png", card_error(i, wrong, right, rule, src)))
    for i, (chunk, meaning, demo, src) in enumerate(CHUNKS, 1):
        files.append((OUT_DIR / f"B{i:02d}_语块.png", card_chunk(i, chunk, meaning, demo, src)))
    extras = [
        ("C1_AREA扩答框架.png", card_area()),
        ("C2_十大伤口总览.png", card_poster()),
        ("C3_14天计划.png", card_plan()),
        ("C4_使用指南.png", card_guide()),
    ]
    files.extend((OUT_DIR / name, img) for name, img in extras)
    for path, img in files:
        img.save(path)
        print(f"  {path.name}")
    print(f"共 {len(files)} 张卡片 -> {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
