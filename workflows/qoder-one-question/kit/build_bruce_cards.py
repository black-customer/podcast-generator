"""Bruce 学习包视觉材料渲染器：内容模块 → HTML → Playwright 截图 → PNG。

为什么不用 AI 直接生图：文字密集的卡片用生成模型必然糊字。
这里所有排版都走真实字体渲染（Segoe UI Variable + 微软雅黑），
AI 只负责三张无文字的隐喻插图（已预先放在 assets/img/）。
"""
# ruff: noqa: E501  # 语料与 HTML 模板是数据，折行会让内容不可核对

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bruce_kit_content as C  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

KIT = Path(__file__).resolve().parent / "learning_kit_bruce"
OUT = KIT / "cards"
IMG = KIT / "assets" / "img"
TMP = KIT / ".html"

E = html.escape

BASE_CSS = """
@font-face { font-family: local; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: "Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei", system-ui, sans-serif;
  background: #0b0e13; color: #eef2f6; -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
.mono { font-family: "Cascadia Mono", Consolas, "Segoe UI Mono", monospace; }
"""

CARD_CSS = BASE_CSS + """
.card { width: 1080px; height: 1350px; padding: 64px 60px; position: relative; overflow: hidden;
  background:
    radial-gradient(1100px 620px at 88% -12%, rgba(232,163,61,.17), transparent 62%),
    radial-gradient(900px 520px at -10% 108%, rgba(77,208,199,.13), transparent 60%),
    #0b0e13;
  display: flex; flex-direction: column;
}
.strip { display:flex; justify-content:space-between; align-items:center; font-size:21px;
  letter-spacing:.16em; text-transform:uppercase; color:#8b97a7; }
.strip .n { color:#E8A33D; font-weight:700; }
.rule { height:3px; background:linear-gradient(90deg,#E8A33D,rgba(232,163,61,0) 70%); margin:24px 0 0; }
.zh { font-size:54px; font-weight:750; margin-top:38px; line-height:1.2; }
.ghost { position:absolute; right:14px; top:280px; font-size:340px; font-weight:800;
  color:rgba(255,255,255,.032); line-height:.8; letter-spacing:-.04em; }
.chunk { font-weight:800; line-height:1.02; letter-spacing:-.022em; color:#fff; margin-top:26px;
  word-spacing:2px; position:relative; }
.hl { color:#4DD0C7; }
.pron { display:flex; gap:20px; align-items:baseline; margin-top:22px; flex-wrap:wrap; }
.ipa { font-size:29px; color:#7fd8cf; }
.stress { font-size:26px; color:#8b97a7; letter-spacing:.05em; }
.block { margin-top:30px; padding:28px 30px; border-radius:18px; }
.bad { background:rgba(226,92,92,.10); border-left:5px solid #b8504f; }
.good { background:rgba(77,208,199,.10); border-left:5px solid #4DD0C7; }
.tag { font-size:19px; letter-spacing:.15em; text-transform:uppercase; color:#96a2b1; margin-bottom:12px; }
.bad .txt { font-size:29px; color:#e28c8c; line-height:1.45; }
.bad .txt s { text-decoration:line-through; text-decoration-color:#b8504f;
  text-decoration-thickness:3px; }
.bad .why { font-size:22px; color:#8f7b7b; }
.good .txt { font-size:32px; line-height:1.48; font-weight:600; color:#f3f7fa; }
.good .txt b { color:#4DD0C7; font-weight:800; }
.alt { margin-top:18px; font-size:26px; line-height:1.5; color:#b9c4d0; font-style:italic; }
.chips { display:flex; gap:12px; margin-top:30px; flex-wrap:wrap; }
.chip { font-size:21px; color:#a7b6c5; border:1px solid #27313d; border-radius:999px;
  padding:9px 20px; letter-spacing:.04em; }
.note { margin-top:auto; padding-top:26px; border-top:1px solid #202834; font-size:23px;
  line-height:1.6; color:#98a4b3; }
.note em { color:#E8A33D; font-style:normal; font-weight:700; }
.foot { display:flex; justify-content:space-between; margin-top:20px; font-size:20px; color:#5d6875;
  letter-spacing:.08em; }
"""


def chunk_font(text: str) -> int:
    n = len(text)
    return 96 if n <= 16 else 84 if n <= 24 else 72 if n <= 32 else 62


