#!/usr/bin/env python
"""生成应用图标 app.ico（项目根，桌面快捷方式用）。

自绘设计：暗色圆角方底 + 荧光绿麦克风胶囊 + 白色支架 + 右侧声波弧——
与应用 UI 品牌一致（#1ed760 主色 / #121212 暗底，播客主题）。
需要 Pillow（仅生成时用，运行时无依赖）：pip install pillow
输出多尺寸（256→16）单文件 ico；另出 data/.tmp/app_icon_preview.png 供目检。
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "app.ico"
PREVIEW = BASE / "data" / ".tmp" / "app_icon_preview.png"
S = 1024  # 母版尺寸

BG_TOP = (38, 40, 38)      # 圆角底渐变上端
BG_BOT = (8, 10, 9)        # 下端
GREEN = (30, 215, 96)      # 应用主色 #1ed760
GREEN_DIM = (24, 160, 72)  # 声波外弧（稍暗）
WHITE = (240, 248, 243)
RADIUS = 220


def rounded_gradient() -> Image.Image:
    """暗色竖向渐变 + 圆角矩形蒙版，透明四角。"""
    grad = Image.new("RGB", (S, S))
    px = grad.load()
    for y in range(S):
        t = y / (S - 1)
        c = tuple(round(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3))
        for x in range(S):
            px[x, y] = c
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=RADIUS, fill=255)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(grad, (0, 0), mask)
    return icon


def draw_mark(img: Image.Image) -> None:
    """麦克风主体：胶囊 + 支架，偏左；声波两道弧在右。"""
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    # 麦克风胶囊（完整药丸形）
    cx = 420
    cap_w, cap_top, cap_bot = 300, 150, 620
    d.rounded_rectangle(
        [cx - cap_w // 2, cap_top, cx + cap_w // 2, cap_bot],
        radius=cap_w // 2, fill=GREEN,
    )
    # 胶囊内三道横向格栅（深绿，增加质感，小尺寸自然消失）
    for i, yy in enumerate((268, 360, 452)):
        half = 118 if i == 1 else 104
        d.rounded_rectangle(
            [cx - half, yy - 17, cx + half, yy + 17], radius=17, fill=(18, 120, 48, 255)
        )

    # U 型支架（包住胶囊下半的粗弧线）
    yoke_box = [cx - 220, 210, cx + 220, 640]
    d.arc(yoke_box, start=10, end=170, fill=WHITE, width=46)

    # 立杆与底座
    d.rounded_rectangle([cx - 23, 620, cx + 23, 800], radius=23, fill=WHITE)
    d.rounded_rectangle([cx - 120, 776, cx + 120, 844], radius=34, fill=WHITE)

    # 声波弧（右侧两道，弧心对准胶囊中心）
    for r, w, col in ((300, 42, GREEN), (400, 36, GREEN_DIM)):
        d.arc([cx + 40 - r, 385 - r, cx + 40 + r, 385 + r],
              start=-52, end=52, fill=col, width=w)

    img.alpha_composite(layer)


def main() -> int:
    master = rounded_gradient()
    draw_mark(master)

    sizes = [256, 128, 64, 48, 32, 16]
    master.resize((256, 256), Image.LANCZOS).save(
        OUT, format="ICO", sizes=[(n, n) for n in sizes]
    )
    PREVIEW.parent.mkdir(parents=True, exist_ok=True)
    master.resize((512, 512), Image.LANCZOS).save(PREVIEW)
    print(f"图标已生成: {OUT}（{', '.join(map(str, sizes))}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
