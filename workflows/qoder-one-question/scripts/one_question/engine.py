"""单题工作流的通用引擎：合成、时间轴、母带、HTML→PNG。

刻意不依赖仓库里的个人材料模块，这样整个 workflows/ 目录可以单独开源出去。
唯一的外部依赖是 server.tts / server.audio（TTS 与 ffmpeg 封装）和 playwright。
"""
# ruff: noqa: E501  # ffmpeg 参数与 HTML 模板是数据，折行反而看不清

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

from server.audio import _concat_line, _run, make_silence, probe_duration
from server.config import TMP_DIR
from server.tts import fish_tts_dialogue

SPEED_SLOW = 0.84


def for_tts(text: str) -> str:
    """去掉 TTS 会读崩的排版符号。"""
    return (text.replace("「", "“").replace("」", "”").replace("｜", "，")
            .replace("→", " to ").replace("\n", " ").strip())


class Synth:
    """带内容哈希缓存的多说话人合成。重跑只花变化的那几次配额。"""

    def __init__(self, settings: dict, cache_dir: Path) -> None:
        self.settings = settings
        self.cache = cache_dir
        self.cache.mkdir(parents=True, exist_ok=True)
        self.stats = {"api_calls": 0, "cache_hits": 0}

    def __call__(self, lines: list[tuple[str, str]], speed: float | None = None) -> Path:
        key = hashlib.sha256(json.dumps(
            [[s, t] for s, t in lines], ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
        out = self.cache / f"{key}.mp3"
        if out.exists() and out.stat().st_size > 2000:
            self.stats["cache_hits"] += 1
            return out
        settings = dict(self.settings) if speed is None else {**self.settings, "speed": speed}
        audio = fish_tts_dialogue([(s, for_tts(t)) for s, t in lines], settings)
        if len(audio) < 1500:
            raise RuntimeError(f"合成结果过短（{len(audio)} bytes）：{lines[0][1][:50]}")
        tmp = self.cache / f"{key}.{uuid.uuid4().hex[:6]}.tmp.mp3"
        tmp.write_bytes(audio)
        tmp.replace(out)
        self.stats["api_calls"] += 1
        return out


class Timeline:
    """攒条目并记录每个片段/窗口的起止，供页面和视频对齐。"""

    def __init__(self) -> None:
        self.entries: list[Path] = []
        self.markers: list[dict] = []
        self.windows: list[dict] = []
        self._t = 0.0

    def clip(self, synth: Synth, lines: list[tuple[str, str]], label: str = "",
             gap: float = 0.0, speed: float | None = None) -> Timeline:
        if gap > 0:
            self.entries.append(make_silence(gap))
            self._t += gap
        path = synth(lines, speed=speed)
        dur = probe_duration(path)
        self.entries.append(path)
        if label:
            self.markers.append({"label": label, "start": round(self._t, 2), "duration": round(dur, 2)})
        self._t += dur
        return self

    def window(self, seconds: float, label: str = "", cache: Path | None = None) -> Timeline:
        start = self._t
        for freq in (660,):
            self.entries.append(_cue(freq, 0.22, cache))
            self._t += 0.22
        self.entries.append(make_silence(seconds))
        self._t += seconds
        self.entries.append(_cue(880, 0.22, cache))
        self._t += 0.22
        self.windows.append({"start": round(start, 2), "end": round(self._t, 2),
                             "label": label, "seconds": seconds})
        return self

    def rest(self, seconds: float) -> Timeline:
        self.entries.append(make_silence(seconds))
        self._t += seconds
        return self

    @property
    def scheduled(self) -> float:
        return self._t

    def render(self, out_path: Path) -> dict:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        list_file = TMP_DIR / f"oq-concat-{uuid.uuid4().hex[:8]}.txt"
        list_file.write_text("\n".join(_concat_line(p) for p in self.entries) + "\n", encoding="utf-8")
        try:
            _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                  "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                  "-ar", "44100", "-ac", "1", "-b:a", "128k", str(out_path)])
        finally:
            list_file.unlink(missing_ok=True)
        return {"file": out_path.name, "duration": round(probe_duration(out_path), 2),
                "markers": self.markers, "windows": self.windows}


def _cue(freq: int, seconds: float, cache: Path | None) -> Path:
    base = cache or TMP_DIR
    base.mkdir(parents=True, exist_ok=True)
    out = base / f"cue-{freq}-{seconds:.2f}.mp3"
    if not out.exists():
        tmp = base / f"{out.stem}.{uuid.uuid4().hex[:6]}.tmp.mp3"
        _run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
              "-af", f"afade=t=in:ss=0:d=0.02,afade=t=out:st={seconds - 0.08}:d=0.08,volume=0.3",
              "-ar", "44100", "-ac", "1", "-b:a", "128k", str(tmp)])
        tmp.replace(out)
    return out


def html_to_png(pages: list[tuple[Path, str, dict]], scale: int = 2) -> None:
    """把 (目标png, html, 尺寸) 渲染成图。尺寸含 full=True 时按整页截。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        ctx = browser.new_context(viewport={"width": 1400, "height": 1000}, device_scale_factor=scale)
        page = ctx.new_page()
        for out, markup, dims in pages:
            out = out.resolve()
            src = out.with_suffix(".html")
            src.write_text(markup, encoding="utf-8")
            page.goto(src.as_uri())
            page.wait_for_timeout(150)
            if dims.get("full"):
                page.screenshot(path=str(out), full_page=True)
            else:
                w, h = dims["width"], dims["height"]
                page.set_viewport_size({"width": w, "height": h})
                if dims.get("fit"):
                    # 内容超过卡高就整体缩放，宁可字小一点，也绝不裁掉最后一块
                    actual = page.evaluate(
                        "() => Math.max(...[...document.querySelectorAll('.c')]"
                        ".map(el => el.getBoundingClientRect().height))")
                    if actual > h + 1:
                        page.evaluate("([ratio]) => { document.querySelector('.c').style.zoom "
                                      "= String(1 / ratio); }", [actual / h])
                        page.wait_for_timeout(60)
                page.screenshot(path=str(out), clip={"x": 0, "y": 0, "width": w, "height": h})
                page.set_viewport_size({"width": 1400, "height": 1000})
            src.unlink(missing_ok=True)
        browser.close()


def loudness(path: Path) -> dict:
    import re
    import subprocess
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path),
                          "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stderr
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", err)
    lra = re.search(r"LRA:\s+([\d.]+) LU", err)
    return {"integrated_lufs": float(i.group(1)) if i else None,
            "lra_lu": float(lra.group(1)) if lra else None}


def say_ok(msg: str) -> None:
    """Windows 控制台默认 GBK，✓ 会抛 UnicodeEncodeError 把整次构建弄崩。"""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    print(msg)
