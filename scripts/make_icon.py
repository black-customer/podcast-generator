#!/usr/bin/env python
"""从选定的品牌母版生成 Web、Windows 和 Android 图标（需 Pillow）。"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

BASE = Path(__file__).resolve().parent.parent
SOURCE = BASE / "docs" / "design" / "icon-b-master.png"
WEB_ICONS = BASE / "web" / "icons"
ANDROID_RES = BASE / "mobile" / "android" / "app" / "src" / "main" / "res"
BLUE = (14, 104, 249)
NAVY = (11, 23, 51)
ANDROID_DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}


def rounded_icon(icon: Image.Image, size: int) -> Image.Image:
    """为旧版 Android 启动器生成带抗锯齿透明圆角的圆形图标。"""
    oversample = 4
    large = icon.resize((size * oversample, size * oversample), Image.Resampling.LANCZOS)
    mask = Image.new("L", large.size)
    ImageDraw.Draw(mask).ellipse((0, 0, large.width - 1, large.height - 1), fill=255)
    large.putalpha(mask)
    return large.resize((size, size), Image.Resampling.LANCZOS)


def foreground_mark(source: Image.Image) -> Image.Image:
    """把蓝底母版的白色对话形和深色声波拆成自适应图标前景。"""
    red, _, blue = source.split()
    white_alpha = red.point(
        lambda value: max(0, min(255, round((value - BLUE[0]) * 255 / (255 - BLUE[0]))))
        if value > BLUE[0] + 18 else 0
    )
    navy_alpha = blue.point(
        lambda value: max(0, min(255, round((BLUE[2] - value) * 255 / (BLUE[2] - NAVY[2]))))
        if value < BLUE[2] - 18 else 0
    )
    white = Image.new("RGBA", source.size, "white")
    white.putalpha(white_alpha)
    navy = Image.new("RGBA", source.size, NAVY)
    navy.putalpha(navy_alpha)
    white.alpha_composite(navy)
    bounds = ImageChops.lighter(white_alpha, navy_alpha).getbbox()
    if bounds is None:
        raise ValueError("母版中没有识别到图案")
    return white.crop(bounds)


def adaptive_foreground(mark: Image.Image, size: int) -> Image.Image:
    """把图案收进 Android 自适应图标的中央安全区。"""
    foreground = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    fitted = mark.copy()
    limit = round(size * 0.58)
    fitted.thumbnail((limit, limit), Image.Resampling.LANCZOS)
    foreground.alpha_composite(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
    return foreground


def compact_square(source: Image.Image) -> Image.Image:
    """电脑任务栏和浏览器标签需要比启动器更饱满的小尺寸图案。"""
    margin = round(source.width * 0.09)
    return source.crop((margin, margin, source.width - margin, source.height - margin))


def main() -> None:
    source = Image.open(SOURCE).convert("RGB")
    if source.width != source.height:
        raise ValueError("图标母版必须为正方形")

    compact = compact_square(source)
    for size in (32, 192, 512):
        master = compact if size == 32 else source
        master.resize((size, size), Image.Resampling.LANCZOS).save(
            WEB_ICONS / f"icon-{size}.png", optimize=True
        )

    compact.resize((256, 256), Image.Resampling.LANCZOS).save(
        BASE / "app.ico", format="ICO", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    )

    mark = foreground_mark(source)
    for density, scale in ANDROID_DENSITIES.items():
        output = ANDROID_RES / f"mipmap-{density}"
        legacy_size = round(48 * scale)
        icon = source.resize((legacy_size, legacy_size), Image.Resampling.LANCZOS)
        icon.save(output / "ic_launcher.png", optimize=True)
        rounded_icon(source, legacy_size).save(output / "ic_launcher_round.png", optimize=True)
        adaptive_foreground(mark, round(108 * scale)).save(
            output / "ic_launcher_foreground.png", optimize=True
        )

    print("图标已生成：Web PNG、Windows ICO、Android 各密度启动图标")


if __name__ == "__main__":
    main()