def mark(chunk: str, sentence: str) -> str:
    """把语块在例句里高亮出来：整块优先，匹配不到就退到更短的词尾序列。"""
    out = E(sentence)
    words = chunk.split()
    candidates = [chunk] + [" ".join(words[i:]) for i in range(1, max(1, len(words) - 1))]
    for cand in candidates:
        c = E(cand)
        if c in out:
            return out.replace(c, f"<b>{c}</b>", 1)
        c_low = c.lower()
        idx = out.lower().find(c_low)
        if idx >= 0:
            return out[:idx] + "<b>" + out[idx:idx + len(c)] + "</b>" + out[idx + len(c):]
    return out


def render_card(ch: dict, idx: int, total: int) -> str:
    wrong_en, _, wrong_note = ch["wrong"].partition("（")
    why = f"（{wrong_note}" if wrong_note else ""
    chips = "".join(f"<span class='chip'>{E(t.strip())}</span>" for t in ch["topics"].split("/"))
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CARD_CSS}</style></head><body>
<div class="card">
  <div class="ghost mono">{idx:02d}</div>
  <div class="strip"><span><span class="n">{idx:02d}</span> / {total:02d} · 语块健身房</span>
    <span>{E(ch['topics'])}</span></div>
  <div class="rule"></div>
  <div class="zh">{E(ch['zh'])}</div>
  <div class="chunk" style="font-size:{chunk_font(ch['chunk'])}px"><span class="hl">{E(ch['chunk'])}</span></div>
  <div class="pron">
    {f'<span class="ipa mono">{E(ch["ipa"])}</span>' if ch['ipa'] else ''}
    <span class="stress mono">{E(ch['stress'])}</span>
  </div>
  <div class="block bad"><div class="tag">你原来这么说</div>
    <div class="txt mono"><s>{E(wrong_en.strip())}</s> <span class="why">{E(why)}</span></div></div>
  <div class="block good"><div class="tag">母语者这么说</div>
    <div class="txt">{mark(ch['chunk'], ch['example_a'])}</div>
    <div class="alt">{E(ch['example_b'])}</div></div>
  <div class="chips">{chips}</div>
  <div class="note">{E(ch['usage_zh'])}</div>
  <div class="foot"><span>IELTS POD · BRUCE KIT</span><span>Track 02 · 05</span></div>
</div></body></html>"""


def render_fossil(f: dict, idx: int, total: int) -> str:
    css = CARD_CSS.replace("#4DD0C7", "#8FBF6E") + """
