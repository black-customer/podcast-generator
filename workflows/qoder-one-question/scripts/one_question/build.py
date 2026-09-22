"""lesson.json → 单题教学包（音频 + 3 张卡 + 页面）。

校验器是这个工作流的核心，不是附属品：剂量上限就是它存在的理由。
一次给太多，人就不学了。所以超上限会直接失败，并且不许改校验器来放行。

用法：
    python -m one_question.build lessons/<id>/lesson.json
    python -m one_question.build lessons/<id>/lesson.json --dry-run   # 只校验与排期，不花钱
"""
# ruff: noqa: E501  # HTML/CSS 模板与规则字符串是数据，折行会看不清

from __future__ import annotations

import json
import re
import sys
import time
from html import escape as E
from pathlib import Path

from . import engine as En

HERE = Path(__file__).resolve().parent
WORKFLOW_ROOT = HERE.parent.parent

# ---------------------------------------------------------------- 剂量硬上限
CAPS = {
    "fixes_max": 3,
    "chunks_max": 3,
    "model_sentences": (4, 6),
    "model_words": (60, 85),
    "audio_seconds_max": 390,
    "windows_max": 7,
    "cards": 3,
}

WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*\b")
FUNCTION_WORDS = set(
    "the a an and or but of to in on at for with from by as is are was were be been it its this "
    "that these those i you he she we they my your his her our their me him them us so do does "
    "did have has had would could should will than then there here who which what some any one "
    "about into because".split())


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", s.lower()).strip()


def tails(chunk: str) -> list[str]:
    """语块整体，加上依次去掉开头单词的后缀，用于容忍人称/时态变化。"""
    words = chunk.split()
    return [" ".join(words[i:]) for i in range(max(1, len(words)))]


def uses(chunk: str, text: str) -> bool:
    t = norm(text)
    return any(norm(c) in t for c in tails(chunk) if len(norm(c)) > 2)


# ---------------------------------------------------------------- 校验
def validate(lesson: dict) -> list[str]:
    err: list[str] = []
    for k in ("id", "question", "answer_raw", "diagnosis_line_zh", "fixes", "chunks",
              "model_answer", "scaffold_zh"):
        if k not in lesson:
            err.append(f"缺少必填字段：{k}")
    if err:
        return err

    raw = norm(lesson["answer_raw"])
    fixes, chunks = lesson["fixes"], lesson["chunks"]

    if len(fixes) > CAPS["fixes_max"]:
        err.append(f"纠错点 {len(fixes)} 个，上限 {CAPS['fixes_max']}：第 4 个这一轮不会被习得，只会稀释前 3 个")
    if len(chunks) > CAPS["chunks_max"]:
        err.append(f"语块 {len(chunks)} 个，上限 {CAPS['chunks_max']}")

    for f in fixes:
        for k in ("id", "label_zh", "original", "fixed", "core", "rule_zh", "prompt_zh"):
            if not f.get(k):
                err.append(f"fix {f.get('id', '?')} 缺字段 {k}")
        # 不许把用户原话美化掉——那是 noticing 的燃料
        if f.get("original") and norm(f["original"]) not in raw:
            err.append(f"fix {f['id']} 的 original 不是用户原话逐字（校验的是去标点小写后的子串）："
                       f"{f['original'][:50]!r}")
        if f.get("original") and norm(f.get("fixed", "")) == norm(f["original"]):
            err.append(f"fix {f['id']} 的 fixed 和 original 一样，没修")

    seen = {f.get("id") for f in fixes}
    if len(seen) != len(fixes):
        err.append("fix id 重复")

    for c in chunks:
        for k in ("chunk", "zh", "wrong", "example", "usage_zh"):
            if not c.get(k):
                err.append(f"chunk {c.get('chunk', '?')} 缺字段 {k}")
        if c.get("example") and not uses(c["chunk"], c["example"]):
            err.append(f"chunk {c['chunk']!r} 没有真的出现在它的 example 里")

    sents = lesson["model_answer"]
    lo, hi = CAPS["model_sentences"]
    if not lo <= len(sents) <= hi:
        err.append(f"示范答案 {len(sents)} 句，要求 {lo}–{hi} 句（Part 1 的真实长度）")
    joined = " ".join(sents)
    w = len(WORD_RE.findall(joined))
    wlo, whi = CAPS["model_words"]
    if not wlo <= w <= whi:
        err.append(f"示范答案 {w} 词，要求 {wlo}–{whi} 词：写长了就是阅读练习不是口语练习")
    missing = [c["chunk"] for c in chunks if not uses(c["chunk"], joined)]
    if missing:
        err.append("示范答案没有用上这些语块（必须全部用上，否则语块进不了他的长句）："
                   + ", ".join(missing))
    return err


