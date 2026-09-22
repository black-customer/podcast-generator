"""单题速通工作流合成器：kit JSON -> 1 音频 + 4 卡片 + 速览 HTML（--media 加媒体包装）。

只做模板装配 + TTS + 出图 + 程序化质量门，不做内容判断（判断性工作见 README §3）。
复用 bruce_kit 一期的块引擎（提示音/缓存/响度）与卡片原语，保证学习者体验一致。
"""
import argparse
import html
import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "scripts"))

from generate_bruce_kit_cards import (  # noqa: E402
    AMBER,
    AMBER_BG,
    GREEN,
    GREEN_BG,
    INK,
    LINE,
    MARGIN,
    PAPER,
    RED,
    RED_BG,
    SUB,
    W,
    _units,
    canvas,
    draw_lines,
    font,
    pill,
    wrap,
)
from generate_bruce_learning_kit import _blocks_to_entries  # noqa: E402

from server.audio import concat_mp3, probe_duration  # noqa: E402
from server.config import load_settings  # noqa: E402

OUT_ROOT = BASE_DIR / "glm-workflow" / "output"

DUR_MIN_S, DUR_MAX_S = 90, 240
RETRIEVAL_WINDOW_S = 8.0
MAX_FIXES, MAX_CHUNKS = 3, 2


def validate(kit: dict) -> list[str]:
    errors: list[str] = []
    for field in ("id", "question", "question_zh", "original_answer", "model_answer",
                  "takeaway", "audio"):
        if not kit.get(field):
            errors.append(f"缺少必填字段: {field}")
    fixes = kit.get("fixes") or []
    if not 1 <= len(fixes) <= MAX_FIXES:
        errors.append(f"fixes 必须在 1-{MAX_FIXES} 条之间（反压倒性契约），当前 {len(fixes)}")
    chunks = kit.get("chunks") or []
    if not 1 <= len(chunks) <= MAX_CHUNKS:
        errors.append(f"chunks 必须在 1-{MAX_CHUNKS} 个之间（反压倒性契约），当前 {len(chunks)}")
    for i, fix in enumerate(fixes, 1):
        for key in ("wrong", "right", "rule"):
            if not fix.get(key):
                errors.append(f"fixes[{i}] 缺少 {key}")
    for i, chunk in enumerate(chunks, 1):
        for key in ("chunk", "meaning_zh", "transfer_zh", "transfer"):
            if not chunk.get(key):
                errors.append(f"chunks[{i}] 缺少 {key}")
    if not kit.get("model_segments"):
        errors.append("缺少 model_segments（模范答案卡的语块高亮分段）")
    return errors


def build_audio_blocks(kit: dict) -> list[dict]:
    a = kit["audio"]
    blocks: list[dict] = []
    lines1: list[list[str]] = [["a", a["hook_zh"]], ["a", kit["question"]]]
    for fix in kit["fixes"][:2]:
        lines1.append(["a", f'{a["contrast_intro_zh"]}{fix["wrong"]}。{a["contrast_mid_zh"]}'])
        lines1.append(["b", fix["right"]])
        lines1.append(["a", fix["rule"]])
    blocks.append({"t": "dlg", "lines": lines1})

    chunks = kit["chunks"]
    count_zh = "一" if len(chunks) == 1 else "两"
    lines2: list[list[str]] = [
        ["a", f"这段回答里值得带走的语块只有{count_zh}个，但都能迁移。第一个："],
        ["b", chunks[0]["chunk"]],
        ["a", f'{chunks[0]["meaning_zh"]}。{chunks[0]["transfer_zh"]}'],
        ["b", chunks[0]["transfer"]],
    ]
    if len(chunks) > 1:
        lines2 += [
            ["a", "第二个："],
            ["b", chunks[1]["chunk"]],
            ["a", f'{chunks[1]["meaning_zh"]}。{chunks[1]["transfer_zh"]}'],
            ["b", chunks[1]["transfer"]],
        ]
    lines2.append(["a", a["model_intro_zh"]])
    lines2.append(["b", kit["model_answer"]])
    blocks.append({"t": "dlg", "lines": lines2})

    # 检索指令必须在提示音窗口之前；带走句收尾在窗口之后。
    blocks.append({"t": "dlg", "lines": [["a", a["retrieval_zh"]]]})
    blocks.append({"t": "beep", "freq": 660, "dur": 0.25})
    blocks.append({"t": "sil", "sec": RETRIEVAL_WINDOW_S})
    blocks.append({"t": "beep", "freq": 880, "dur": 0.25})
    blocks.append({"t": "dlg", "lines": [
        ["a", a["takeaway_intro_zh"]],
        ["b", kit["takeaway"]],
        ["a", a["outro_zh"]],
    ]})
    return blocks


