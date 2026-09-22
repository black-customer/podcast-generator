"""Stage 2：把单题教学包包装成可发布的竖屏作品。

与 Stage 1 的关键区别：Stage 1 服务「他学得完」，这里服务「陌生人愿意看完」。
所以这里只允许讲**一个**啊哈点——一份教学包里的三个纠错点，发布时砍到只剩一个。

任何一步失败都不阻塞出片：TTS 不通就只出封面和文案，Minimax 没起就只出静态封面。
"""
# ruff: noqa: E501  # HTML/CSS 模板与规则字符串是数据，折行会看不清

from __future__ import annotations

import argparse
import json
import sys
from html import escape as E
from pathlib import Path

from . import engine as En
from . import minimax

VW, VH = 1080, 1920

SCENE_CSS = """
*{box-sizing:border-box;margin:0;padding:0}
::-webkit-scrollbar{display:none}
body{font-family:"Segoe UI Variable Text","Segoe UI","Microsoft YaHei",system-ui,sans-serif;
 background:#07090d;color:#fff;-webkit-font-smoothing:antialiased}
.c{width:1080px;height:1920px;padding:120px 76px;display:flex;flex-direction:column;position:relative;
 overflow:hidden;background:radial-gradient(1200px 700px at 92% -6%,rgba(232,163,61,.20),
 transparent 60%),radial-gradient(1000px 640px at -10% 106%,rgba(77,208,199,.14),transparent 62%),#07090d}
.kicker{font-size:30px;letter-spacing:.24em;text-transform:uppercase;color:#E8A33D;font-weight:700}
.big{font-size:96px;line-height:1.1;font-weight:800;letter-spacing:-.02em;margin-top:44px}
.mid{font-size:60px;line-height:1.28;font-weight:700;margin-top:36px;color:#eef2f6}
.en{font-size:70px;line-height:1.3;font-weight:800;margin-top:40px;word-spacing:3px}
.wrong{color:#e28c8c;text-decoration:line-through;text-decoration-thickness:6px;
 text-decoration-color:#b8504f}
.right{color:#4DD0C7}
.sub{font-size:38px;line-height:1.55;color:#93a0af;margin-top:34px;font-weight:500}
.spacer{margin-top:auto}
.badge{display:inline-block;font-size:30px;color:#0b0e13;background:#E8A33D;font-weight:800;
 padding:12px 26px;border-radius:999px;letter-spacing:.04em}
.cta{font-size:64px;line-height:1.3;font-weight:800;margin-top:40px}
.tag{font-size:32px;color:#5d6875;letter-spacing:.14em;margin-top:26px}
"""


def scene(markup_body: str) -> str:
    return f"<!doctype html><meta charset='utf-8'><style>{SCENE_CSS}</style><body><div class='c'>{markup_body}</div>"


def pick_aha(lesson: dict) -> tuple[dict, str]:
    """一条视频只讲一个点。publish.aha_fix_id 是编辑判断，缺省退回第一处。"""
    want = (lesson.get("publish") or {}).get("aha_fix_id")
    for f in lesson["fixes"]:
        if f["id"] == want:
            return f, "publish.aha_fix_id"
    return lesson["fixes"][0], "（publish.aha_fix_id 缺省，退回第一处）"


