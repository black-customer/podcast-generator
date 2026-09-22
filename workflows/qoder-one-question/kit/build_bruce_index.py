"""生成 learning_kit_bruce/index.html：双击就能在浏览器里听完、看完、打印。

页面只引用相对路径，整个文件夹拷到手机或 U 盘都不需要服务器。
"""
# ruff: noqa: E501  # 语料与 HTML 模板是数据，折行会让内容不可核对

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import bruce_kit_content as C  # noqa: E402

from server.audio import probe_duration  # noqa: E402

for _stream in (sys.stdout, sys.stderr):  # Windows 控制台默认 GBK，✓ 会崩掉整次构建
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

E = html.escape
KIT = Path(__file__).resolve().parent / "learning_kit_bruce"


def _fmt(sec: float) -> str:
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def build() -> str:
    mpath = KIT / "audio_manifest.json"
    manifest = json.loads(mpath.read_text(encoding="utf-8")) if mpath.exists() else {"tracks": []}
    tracks = {t["track"]: t for t in manifest.get("tracks", [])}

    audio_rows = ""
    for k, desc in TRACK_DESC.items():
        t = tracks.get(k)
        f = KIT / "audio" / f"{TRACK_FILE[k]}.mp3"
        if not f.exists():
            continue
        dur = t["duration"] if t else probe_duration(f)
        wins = len(t["windows"]) if t else 0
        audio_rows += f"""<article class="item">
          <div class="ih"><span class="num">{k}</span><h3>{E(desc)}</h3>
          <span class="meta">{_fmt(dur)} · {wins} 个强制输出窗口</span></div>
          <audio controls preload="none" src="audio/{E(f.name)}"></audio>
        </article>"""

    videos = "".join(
        f"""<article class="item"><div class="ih"><h3>{E(name)}</h3></div>
        <video controls preload="none" src="video/{E(name)}"
          style="width:100%;max-width:420px;border-radius:14px;background:#000"></video></article>"""
        for name in ("chunk_reel.mp4", "repair_lab.mp4")
        if (KIT / "video" / name).exists()
    )

    posters = "".join(
        f'<a class="thumb" href="cards/{E(p)}" target="_blank"><img loading="lazy" src="cards/{E(p)}">'
        f"<span>{E(POSTER_TITLES[p])}</span></a>"
        for p in POSTER_TITLES
        if (KIT / "cards" / p).exists()
    )
    chunks = "".join(
        f'<a class="thumb sm" href="cards/{E(p.name)}" target="_blank">'
        f'<img loading="lazy" src="cards/{E(p.name)}"><span>{E(c["chunk"])}</span></a>'
        for c, p in zip(
            C.CHUNKS,
            [KIT / "cards" / f"chunk_{i:02d}_{c['id']}.png" for i, c in enumerate(C.CHUNKS, 1)],
            strict=True,
        )
        if p.exists()
    )
    fossils = "".join(
        f'<a class="thumb sm" href="cards/{E(p.name)}" target="_blank">'
        f'<img loading="lazy" src="cards/{E(p.name)}"><span>{E(f["label_zh"])}</span></a>'
        for f, p in zip(
            C.FOSSILS,
            [KIT / "cards" / f"fossil_{i:02d}_{f['id']}.png" for i, f in enumerate(C.FOSSILS, 1)],
            strict=True,
        )
        if p.exists()
    )

    metrics = "".join(
        f"<tr><td>{E(m['key'])}</td><td class='bad'>{E(m['yours'])}</td>"
        f"<td class='good'>{E(m['native'])}</td><td class='dim'>{E(m['note'])}</td></tr>"
        for m in C.DIAGNOSIS["metrics"]
    )
    proto = "".join(
        f"<tr><td class='day'>{E(p['day'])}</td><td>{E(p['task'])}</td></tr>" for p in C.PROTOCOL
    )

    return f"""<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bruce 定制口语强化包</title>
<style>
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#0b0e13; color:#e6ecf2; font-family:"Segoe UI Variable Text","Segoe UI",
  "Microsoft YaHei",system-ui,sans-serif; line-height:1.6; }}
.wrap {{ max-width:1180px; margin:0 auto; padding:48px 22px 90px; }}
h1 {{ font-size:40px; letter-spacing:-.02em; margin:0 0 6px; }}
.lead {{ color:#93a0af; font-size:18px; max-width:820px; }}
h2 {{ font-size:15px; letter-spacing:.2em; text-transform:uppercase; color:#E8A33D;
  margin:52px 0 16px; border-bottom:1px solid #1b232e; padding-bottom:10px; }}
.item {{ background:#10151d; border:1px solid #1c2531; border-radius:16px; padding:18px 20px;
  margin-bottom:14px; }}
.ih {{ display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }}
.ih h3 {{ margin:0; font-size:19px; }}
.num {{ color:#E8A33D; font-weight:800; font-family:Consolas,monospace; }}
.meta {{ color:#68757f; font-size:14px; margin-left:auto; }}
audio {{ width:100%; margin-top:12px; height:38px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:14px; }}
.grid.big {{ grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); }}
.thumb {{ display:block; background:#10151d; border:1px solid #1c2531; border-radius:14px;
  overflow:hidden; text-decoration:none; color:#c3ccd6; }}
.thumb img {{ width:100%; display:block; }}
.thumb span {{ display:block; padding:9px 12px 12px; font-size:14px; color:#8d99a8; }}
table {{ width:100%; border-collapse:collapse; font-size:15px; }}
td,th {{ padding:11px 12px 11px 0; border-bottom:1px solid #171e27; text-align:left;
  vertical-align:top; }}
.bad {{ color:#e28c8c; }} .good {{ color:#4DD0C7; }} .dim {{ color:#8d99a8; }}
.day {{ color:#E8A33D; white-space:nowrap; width:120px; }}
.cmd {{ background:#10151d; border:1px solid #1c2531; border-radius:12px; padding:14px 16px;
  font-family:Consolas,monospace; font-size:13.5px; color:#9fb0c0; overflow-x:auto; }}
.rule {{ background:rgba(232,163,61,.08); border:1px solid rgba(232,163,61,.3);
  border-radius:14px; padding:16px 20px; margin-top:18px; }}
.rule b {{ color:#fff; }}
</style></head><body><div class="wrap">
<h1>Bruce 定制口语强化包</h1>
<p class="lead">基于你自己的 11,332 词口语转写稿定制。目标不是教你新知识，
是把你已经会的东西变成张嘴就有的肌肉。诊断结论：<b>{E(C.DIAGNOSIS['estimated_band'])}</b>。</p>
<div class="rule"><b>唯一硬性要求：</b>音频里的提示音窗口必须张嘴出声。
听懂和会说在大脑里走的是两条不同的通路，静音听完十遍，一句也不会说。</div>

<h2>音频 · 五轨</h2>
{audio_rows or '<p class="dim">音频还没生成。</p>'}

<h2>视频 · 竖屏跟读</h2>
<div class="grid">{videos or '<p class="dim">视频还没生成。</p>'}</div>

<h2>海报</h2>
<div class="grid big">{posters}</div>
<h2>语块卡 · 20 张</h2>
<div class="grid">{chunks}</div>
<h2>化石卡 · 10 张</h2>
<div class="grid">{fossils}</div>

<h2>数据说话</h2>
<table><tr><th>指标</th><th>你的</th><th>母语者</th><th>意味着什么</th></tr>{metrics}</table>

<h2>21 天节奏</h2>
<table>{proto}</table>

<h2>重新生成</h2>
<div class="cmd">.venv/Scripts/python scripts/build_bruce_audio.py<br>
.venv/Scripts/python scripts/build_bruce_cards.py<br>
.venv/Scripts/python scripts/build_bruce_video.py<br>
.venv/Scripts/python scripts/build_bruce_index.py</div>
<p class="dim" style="margin-top:26px;font-size:14px">内容唯一来源：scripts/bruce_kit_content.py ·
改内容只改这一个文件，音频、卡片、视频会同步。</p>
</div></body></html>"""


TRACK_DESC = {
    "01": "体检报告 + 十大化石纠错（强制输出）",
    "02": "二十个语块健身房 + 反向检索",
    "03": "影子跟读与句子重音",
    "04": "考官快问快答 + 四步骨架",
    "05": "睡前间隔复习（不张嘴）",
}
TRACK_FILE = {
    "01": "01_xray_repair_lab", "02": "02_chunk_gym", "03": "03_shadow_stress",
    "04": "04_examiner_gauntlet", "05": "05_sleep_review",
}
POSTER_TITLES = {
    "poster_01_xray.png": "英语口语体检报告",
    "poster_02_scaffolds.png": "答案骨架 + 含糊词升级",
    "poster_03_rhythm.png": "重音与意群",
    "poster_04_protocol.png": "怎么用这套材料",
    "poster_05_chunk_sheet.png": "二十个语块总表（贴墙）",
}


def main() -> int:
    out = KIT / "index.html"
    out.write_text(build(), encoding="utf-8")
    print(f"✓ {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