# ---------------------------------------------------------------- 音频
def build_audio(lesson: dict, synth: En.Synth, tl: En.Timeline) -> None:
    q = lesson["question"]
    follow = lesson.get("follow_ups") or []
    tl.clip(synth, [("a", f"单题精练。今天只练这一道：{q}"),
                   ("a", lesson["diagnosis_line_zh"]),
                   ("a", "规则：听到第二声提示音之前，你必须出声。静音不算完成。")], label="hook")
    tl.window(2.0, "hook")

    for f in lesson["fixes"]:
        tl.clip(synth, [
            ("a", f"先看这一处。你的原话是：{f['original']}"),
            ("b", f["fixed"]),
            ("a", f["rule_zh"]),
            ("a", f"现在换你，八秒。把这句说成英语：{f['prompt_zh']}"),
        ], label=f"fix:{f['id']}", gap=0.4)
        tl.window(8.0, f"fix:{f['id']}")
        tl.clip(synth, [("b", f["core"])], label=f"core:{f['id']}")

    prev = None
    for c in lesson["chunks"]:
        lines = ([("b", prev["example"]), ("a", f"下一个语块，{c['chunk']}。")]
                 if prev else [("a", f"三个语块。第一个，{c['chunk']}。")])
        lines += [("b", c["example"]),
                  ("a", f"{c['zh']}。你原来会说 {c['wrong']}。{c['usage_zh']}"),
                  ("a", f"用 {c['chunk']} 说一句你自己的，七秒。")]
        tl.clip(synth, lines, label=f"chunk:{c['chunk']}")
        tl.window(7.0, f"chunk:{c['chunk']}")
        prev = c

    tl.clip(synth, [("b", prev["example"])] if prev else [], label="chunk-tail")
    tl.clip(synth, [
        ("a", "完整答案。先听一遍，然后跟我一句一句说，只模仿旋律，不用管意思。"),
        ("b", " ".join(lesson["model_answer"])),
    ], label="model-full", gap=0.5)
    for i, s in enumerate(lesson["model_answer"], 1):
        tl.clip(synth, [("b", s)], label=f"echo:{i}")
        tl.rest(max(1.5, En.probe_duration(tl.entries[-1]) * 1.3))

    tl.clip(synth, [
        ("a", "最后，考试节奏。我只问一次，四秒内开口，用上刚才的语块。"),
        ("a", q if not follow else f"{q} And follow-up: {follow[0]}"),
    ], label="pressure", gap=0.6)
    tl.window(4.0, "pressure")
    tl.clip(synth, [("a", "这一轮结束。明天同一个时间，再跑一遍这段音频，只要六分钟。")],
            label="outro")