def build_scenes(lesson: dict, aha: dict) -> list[dict]:
    """六拍结构，见 skills/one-question-creator/SKILL.md。"""
    chunk = next((c for c in lesson["chunks"] if c["chunk"] in " ".join(lesson["model_answer"])),
                 lesson["chunks"][0])
    hook_zh = (lesson.get("publish") or {}).get(
        "hook_zh", f"这句英文，{len(lesson['fixes'])} 个人里 {max(2, len(lesson['fixes']))} 个都说错")
    return [
        {"id": "hook", "seconds": 3, "narration": None, "html": scene(
            f"<div class='kicker'>IELTS Speaking</div><div class='big'>{E(hook_zh)}</div>"
            f"<div class='spacer'></div><div class='tag'>雅思考场真实回答</div>")},
        {"id": "wrong", "seconds": 9, "narration": [("a", "Listen to this real answer."),
                                                    ("a", aha["original"])], "html": scene(
            f"<div class='kicker'>考生原话</div><div class='en wrong'>{aha['original']}</div>"
            f"<div class='sub'>{E(aha['label_zh'])}</div>")},
        {"id": "right", "seconds": 18, "narration": [("b", aha["fixed"]), ("a", aha["rule_zh"])],
         "html": scene(f"<div class='kicker'>母语者这么说</div>"
                       f"<div class='en right'>{aha['fixed']}</div>"
                       f"<div class='sub'>{aha['rule_zh']}</div>")},
        {"id": "chunk", "seconds": 20, "narration": [("a", f"记住这四个字：{chunk['chunk']}。"),
                                                     ("b", chunk["example"])],
         "html": scene(f"<div class='kicker'>带走这个</div><div class='en right'>{chunk['chunk']}</div>"
                       f"<div class='big' style='font-size:64px;margin-top:26px'>{chunk['zh']}</div>"
                       f"<div class='sub'>{E(chunk['example'])}</div>")},
        {"id": "ask", "seconds": 12, "narration": [("a", lesson["question"])], "html": scene(
            f"<div class='kicker'>轮到你了</div><div class='mid'>{lesson['question']}</div>"
            f"<div class='sub'>三秒。在心里答一遍，别出声也行。</div>")},
        {"id": "cta", "seconds": 6, "narration": [("a", "把你的答案打在评论区。")], "html": scene(
            "<div class='badge'>评论区写下来</div><div class='cta'>你答的那句，<br>"
            "和这条视频里<br>改好的那句<br>差多远？</div>"
            "<div class='spacer'></div><div class='tag'>IELTS POD · 单题精练</div>")},
    ]


def cover_markup(lesson: dict, aha: dict, ratio: str) -> str:
    big = "112px" if ratio == "3x4" else "96px"
    # 上下各留一个 spacer，让两句英文落在画面中部：竖屏封面顶部 1/3 会被平台标题栏压住
    return scene(f"<div class='spacer'></div><div class='kicker'>雅思考生真实回答</div>"
                 f"<div class='en wrong' style='font-size:{big}'>{aha['original']}</div>"
                 f"<div class='en right' style='font-size:{big};margin-top:56px'>{E(aha['core'])}</div>"
                 f"<div class='spacer'></div>"
                 f"<div class='sub'>一处改动，6 分到 7 分</div>")


def publish_copy(lesson: dict, aha: dict, chunk: dict) -> str:
    # 这是 markdown，不是 HTML：这里一律不转义，否则正文里会出现 &#x27;
    titles = [
        f"雅思考生原话「{aha['original']}」——考官听懂了，但会记你一笔",
        "「我没有最喜欢的老师」用英语说，多说一个词就掉分",
        f"口语 6 分和 7 分的差距，可能只是 {chunk['chunk']} 这几个词",
    ]
    return f"""# 发布物料 · {lesson['question']}

> 脱敏检查：正文与口播里**不得**出现真实姓名、学校、城市。下面所有文案均已匿名化为「雅思考生」。

## 标题候选

1. {titles[0]}
2. {titles[1]}
3. {titles[2]}

## 正文

雅思考生真实回答里的一句：

> {aha['original']}

考官听懂了，但会当场记下语法错误。改成：

> {aha['fixed']}

差别在哪：**{aha['rule_zh']}**

再送你一个能带走的说法：**{chunk['chunk']}**（{chunk['zh']}）。
{chunk['usage_zh']}

原题：{lesson['question']}
评论区把你的答案写下来，我逐条看。

## 话题标签

#雅思 #雅思口语 #英语口语 #IELTS #雅思备考 #英语学习 #口语素材

## 发布建议

- 竖屏 9:16，前 3 秒必须是那句错话本身，不要放 logo 不要放"大家好"
- 时段：工作日 12:00–13:00 或 21:30–23:00（备考人群刷题时间）
- 置顶第一条评论：把正确说法再打一遍，降低回复门槛
- 48 小时复盘：完播率 <30% 说明钩子太慢，下次把正确句也压进前 5 秒
"""