def render_audio(kit: dict, out_dir: Path, settings: dict) -> float:
    blocks = build_audio_blocks(kit)
    out_file = out_dir / "question_coach.mp3"
    entries = _blocks_to_entries(blocks, settings)
    concat_mp3(entries, out_file)
    return probe_duration(out_file)


def check_silence_windows(path: Path) -> int:
    """检索窗口程序化验证：全曲只应有一条 >=6s 的静音。"""
    proc = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "silencedetect=noise=-35dB:d=6", "-f", "null", "-"],
        capture_output=True, text=True, timeout=120,
    )
    return (proc.stderr or "").count("silence_start")


def _kit_footer(d: object, label: str, kit_id: str) -> None:
    f = font("zh", False, 28)
    y = 1350 - 116
    d.text((MARGIN, y), label, font=f, fill=SUB)
    brand = f"单题速通 · {kit_id}"
    bx = W - MARGIN - int(d.textlength(brand, font=f))
    d.text((bx, y), brand, font=f, fill=SUB)


def card_fix(kit: dict, fix: dict) -> object:
    img, d = canvas()
    d.text((MARGIN, 92), "错误急诊室", font=font("zh", True, 40), fill=INK)
    d.line([MARGIN, 152, W - MARGIN, 152], fill=LINE, width=2)
    max_w = W - MARGIN * 2
    f_en_b = font("en", True, 46)
    y = pill(d, (MARGIN, 210), "你说过的", "#FFFFFF", RED_BG)
    y = draw_lines(d, wrap(d, fix["wrong"], f_en_b, max_w), f_en_b, (MARGIN, y + 18), RED) + 40
    d.polygon([(W // 2 - 26, y), (W // 2 + 26, y), (W // 2, y + 34)], fill=SUB)
    y += 66
    y = pill(d, (MARGIN, y), "母语者说的", "#FFFFFF", GREEN_BG)
    y = draw_lines(d, wrap(d, fix["right"], f_en_b, max_w), f_en_b, (MARGIN, y + 18), GREEN) + 52
    d.line([MARGIN, y, W - MARGIN, y], fill=LINE, width=2)
    y += 36
    d.text((MARGIN, y), "一句规则", font=font("zh", True, 40), fill=AMBER)
    y += 68
    f_rule = font("zh", False, 38)
    draw_lines(d, wrap(d, fix["rule"], f_rule, max_w), f_rule, (MARGIN, y), INK)
    _kit_footer(d, "来自你自己的回答", kit["id"])
    return img


def card_chunk(kit: dict, chunk: dict, idx: int) -> object:
    img, d = canvas()
    d.text((MARGIN, 92), f"今天的语块 {idx}/{len(kit['chunks'])}",
           font=font("zh", True, 40), fill=INK)
    d.line([MARGIN, 152, W - MARGIN, 152], fill=LINE, width=2)
    max_w = W - MARGIN * 2
    f_chunk = font("en", True, 54)
    y = draw_lines(d, wrap(d, chunk["chunk"], f_chunk, max_w), f_chunk, (MARGIN, 220), INK, 16) + 44
    f_zh = font("zh", False, 38)
    y = draw_lines(d, wrap(d, chunk["meaning_zh"], f_zh, max_w), f_zh, (MARGIN, y), AMBER) + 56
    d.line([MARGIN, y, W - MARGIN, y], fill=LINE, width=2)
    y += 40
    y = pill(d, (MARGIN, y), "换个话题也会用", "#FFFFFF", GREEN_BG)
    f_demo = font("en", False, 44)
    y = draw_lines(d, wrap(d, chunk["transfer"], f_demo, max_w), f_demo, (MARGIN, y + 20), GREEN)
    f_zh2 = font("zh", False, 32)
    draw_lines(d, wrap(d, chunk["transfer_zh"], f_zh2, max_w), f_zh2, (MARGIN, y + 24), SUB)
    _kit_footer(d, "15 秒内能复述，才算带走", kit["id"])
    return img


def card_model(kit: dict) -> object:
    img, d = canvas()
    d.text((MARGIN, 92), "8.5 分模范答案（你的内容）", font=font("zh", True, 40), fill=INK)
    d.line([MARGIN, 152, W - MARGIN, 152], fill=LINE, width=2)
    max_w = W - MARGIN * 2
    f_q = font("en", True, 40)
    y = draw_lines(d, wrap(d, kit["question"], f_q, max_w), f_q, (MARGIN, 200), AMBER, 10) + 44
    d.line([MARGIN, y, W - MARGIN, y], fill=LINE, width=2)
    y += 40

    tokens: list[tuple[str, str, bool]] = []
    for seg_type, text in kit["model_segments"]:
        for unit in _units(text):
            tokens.append((unit, GREEN if seg_type == "c" else INK, seg_type == "c"))
    f_reg = font("en", False, 35)
    f_bold = font("en", True, 35)
    line_h = 50
    x = MARGIN
    for text, color, bold in tokens:
        f_cur = f_bold if bold else f_reg
        tw = int(d.textlength(text, font=f_cur))
        if text.isspace() and x == MARGIN:
            continue
        if x + tw > W - MARGIN and not text.isspace():
            x = MARGIN
            y += line_h
            if text.isspace():
                continue
        d.text((x, y), text, font=f_cur, fill=color)
        x += tw
    _kit_footer(d, "绿色 = 今天的语块；跟读三遍", kit["id"])
    return img


def card_cover(kit: dict) -> Image.Image:
    height = 1440
    img = Image.new("RGB", (W, height), PAPER)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([36, 36, W - 36, height - 36], radius=28, outline=LINE, width=3)
    pill(d, (MARGIN, 110), f'雅思 Part {kit["part"]} · Band 8.5 答案骨架', "#FFFFFF", AMBER_BG)
    f_title = font("zh", True, 78)
    y = draw_lines(
        d, wrap(d, kit["media"]["titles"][0], f_title, W - MARGIN * 2), f_title,
        (MARGIN, 280), INK, 20,
    ) + 80
    d.line([MARGIN, y, W - MARGIN, y], fill=LINE, width=2)
    y += 70
    y = pill(d, (MARGIN, y), "答案的第一句，就是这个", "#FFFFFF", GREEN_BG)
    f_chunk = font("en", True, 46)
    y = draw_lines(
        d, wrap(d, kit["chunks"][0]["chunk"], f_chunk, W - MARGIN * 2), f_chunk,
        (MARGIN, y + 24), GREEN, 12,
    ) + 90
    f_q = font("en", False, 40)
    draw_lines(d, wrap(d, kit["question"], f_q, W - MARGIN * 2), f_q, (MARGIN, y), SUB)
    f_brand = font("zh", True, 34)
    d.text((MARGIN, height - 140), "单题速通 · 跟着练，一道题打穿一道",
           font=f_brand, fill=INK)
    return img


def speedview_html(kit: dict, duration_s: float) -> str:
    esc = html.escape
    fixes_rows = "".join(
        f'<tr><td class="bad">{esc(f["wrong"])}</td>'
        f'<td class="good">{esc(f["right"])}</td><td>{esc(f["rule"])}</td></tr>'
        for f in kit["fixes"]
    )
    chunks_html = "".join(
        f'<div class="chunk"><div class="c">{esc(c["chunk"])}</div>'
        f'<div class="m">{esc(c["meaning_zh"])}</div>'
        f'<div class="t">迁移示范：<code>{esc(c["transfer"])}</code></div></div>'
        for c in kit["chunks"]
    )
    answer_html = "".join(
        f'<mark>{esc(text)}</mark>' if seg_type == "c" else esc(text)
        for seg_type, text in kit["model_segments"]
    )
    audio_label = (
        f"训练音频（{duration_s:.0f} 秒，听三遍）" if duration_s > 0 else "训练音频（合成中）"
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>速览 · {esc(kit["question_zh"])}</title><style>
body{{margin:0;background:#FAF6EE;color:#1F2937;line-height:1.8;
font-family:"Microsoft YaHei",system-ui,sans-serif;padding:32px 16px 80px}}
main{{max-width:820px;margin:0 auto}}
h1{{font-size:26px;margin:0 0 2px}}.q{{color:#B45309;font-weight:700;margin-bottom:20px}}
.card{{background:#fff;border:1px solid #D9CFBC;border-radius:14px;padding:16px 20px;margin:14px 0}}
audio{{width:100%;margin:8px 0}}table{{border-collapse:collapse;width:100%}}
td{{border-top:1px solid #EEE;padding:8px 6px;font-size:14px;vertical-align:top}}
.bad{{color:#C2410C}}.good{{color:#047857;font-weight:700}}
mark{{background:#E2F3EC;color:#047857;font-weight:700;padding:0 3px;border-radius:4px}}
.chunk .c{{font-weight:700;font-size:17px}}.chunk .m{{color:#B45309;font-size:14px}}
.chunk .t{{font-size:14px;color:#6B7280}}
code{{background:#F3EFE4;padding:1px 6px;border-radius:6px}}
.tk{{background:#FDEBE3;border-radius:12px;padding:12px 18px;font-weight:700}}
details summary{{cursor:pointer;color:#6B7280}}.tip{{font-size:13px;color:#6B7280}}
</style></head><body><main>
<h1>单题速览</h1>
<div class="q">Part {kit["part"]} · {esc(kit["question_zh"])}<br>{esc(kit["question"])}</div>
<div class="card"><b>{audio_label}</b>
<audio controls src="question_coach.mp3"></audio>
<div class="tip">第 1 遍只听懂；第 2 遍提示音后必须开口；第 3 遍影子跟读模范答案。</div></div>
<div class="card"><b>你的三处修复</b><table><tr><th style="text-align:left">你说过的</th>
<th style="text-align:left">母语者说的</th>
<th style="text-align:left">规则</th></tr>{fixes_rows}</table></div>
<div class="card"><b>今天的语块（{len(kit["chunks"])} 个）</b>{chunks_html}</div>
<div class="card"><b>8.5 分模范答案（绿色 = 语块）</b><p>{answer_html}</p></div>
<div class="tk">带走句：{esc(kit["takeaway"])}</div>
<div class="card"><details><summary>你的原始回答（存档）</summary>
<p>{esc(kit["original_answer"])}</p></details></div>
<p class="tip">由 glm-workflow 单题速通工作流生成 · 重学只需重听这一条音频。</p>
</main></body></html>"""


def media_pack_md(kit: dict) -> str:
    script_en = "\n".join(
        f"  **{sp.upper()}**：{text}" for sp, text in kit["media"]["script_en"]
    )
    script_zh = "\n".join(
        f"  **{sp.upper()}**：{text}" for sp, text in kit["media"]["script_zh_variant"]
    )
    titles = "\n".join(f"{i}. {t}" for i, t in enumerate(kit["media"]["titles"], 1))
    tags = " ".join("#" + t.strip() for t in kit["media"]["tags"])
    return f"""# 媒体包装包 · {kit["question_zh"]}

> 阶段二产物：全部内容来自阶段一教学包，不新造知识点。封面卡 = cover.png。

## 候选标题（A/B 测试用）
{titles}

## 纯英文双主持脚本（45-60 秒，主形态）
{script_en}

## 中英结合变体（大众流量版，可选）
{script_zh}

## 发布文案
{kit["media"]["caption_zh"]}

## 标签
{tags}

## 发布提示
- 封面即 cover.png；标题 A/B 各发一次测点击率
- 视频只拆 1 个语块（It really depends on how...），完整答案引导到主页音频
- 评论区置顶带走句，引导"交作业"
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="单题速通工作流合成器")
    parser.add_argument("--kit", required=True, help="kit JSON 路径")
    parser.add_argument("--media", action="store_true", help="同时产出阶段二媒体包装包")
    parser.add_argument("--force", action="store_true", help="音频已存在也重新合成")
    parser.add_argument(
        "--skip-audio", action="store_true",
        help="跳过 TTS 只出文字/图片产物（TTS 网络不可用时先迭代内容）",
    )
    args = parser.parse_args()

    kit_path = Path(args.kit)
    kit = json.loads(kit_path.read_text(encoding="utf-8"))
    errors = validate(kit)
    if errors:
        print("kit JSON 未通过契约检查：", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 2

    settings = load_settings()
    if not (settings.get("fish_api_key") or "").strip():
        print("未配置 fish_api_key，拒绝静默 dry-run。", file=sys.stderr)
        return 2

    out_dir = OUT_ROOT / kit["id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "question_coach.mp3"

    if out_file.exists() and not args.force and not args.skip_audio:
        print(f"音频已存在，跳过合成（--force 重合成）: {out_file}")
        duration = probe_duration(out_file)
    elif args.skip_audio:
        print("!! --skip-audio：跳过 TTS，先产出文字/图片产物；交付前需重跑补音频")
        duration = 0.0
    else:
        print("合成训练音频...")
        duration = render_audio(kit, out_dir, settings)
    print(f"  音频时长 {duration:.1f}s（契约 {DUR_MIN_S}-{DUR_MAX_S}s）")

    print("绘制卡片...")
    cards = [
        (out_dir / "01_错误修补.png", card_fix(kit, kit["fixes"][0])),
        (out_dir / "02_语块A.png", card_chunk(kit, kit["chunks"][0], 1)),
    ]
    if len(kit["chunks"]) > 1:
        cards.append((out_dir / "03_语块B.png", card_chunk(kit, kit["chunks"][1], 2)))
    cards.append((out_dir / "04_模范答案.png", card_model(kit)))
    if args.media:
        cards.append((out_dir / "05_封面.png", card_cover(kit)))
    for path, img in cards:
        img.save(path)

    (out_dir / "速览.html").write_text(speedview_html(kit, duration), encoding="utf-8")
    if args.media:
        (out_dir / "媒体包装包.md").write_text(media_pack_md(kit), encoding="utf-8")

    if args.skip_audio and not out_file.exists():
        print(f"完成（无音频，交付前需重跑） -> {out_dir}")
        return 0

    failed = False
    if not DUR_MIN_S <= duration <= DUR_MAX_S:
        print("  !! 时长超出契约区间", file=sys.stderr)
        failed = True
    windows = check_silence_windows(out_file)
    if windows != 1:
        print(f"  !! 检索静音窗口数量为 {windows}，应为 1", file=sys.stderr)
        failed = True
    print(f"完成 -> {out_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