.drill { background:rgba(232,163,61,.09); border-left:5px solid #E8A33D; }
.drill .txt { font-size:31px; line-height:1.5; color:#f4e9d8; font-weight:600; }
.drill .hint { font-size:22px; color:#a08a63; margin-top:12px; }
"""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>
<div class="card">
  <div class="ghost mono">{idx:02d}</div>
  <div class="strip"><span><span class="n">{idx:02d}</span> / {total:02d} · 化石纠错</span>
    <span>{E(f['label_zh'])}</span></div>
  <div class="rule"></div>
  <div class="chunk" style="font-size:{chunk_font(f['core'])}px"><span class="hl">{E(f['core'])}</span></div>
  <div class="block bad"><div class="tag">你的原话</div>
    <div class="txt mono"><s>{E(f['your_words'])}</s></div></div>
  <div class="block good"><div class="tag">8 分版本</div>
    <div class="txt">{E(f['fixed'])}</div></div>
  <div class="block drill"><div class="tag">自测：遮住上面，说成英语</div>
    <div class="txt">{E(f['prompt_zh'])}</div>
    <div class="hint">十秒。出声，不许在脑子里过一遍就算过。</div></div>
  <div class="chips"><span class="chip">{E(f['label_zh'])}</span>
    <span class="chip">Track 01 · 第 {idx} 号</span></div>
  <div class="note"><em>规则：</em>{E(f['rule_zh'])}<br><br><em>出处：</em>{E(f['note_zh'])}</div>
  <div class="foot"><span>IELTS POD · BRUCE KIT</span><span>Track 01</span></div>
</div></body></html>"""


# ------------------------------------------------------------------ 海报
def stress_markup(sentence: str) -> str:
    """按意群标重音：每组只有最后一个实词是核应力（nuc），其余实词次之（sec）。"""
    function_words = {
        "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for", "with",
        "from", "by", "as", "is", "are", "was", "were", "be", "been", "it", "its", "this",
        "that", "these", "those", "i", "you", "he", "she", "we", "they", "my", "your",
        "his", "her", "our", "their", "me", "him", "them", "us", "so", "do", "does", "did",
        "have", "has", "had", "would", "could", "should", "will", "than", "then", "there",
        "here", "who", "which", "what", "some", "any", "one", "about", "into", "because",
    }
    groups: list[list[str]] = [[]]
    for token in re.findall(r"\S+", sentence):
        if token in {"—", "–", "-"}:
            groups.append([])
            continue
        groups[-1].append(token)
        if re.search(r"[,;:]", token):
            groups.append([])

    rendered = []
    for gi, group in enumerate(groups):
        if not group:
            continue
        bases = [re.sub(r"[^A-Za-z'’-]", "", t).lower() for t in group]
        content = [i for i, b in enumerate(bases) if len(b) > 2 and b not in function_words]
        nuclear = content[-1] if content else -1
        marked = []
        last = len(group) - 1
        for i, token in enumerate(group):
            if i == last and gi != len(groups) - 1:
                token = token.rstrip(",;:")
            word = E(token)
            if i == nuclear:
                word = f'<strong class="nuc">{word}</strong>'
            elif i in content:
                word = f'<strong class="sec">{word}</strong>'
            marked.append(word)
        rendered.append(" ".join(marked))
    return ' <span class="gap">/</span> '.join(rendered)


def render_xray() -> str:
    d = C.DIAGNOSIS
    metrics = "".join(
        f"<tr><td class='k mono'>{E(m['key'])}</td><td class='y'>{E(m['yours'])}</td>"
        f"<td class='n'>{E(m['native'])}</td><td class='note'>{E(m['note'])}</td></tr>"
        for m in d["metrics"]
    )
    families = "".join(f"<li>{E(x)}</li>" for x in d["error_families"])
    strengths = "".join(f"<li>{E(x)}</li>" for x in d["strengths"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{BASE_CSS}
.page {{ width:1400px; padding:64px 60px 70px; background:
  radial-gradient(1200px 700px at 100% -8%, rgba(232,163,61,.14), transparent 60%), #0b0e13; }}
h1 {{ font-size:66px; font-weight:800; letter-spacing:-.02em; }}
.sub {{ color:#96a3b2; font-size:26px; margin-top:12px; }}
.hero {{ display:grid; grid-template-columns: 1fr 460px; gap:40px; margin-top:38px; align-items:stretch; }}
.img {{ width:460px; height:345px; object-fit:cover; border-radius:20px; opacity:.92;
  border:1px solid #222b37; }}
.verdict {{ background:rgba(232,163,61,.09); border:1px solid rgba(232,163,61,.35);
  border-radius:20px; padding:30px 32px; }}
.band {{ font-size:30px; color:#E8A33D; font-weight:700; letter-spacing:.04em; }}
.big {{ font-size:26px; line-height:1.62; margin-top:14px; color:#e6ecf2; }}
h2 {{ font-size:25px; letter-spacing:.2em; text-transform:uppercase; color:#7f8c9b;
  margin:52px 0 20px; border-bottom:1px solid #1e2732; padding-bottom:12px; }}
table {{ width:100%; border-collapse:collapse; font-size:23px; }}
th {{ text-align:left; color:#67748233; }}
td {{ padding:16px 18px 16px 0; border-bottom:1px solid #171e27; vertical-align:top; line-height:1.45; }}
td.k {{ color:#dfe7ee; font-weight:600; width:23%; }}
td.y {{ color:#e28c8c; width:23%; }}
td.n {{ color:#7fd8cf; width:20%; }}
td.note {{ color:#8d99a8; font-size:21px; }}
ul {{ list-style:none; display:grid; grid-template-columns:1fr 1fr; gap:14px 34px; }}
li {{ font-size:23px; line-height:1.5; padding-left:26px; position:relative; color:#cdd7e1; }}
li:before {{ content:""; position:absolute; left:0; top:12px; width:10px; height:10px;
  border-radius:50%; background:#b8504f; }}
.good ul li:before {{ background:#4DD0C7; }}
.foot {{ margin-top:52px; color:#5d6875; font-size:20px; letter-spacing:.1em;
  display:flex; justify-content:space-between; }}
</style></head><body><div class="page">
<h1>英语口语体检报告</h1>
<div class="sub">样本：三份雅思口语自录转写稿，11,332 词 · 对象：Bruce，21 岁 · 目标：6.0 → 8.0+</div>
<div class="hero">
  <div class="verdict">
    <div class="band">诊断：{E(d['estimated_band'])}</div>
    <div class="big">{E(d['core_finding'])}</div>
  </div>
  <img class="img" src="{(IMG / 'filter_bubble.png').as_uri()}">
</div>
<h2>数据说话</h2>
<table><tr><td class="k">指标</td><td class="y">你的</td><td class="n">母语者</td><td class="note">意味着什么</td></tr>
{metrics}</table>
<h2>化石级错误（按出现次数排）</h2>
<ul>{families}</ul>
<h2 class="">你已经有的资产</h2>
<div class="good"><ul>{strengths}</ul></div>
<div class="foot"><span>IELTS POD · BRUCE KIT</span><span>配套音频 Track 01 · 02</span></div>
</div></body></html>"""


def render_scaffolds() -> str:
    blocks = ""
    for s in C.SCAFFOLDS:
        rows = "".join(
            f"<tr><td class='mv'>{E(m['move'])}</td><td class='en mono'>{E(m['en'])}</td>"
            f"<td class='zh'>{E(m['zh'])}</td></tr>" for m in s["moves"]
        )
        blocks += f"""<section><h2>{E(s['name'])}</h2>
        <table><tr><th></th><th></th><th></th></tr>{rows}</table></section>"""
    ups = "".join(
        f"<tr><td class='v mono'>{E(v['vague'])}</td><td class='b'>{E(v['better'])}</td>"
        f"<td class='z'>{E(v['zh'])}</td></tr>" for v in C.VAGUE_UPGRADES
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{BASE_CSS}
.page {{ width:1400px; padding:60px; background:
  radial-gradient(1000px 600px at 0% 0%, rgba(77,208,199,.12), transparent 55%), #0b0e13; }}
h1 {{ font-size:60px; font-weight:800; letter-spacing:-.02em; }}
.sub {{ color:#96a3b2; font-size:25px; margin-top:10px; }}
h2 {{ font-size:27px; color:#E8A33D; margin:46px 0 16px; letter-spacing:.04em; }}
table {{ width:100%; border-collapse:collapse; }}
th {{ display:none; }}
td {{ padding:17px 18px 17px 0; border-bottom:1px solid #171e27; font-size:24px; line-height:1.45; }}
td.mv {{ width:15%; color:#8d99a8; }}
td.en {{ width:45%; color:#fff; font-weight:650; }}
td.zh {{ color:#93a0af; font-size:22px; }}
td.v {{ color:#e28c8c; width:30%; font-size:22px; }}
td.b {{ color:#4DD0C7; width:30%; font-weight:650; }}
td.z {{ color:#93a0af; }}
h3 {{ font-size:27px; color:#E8A33D; margin:54px 0 6px; }}
.warn {{ font-size:22px; color:#8d99a8; margin-bottom:10px; }}
.foot {{ margin-top:50px; color:#5d6875; font-size:20px; letter-spacing:.1em; }}
</style></head><body><div class="page">
<h1>答案骨架</h1>
<div class="sub">你不是没想法，是缺承载想法的架子。把这四句背下来，任何 Part 3 题都能落地。</div>
{blocks}
<h3>把含糊词升级（你稿子里有 54 次 stuff / things）</h3>
<div class="warn">模糊名词 = 词汇量天花板。考官听到 stuff 就停止期待更精准的表达。</div>
<table>{ups}</table>
<div class="foot">IELTS POD · BRUCE KIT · 配套音频 Track 04</div>
</div></body></html>"""


def render_rhythm() -> str:
    secs = ""
    for m in C.MODELS:
        lines = "".join(
            f"<p class='s'>{stress_markup(s)}</p>" for s in m["sentences"]
        )
        secs += f"""<section><h2>{E(m['title_zh'])}</h2>{lines}
        <div class='tip'>{E(m['focus_zh'])}</div></section>"""
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{BASE_CSS}
.page {{ width:1400px; padding:60px; background:
  radial-gradient(1000px 600px at 100% 0%, rgba(232,163,61,.13), transparent 55%), #0b0e13; }}
h1 {{ font-size:58px; font-weight:800; letter-spacing:-.02em; }}
.sub {{ color:#96a3b2; font-size:25px; margin-top:12px; line-height:1.5; }}
.legend {{ display:flex; gap:34px; margin:26px 0 6px; font-size:22px; color:#8d99a8; }}
.legend b {{ color:#fff; }}
.legend .nuc-demo {{ background:rgba(232,163,61,.15); border-bottom:3px solid #E8A33D;
  padding:0 5px; font-weight:800; }}
.legend .sec-demo {{ color:#c8d3dd; font-weight:600; }}
.legend .gap {{ color:#E8A33D; font-size:26px; }}
h2 {{ font-size:25px; color:#4DD0C7; margin:42px 0 12px; font-weight:650; }}
p.s {{ font-size:29px; line-height:1.8; color:#7f8c9b; margin:8px 0; }}
p.s strong.sec {{ color:#c8d3dd; font-weight:600; }}
p.s strong.nuc {{ color:#fff; font-weight:800; background:rgba(232,163,61,.15);
  border-bottom:3px solid #E8A33D; padding:0 5px; border-radius:5px 5px 0 0; }}
.gap {{ color:#E8A33D; font-weight:800; padding:0 3px; }}
.tip {{ font-size:21px; color:#7f8c9b; margin-top:12px; border-left:3px solid #2c3745;
  padding-left:16px; line-height:1.5; }}
.foot {{ margin-top:48px; color:#5d6875; font-size:20px; letter-spacing:.1em; }}
</style></head><body><div class="page">
<h1>重音与意群</h1>
<div class="sub">中文每个字时长差不多，英语不是。<b>一个意群只有一个重音落点</b>，落在最后那个实词上，
前面的词统统弱化。节奏对了，考官对你"清晰度"的打分立刻变。</div>
<div class="legend"><span><b class="nuc-demo">SELF-discipline</b> 重音落点，拉长并加重</span>
<span><b class="sec-demo">creative</b> 次要实词，一带而过</span>
<span><span class="gap">/</span> 意群边界，在这里吸气</span></div>
{secs}
<div class="foot">IELTS POD · BRUCE KIT · 配套音频 Track 03</div>
</div></body></html>"""


def render_protocol() -> str:
    rows = "".join(
        f"<tr><td class='d'>{E(p['day'])}</td><td class='t'>{E(p['task'])}</td></tr>" for p in C.PROTOCOL
    )
    ints = "".join(
        f"<tr><td class='w mono'>{E(i['when'])}</td><td class='t'>{E(i['then'])}</td></tr>"
        for i in C.IMPLEMENTATION_INTENTIONS
    )
    tracks = "".join(
        f"<tr><td class='n mono'>{E(k)}</td><td class='t'>{E(v[2])}</td><td class='u'>{E(_USE[k])}</td></tr>"
        for k, v in _TRACKS.items()
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{BASE_CSS}
.page {{ width:1400px; padding:60px; background:
  radial-gradient(1000px 600px at 50% -10%, rgba(77,208,199,.12), transparent 60%), #0b0e13; }}
h1 {{ font-size:58px; font-weight:800; letter-spacing:-.02em; }}
.sub {{ color:#96a3b2; font-size:25px; margin-top:12px; }}
h2 {{ font-size:25px; letter-spacing:.16em; text-transform:uppercase; color:#E8A33D;
  margin:46px 0 14px; }}
table {{ width:100%; border-collapse:collapse; }}
td {{ padding:18px 18px 18px 0; border-bottom:1px solid #171e27; font-size:24px; line-height:1.5;
  vertical-align:top; }}
td.d, td.n {{ width:17%; color:#4DD0C7; font-weight:650; }}
td.u {{ width:33%; color:#8d99a8; font-size:22px; }}
td.w {{ width:23%; color:#e2b96d; }}
.t {{ color:#e6ecf2; }}
.foot {{ margin-top:48px; color:#5d6875; font-size:20px; letter-spacing:.1em; }}
.callout {{ margin-top:34px; padding:26px 28px; border-radius:18px;
  background:rgba(232,163,61,.08); border:1px solid rgba(232,163,61,.3);
  font-size:23px; line-height:1.6; color:#e6ecf2; }}
</style></head><body><div class="page">
<h1>怎么用这套材料</h1>
<div class="sub">你说你的学习时长"看心情"。所以这里没有"每天两小时"，只有三个必然发生的时刻。</div>
<h2>五条音频轨</h2>
<table><tr><th></th><th></th><th></th></tr>{tracks}</table>
<h2>21 天节奏</h2>
<table>{rows}</table>
<h2>执行力不是意志力，是挂钩</h2>
<div class="warn" style="font-size:22px;color:#8d99a8;margin-bottom:6px">
把训练挂在已经存在的行为上，不给自己"今天状态不好"这个选项。</div>
<table>{ints}</table>
<div class="callout">唯一硬性要求：<b>强制输出窗口里必须出声</b>。听懂 ≠ 会说，
这两件事在大脑里走的是完全不同的通路。静音听完十遍，一句也不会说。</div>
<div class="foot">IELTS POD · BRUCE KIT · Day 1 / Day 21 各录一次同题对比</div>
</div></body></html>"""


def render_sheet() -> str:
    cells = "".join(
        f"<div class='c'><div class='i mono'>{i:02d}</div><div class='ch'>{E(c['chunk'])}</div>"
        f"<div class='zh'>{E(c['zh'])}</div><div class='wr'>{E(c['wrong'].split('（')[0])}</div></div>"
        for i, c in enumerate(C.CHUNKS, 1)
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
{BASE_CSS}
.page {{ width:1400px; padding:56px; background:#0b0e13; }}
h1 {{ font-size:52px; font-weight:800; }}
.sub {{ color:#96a3b2; font-size:23px; margin-top:8px; }}
.grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:18px; margin-top:34px; }}
.c {{ background:#11161e; border:1px solid #1e2732; border-radius:16px; padding:22px 22px 24px;
  position:relative; min-height:210px; }}
.i {{ position:absolute; right:18px; top:16px; font-size:18px; color:#3d4854; }}
.ch {{ font-size:27px; font-weight:750; color:#4DD0C7; line-height:1.2; }}
.zh {{ font-size:21px; color:#dfe7ee; margin-top:10px; }}
.wr {{ font-size:18px; color:#8b5c5c; margin-top:14px; text-decoration:line-through; line-height:1.35; }}
.foot {{ margin-top:40px; color:#5d6875; font-size:20px; letter-spacing:.1em; }}
</style></head><body><div class="page">
<h1>二十个语块总表</h1>
<div class="sub">贴墙上。每次只想一个：遮住中文说出英语，或遮住英语想起中文。</div>
<div class="grid">{cells}</div>
<div class="foot">IELTS POD · BRUCE KIT · Track 02 详解 · Track 05 睡前重播</div>
</div></body></html>"""


_USE = {
    "01": "第一周主攻。必须张嘴，不许只听。",
    "02": "每天一条通勤路上。第二周开始加 04。",
    "03": "跟读 15 分钟，录音跟自己比。",
    "04": "有一定底子后跑，每天最多一遍。",
    "05": "睡前躺着听，不张嘴。",
}
import build_bruce_audio as _BA  # noqa: E402

_TRACKS = _BA.TRACKS


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    pages: list[tuple[str, str, dict]] = []
    for i, ch in enumerate(C.CHUNKS, 1):
        pages.append((f"chunk_{i:02d}_{ch['id']}.png", render_card(ch, i, len(C.CHUNKS)),
                      {"w": 1080, "h": 1350}))
    for i, f in enumerate(C.FOSSILS, 1):
        pages.append((f"fossil_{i:02d}_{f['id']}.png", render_fossil(f, i, len(C.FOSSILS)),
                      {"w": 1080, "h": 1350}))
    pages += [
        ("poster_01_xray.png", render_xray(), {"full": True}),
        ("poster_02_scaffolds.png", render_scaffolds(), {"full": True}),
        ("poster_03_rhythm.png", render_rhythm(), {"full": True}),
        ("poster_04_protocol.png", render_protocol(), {"full": True}),
        ("poster_05_chunk_sheet.png", render_sheet(), {"full": True}),
    ]

    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, device_scale_factor=2)
        page = ctx.new_page()
        for name, markup, dims in pages:
            src = TMP / name.replace(".png", ".html")
            src.write_text(markup, encoding="utf-8")
            page.goto(src.as_uri())
            page.wait_for_timeout(120)
            if dims.get("full"):
                page.screenshot(path=str(OUT / name), full_page=True)
            else:
                w, h = dims["w"], dims["h"]
                page.set_viewport_size({"width": w, "height": h})
                page.screenshot(path=str(OUT / name), clip={"x": 0, "y": 0, "width": w, "height": h})
                page.set_viewport_size({"width": 1400, "height": 1000})
            print(f"✓ {name}")
        browser.close()
    print(f"\n共 {len(pages)} 张 → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