# ---------------------------------------------------------------- 卡片
def stress(sentence: str) -> str:
    groups: list[list[str]] = [[]]
    for tok in re.findall(r"\S+", sentence):
        if tok in {"—", "–", "-"}:
            groups.append([])
            continue
        groups[-1].append(tok)
        if re.search(r"[,;:]", tok):
            groups.append([])
    out = []
    for gi, g in enumerate(groups):
        if not g:
            continue
        bases = [re.sub(r"[^A-Za-z'’-]", "", t).lower() for t in g]
        content = [i for i, b in enumerate(bases) if len(b) > 2 and b not in FUNCTION_WORDS]
        nuc = content[-1] if content else -1
        marked = []
        for i, tok in enumerate(g):
            if i == len(g) - 1 and gi != len(groups) - 1:
                tok = tok.rstrip(",;:")
            w = E(tok)
            w = (f'<b class="n">{w}</b>' if i == nuc else
                 f'<b class="s">{w}</b>' if i in content else w)
            marked.append(w)
        out.append(" ".join(marked))
    return ' <span class="p">/</span> '.join(out)


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
::-webkit-scrollbar{display:none}html,body{scrollbar-width:none;-ms-overflow-style:none}
body{font-family:"Segoe UI Variable Text","Segoe UI","Microsoft YaHei",system-ui,sans-serif;
 background:#0b0e13;color:#eef2f6;-webkit-font-smoothing:antialiased}
.c{width:1080px;min-height:1350px;padding:60px 56px;position:relative;overflow:hidden;display:flex;
 flex-direction:column;background:radial-gradient(1100px 620px at 90% -14%,rgba(232,163,61,.16),
 transparent 62%),radial-gradient(900px 520px at -8% 110%,rgba(77,208,199,.12),transparent 60%),#0b0e13}
.top{display:flex;justify-content:space-between;font-size:20px;letter-spacing:.16em;
 text-transform:uppercase;color:#8b97a7}
.top b{color:#E8A33D}
.rule{height:3px;background:linear-gradient(90deg,#E8A33D,rgba(232,163,61,0) 70%);margin:22px 0 0}
h1{font-size:46px;line-height:1.22;font-weight:800;letter-spacing:-.015em;margin-top:30px;margin-bottom:6px}
h2{font-size:20px;letter-spacing:.18em;text-transform:uppercase;color:#96a2b1;margin:36px 0 14px}
.q{font-size:33px;line-height:1.4;color:#cfd8e2;font-style:italic}
.s{font-size:33px;line-height:1.72;color:#7f8c9b;margin:9px 0}
.s b.s{color:#c8d3dd;font-weight:600}
.s b.n{color:#fff;font-weight:800;background:rgba(232,163,61,.15);border-bottom:3px solid #E8A33D;
 padding:0 5px;border-radius:5px 5px 0 0}
.p{color:#E8A33D;font-weight:800;padding:0 3px}
.box{margin-top:22px;padding:26px 28px;border-radius:18px}
.bad{background:rgba(226,92,92,.1);border-left:5px solid #b8504f}
.good{background:rgba(77,208,199,.1);border-left:5px solid #4DD0C7}
.amb{background:rgba(232,163,61,.09);border-left:5px solid #E8A33D}
.tg{font-size:18px;letter-spacing:.15em;text-transform:uppercase;color:#96a2b1;margin-bottom:10px}
.bad .tx{font-size:27px;color:#e28c8c;text-decoration:line-through;text-decoration-color:#b8504f;
 text-decoration-thickness:3px}
.good .tx{font-size:29px;line-height:1.5;font-weight:650}
.good .tx em{color:#4DD0C7;font-style:normal;font-weight:800}
.amb .tx{font-size:27px;line-height:1.5;color:#f4e9d8}
.foot{margin-top:auto;padding-top:22px;border-top:1px solid #202834;display:flex;
 justify-content:space-between;font-size:19px;color:#5d6875;letter-spacing:.08em}
.note{font-size:22px;line-height:1.6;color:#98a4b3;margin-top:14px}
.ch{font-size:38px;font-weight:800;color:#4DD0C7;line-height:1.15}
.zh{font-size:26px;color:#dfe7ee;margin-top:8px}
.usage{font-size:22px;color:#93a0af;line-height:1.55;margin-top:10px}
"""


def card_answer(lesson: dict) -> str:
    body = "".join(f"<p class='s'>{stress(s)}</p>" for s in lesson["model_answer"])
    return f"""<!doctype html><meta charset="utf-8"><style>{CSS}</style><body><div class="c">
<div class="top"><span><b>单题精练</b> · 答案卡</span><span>Part {E(str(lesson.get('part',1)))}</span></div>
<div class="rule"></div><h1>{E(lesson['question'])}</h1>
<h2>你的 7.5 分版本 · 加粗＝重音落点 · / ＝吸气</h2>
{body}
<div class="box amb"><div class="tg">骨架</div><div class="tx">{E(lesson['scaffold_zh'])}</div></div>
<div class="note">{E(lesson.get('answer_note_zh',''))}</div>
<div class="foot"><span>IELTS POD · ONE QUESTION</span><span>{E(lesson['id'])}</span></div>
</div>"""


def card_chunks(lesson: dict) -> str:
    blocks = "".join(
        f"""<div class="ch">{E(c['chunk'])}</div><div class="zh">{E(c['zh'])}</div>
        <div class="box bad" style="margin-top:14px"><div class="tx">{E(c['wrong'])}</div></div>
        <div class="box good" style="margin-top:12px"><div class="tx">{_hl(c['chunk'], c['example'])}</div></div>
        <div class="usage">{E(c['usage_zh'])}</div>"""
        for c in lesson["chunks"])
    return f"""<!doctype html><meta charset="utf-8"><style>{CSS}</style><body><div class="c">
<div class="top"><span><b>单题精练</b> · 语块卡</span><span>{len(lesson['chunks'])} 个，够了</span></div>
<div class="rule"></div><h1>这一题只需要这三个</h1>{blocks}
<div class="foot"><span>IELTS POD · ONE QUESTION</span><span>{E(lesson['id'])}</span></div>
</div>"""


def card_before(lesson: dict) -> str:
    pairs = "".join(
        f"""<h2>{E(f['label_zh'])}</h2>
        <div class="box bad"><div class="tg">你原来这么说</div><div class="tx">{E(f['original'])}</div></div>
        <div class="box good"><div class="tg">改完之后</div><div class="tx">{E(f['fixed'])}</div></div>
        <div class="usage">{E(f['rule_zh'])}</div>"""
        for f in lesson["fixes"])
    return f"""<!doctype html><meta charset="utf-8"><style>{CSS}</style><body><div class="c">
<div class="top"><span><b>单题精练</b> · 前后对比</span><span>{len(lesson['fixes'])} 处</span></div>
<div class="rule"></div><h1>{E(lesson['diagnosis_line_zh'])}</h1>{pairs}
<div class="foot"><span>IELTS POD · ONE QUESTION</span><span>{E(lesson['id'])}</span></div>
</div>"""


def _hl(chunk: str, sentence: str) -> str:
    out, words = E(sentence), chunk.split()
    for cand in [chunk, *[" ".join(words[i:]) for i in range(1, max(1, len(words)))]]:
        c = E(cand)
        i = re.search(re.escape(c), out, re.I)
        if i:
            return out[:i.start()] + "<em>" + i.group(0) + "</em>" + out[i.end():]
    return out


# ---------------------------------------------------------------- 页面
def page(lesson: dict, info: dict | None) -> str:
    if info:
        wins = len(info["windows"])
        step1 = (f"① 听完整音频 {int(info['duration']) // 60} 分 {int(info['duration']) % 60:02d} 秒，"
                 f"{wins} 个窗口全部出声 →")
        audio_block = '<audio controls src="audio.mp3"></audio>'
    else:
        step1 = "①（音频待生成）先照卡片练，看中文提示自己说，录音 →"
        audio_block = ('<p class="lead">音频还没生成。卡片和页面已经可用；'
                       '重跑一次构建命令即可补上：<code>python -m one_question.build lesson.json</code></p>')
    rows = "".join(
        f"<tr><td>{E(f['label_zh'])}</td><td class='b'>{E(f['original'])}</td>"
        f"<td class='g'>{E(f['fixed'])}</td></tr>" for f in lesson["fixes"])
    chunks = "".join(
        f"<tr><td class='g'>{E(c['chunk'])}</td><td>{E(c['zh'])}</td></tr>" for c in lesson["chunks"])
    return f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{E(lesson['question'])}</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#0b0e13;color:#e6ecf2;line-height:1.65;
font-family:"Segoe UI Variable Text","Segoe UI","Microsoft YaHei",system-ui,sans-serif}}
.w{{max-width:900px;margin:0 auto;padding:40px 20px 80px}}
h1{{font-size:29px;letter-spacing:-.01em}}.lead{{color:#93a0af;font-size:17px}}
h2{{font-size:13px;letter-spacing:.2em;text-transform:uppercase;color:#E8A33D;margin:36px 0 12px;
border-bottom:1px solid #1b232e;padding-bottom:8px}}
audio{{width:100%;height:40px}}img{{width:100%;border-radius:14px;border:1px solid #1c2531;
margin-bottom:16px;display:block}}
table{{width:100%;border-collapse:collapse;font-size:15px}}
td{{padding:10px 10px 10px 0;border-bottom:1px solid #171e27;vertical-align:top}}
.b{{color:#e28c8c;text-decoration:line-through}}.g{{color:#4DD0C7;font-weight:600}}
.loop{{background:#10151d;border:1px solid #1c2531;border-radius:14px;padding:16px 20px;font-size:16px}}
.loop b{{color:#E8A33D}}</style></head><body><div class="w">
<h1>{E(lesson['question'])}</h1>
<p class="lead">{E(lesson['diagnosis_line_zh'])}</p>
<div class="loop"><b>12 分钟一轮：</b>{step1} ② 拿答案卡遮住英文，看中文提示自己说一遍，录音 →
③ 对比录音，只找你今天那 {len(lesson['fixes'])} 处有没有改过来。别的不用管。</div>
<h2>音频</h2>{audio_block}
<h2>答案卡（重音与意群已标好）</h2><img src="card_1_answer.png">
<h2>语块卡</h2><img src="card_2_chunks.png">
<h2>前后对比卡</h2><img src="card_3_before_after.png">
<h2>这一轮改掉的 {len(lesson['fixes'])} 处</h2><table>{rows}</table>
<h2>这一轮装进去的 {len(lesson['chunks'])} 个语块</h2><table>{chunks}</table>
<p class="lead" style="margin-top:30px;font-size:14px">来源：lesson.json · 生成：one_question.build</p>
</div></body></html>"""


# ---------------------------------------------------------------- 入口
def run(lesson_path: Path, dry: bool = False, cards_only: bool = False,
        wait_network: float = 0.0) -> int:
    lesson = json.loads(lesson_path.read_text(encoding="utf-8"))
    errors = validate(lesson)
    if errors:
        print("lesson.json 未通过剂量校验：")
        for e in errors:
            print(f"  ✗ {e}")
        print("\n改 lesson.json 重跑。不许放宽校验器。")
        return 1
    print(f"剂量校验通过：{len(lesson['fixes'])} 处纠错 / {len(lesson['chunks'])} 个语块 / "
          f"{len(lesson['model_answer'])} 句示范答案")

    lesson_path = lesson_path.resolve()
    out = lesson_path.parent
    if dry:
        est = sum(len(En.for_tts(t)) for t in _peek_texts(lesson)) / 19 + 7 * 8
        En.say_ok(f"[dry-run] 未调用 TTS。预计音频约 {est / 60:.1f} 分钟，"
                  f"强制输出窗口 ≤{CAPS['windows_max']} 个")
        return _render_assets(lesson, out, None)

    info = None if cards_only else _attempt_audio(lesson, lesson_path, out, wait_network)
    return _render_assets(lesson, out, info)


def _attempt_audio(lesson: dict, lesson_path: Path, out: Path,
                   wait_network: float) -> dict | None:
    """合成音频。失败不抛异常——卡片和页面不该被网络卡死。"""
    deadline = time.monotonic() + max(0.0, wait_network)
    attempt, last = 0, ""
    while True:
        attempt += 1
        try:
            from server.config import load_settings
            synth = En.Synth(load_settings(), out / ".cache")
            tl = En.Timeline()
            build_audio(lesson, synth, tl)
            info = tl.render(out / "audio.mp3")
            info.update({"scheduled": round(tl.scheduled, 2),
                         "api_calls": synth.stats["api_calls"],
                         "cache_hits": synth.stats["cache_hits"]})
            if info["duration"] > CAPS["audio_seconds_max"]:
                En.say_ok(f"! 音频 {info['duration']:.0f}s 超过上限 {CAPS['audio_seconds_max']}s——"
                          f"该减解释文字，不是加纠错点")
            if len(info["windows"]) > CAPS["windows_max"]:
                En.say_ok(f"! 输出窗口 {len(info['windows'])} 个，超过上限 {CAPS['windows_max']}")
            (out / "audio_manifest.json").write_text(
                json.dumps({**info, "lesson_id": lesson["id"]}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            (out / "PENDING.json").unlink(missing_ok=True)
            return info
        except Exception as exc:  # noqa: BLE001  网络、配额、上游 5xx 都走这里
            last = f"{type(exc).__name__}: {exc}"
            En.say_ok(f"! 音频合成第 {attempt} 次失败：{last[:150]}")
            if time.monotonic() >= deadline:
                break
            time.sleep(min(20.0, max(3.0, deadline - time.monotonic())))

    (out / "PENDING.json").write_text(json.dumps({
        "lesson_id": lesson["id"],
        "reason": last[:300],
        "hint": "这台机器访问 api.fish.audio 需要本地代理；代理没开时只有音频会失败，"
                "卡片和页面照常可用。",
        "retry": f"python -m one_question.build {lesson_path.as_posix()}",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    En.say_ok("! 音频跳过，已写出 PENDING.json。卡片与页面仍然可用。")
    return None


def _render_assets(lesson: dict, out: Path, info: dict | None) -> int:
    En.html_to_png([
        (out / "card_1_answer.png", card_answer(lesson), {"width": 1080, "height": 1350, "fit": True}),
        (out / "card_2_chunks.png", card_chunks(lesson), {"width": 1080, "height": 1350, "fit": True}),
        (out / "card_3_before_after.png", card_before(lesson), {"width": 1080, "height": 1350, "fit": True}),
    ])
    (out / "page.html").write_text(page(lesson, info), encoding="utf-8")
    if info:
        En.say_ok(f"✓ audio.mp3  {info['duration']:.0f}s  窗口 {len(info['windows'])} 个  "
                  f"响度 {En.loudness(out / 'audio.mp3')['integrated_lufs']} LUFS  "
                  f"TTS {info['api_calls']} 次/缓存 {info['cache_hits']} 次")
    En.say_ok(f"✓ 3 张卡 + page.html → {out}")
    return 0


def _peek_texts(lesson: dict):
    """粗略估算音频文本量，用于 dry-run 报时长。"""
    for f in lesson["fixes"]:
        yield f["original"]
        yield f["fixed"]
        yield f["rule_zh"]
        yield f["prompt_zh"]
    for c in lesson["chunks"]:
        yield c["example"]
        yield c["usage_zh"]
    yield " ".join(lesson["model_answer"])


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("lesson", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cards-only", action="store_true", help="只出卡片和页面，不碰 TTS")
    ap.add_argument("--wait-network", type=float, default=0.0,
                    help="TTS 失败后最多再等这么多秒（代理刚重启时有用）")
    a = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    return run(a.lesson, dry=a.dry_run, cards_only=a.cards_only,
               wait_network=a.wait_network)


if __name__ == "__main__":
    raise SystemExit(main())