def run(lesson_path: Path, motion: bool = False, skip_video: bool = False) -> int:
    lesson_path = lesson_path.resolve()
    lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
    out = lesson_path.parent
    out.mkdir(parents=True, exist_ok=True)
    aha, why = pick_aha(lesson)
    En.say_ok(f"啊哈点：{aha['id']} {why}")

    scenes = build_scenes(lesson, aha)
    (out / "short_script.json").write_text(
        json.dumps({"lesson_id": lesson["id"], "aha_fix_id": aha["id"], "why": why,
                    "aspect": "9:16", "scenes": [
                        {"id": s["id"], "target_seconds": s["seconds"]} for s in scenes]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "publish.md").write_text(publish_copy(lesson, aha, lesson["chunks"][0]), encoding="utf-8")
    En.say_ok("✓ publish.md + short_script.json")

    En.html_to_png([
        (out / "cover_3x4.png", cover_markup(lesson, aha, "3x4"),
         {"width": VW, "height": int(VW * 4 / 3), "fit": True}),
        (out / "cover_9x16.png", cover_markup(lesson, aha, "9x16"),
         {"width": VW, "height": VH, "fit": True}),
    ])
    En.say_ok("✓ cover_3x4.png + cover_9x16.png")

    if motion:
        if minimax.available():
            En.say_ok("Minimax 服务在线，生成动态开场…")
            got = minimax.image_to_video(
                out / "cover_9x16.png",
                "Slow subtle push-in on dark editorial poster, faint film grain, "
                "amber light breathing, no text changes, no camera shake",
                out / "opening.mp4")
            En.say_ok("✓ opening.mp4" if got else "! 动态开场失败，用静态封面")
        else:
            En.say_ok("! 没检测到 MINIMAX_BASE_URL 指向的服务，跳过动态开场")

    if skip_video:
        return 0

    narration = out / ".narration"
    narration.mkdir(exist_ok=True)
    plan: list[tuple[Path, float, str]] = []
    try:
        from server.config import load_settings
        synth = En.Synth(load_settings(), narration)
        for s in scenes:
            En.html_to_png([(narration / f"{s['id']}.png", s["html"], {"width": VW, "height": VH,
                                                                       "fit": True})], scale=1)
            if s["narration"]:
                clip = synth(s["narration"])
                plan.append((narration / f"{s['id']}.png", En.probe_duration(clip) + 0.5, s["id"]))
            else:
                plan.append((narration / f"{s['id']}.png", float(s["seconds"]), s["id"]))
    except Exception as exc:  # noqa: BLE001
        En.say_ok(f"! 短片旁白合成失败（{type(exc).__name__}: {str(exc)[:100]}），"
                  f"已跳过 short.mp4。封面与文案可用；网络恢复后重跑本命令即可。")
        return 0

    _assemble(plan, narration, out / "short.mp4")
    total = sum(p[1] for p in plan)
    En.say_ok(f"✓ short.mp4  {total:.0f}s  竖屏 {VW}x{VH}  TTS {synth.stats['api_calls']} 次")
    return 0


def _assemble(plan: list[tuple[Path, float, str]], work: Path, out_file: Path) -> None:
    import uuid

    from server.audio import _concat_line, _run

    clips = []
    for img, dur, sid in plan:
        aac = work / f"{sid}.m4a"
        _run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "15", "-i", str(img),
              "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", f"{dur:.3f}",
              "-vf", f"scale={VW}:{VH}:force_original_aspect_ratio=decrease,"
                     f"pad={VW}:{VH}:(ow-iw)/2:(oh-ih)/2:color=0x07090d,fps=15,format=yuv420p",
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
              "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "1",
              "-shortest", str(aac)])
        clips.append(aac)
    list_file = work / f"mix-{uuid.uuid4().hex[:8]}.txt"
    list_file.write_text("\n".join(_concat_line(c) for c in clips) + "\n", encoding="utf-8")
    try:
        _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(list_file),
              "-c", "copy", "-movflags", "+faststart", str(out_file)])
    finally:
        list_file.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Stage 2：单题教学包的自媒体包装")
    ap.add_argument("lesson", type=Path)
    ap.add_argument("--motion", action="store_true", help="用本地 Minimax 生成动态开场")
    ap.add_argument("--no-video", action="store_true", help="只出封面与文案，不碰 TTS")
    a = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    return run(a.lesson, motion=a.motion, skip_video=a.no_video)


if __name__ == "__main__":
    raise SystemExit(main())
