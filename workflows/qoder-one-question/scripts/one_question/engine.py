"""单题工作流的通用引擎：合成、时间轴、母带、HTML→PNG。

刻意不依赖仓库里的个人材料模块，这样整个 workflows/ 目录可以单独开源出去。
唯一的外部依赖是 server.tts / server.audio（TTS 与 ffmpeg 封装）和 playwright。
"""
# ruff: noqa: E501  # ffmpeg 参数与 HTML 模板是数据，折行反而看不清

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import time
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
        provider = str(self.settings.get("tts_provider") or "stepfun")
        voices = (str(self.settings.get("question_voice_id") or ""),
                  str(self.settings.get("answer_voice_id") or ""))
        key = hashlib.sha256(json.dumps(
            {"lines": [[s, t] for s, t in lines], "speed": speed,
             "provider": provider, "voices": voices},
            ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
        out = self.cache / f"{key}.mp3"
        if out.exists() and out.stat().st_size > 2000:
            self.stats["cache_hits"] += 1
            return out
        settings = dict(self.settings) if speed is None else {**self.settings, "speed": speed}
        if provider == "stepfun":
            audio = _stepfun_dialogue(lines, settings)
        elif provider == "qwen":
            audio = _qwen_dialogue(lines, settings)
        else:
            audio = fish_tts_dialogue([(s, for_tts(t)) for s, t in lines], settings)
        if len(audio) < 1500:
            raise RuntimeError(f"合成结果过短（{len(audio)} bytes）：{lines[0][1][:50]}")
        tmp = self.cache / f"{key}.{uuid.uuid4().hex[:6]}.tmp.mp3"
        tmp.write_bytes(audio)
        tmp.replace(out)
        self.stats["api_calls"] += 1
        return out


_last_call = 0.0


def _throttle(settings: dict) -> None:
    """StepFun 免费档限 10 RPM，超了就 429。这里主动把节奏压到限额以内，
    而不是靠上游重试硬撞——重试撞多了整条构建会白等。"""
    global _last_call
    rpm = float(settings.get("stepfun_rpm") or 9)
    min_interval = 60.0 / max(1.0, rpm)
    wait = _last_call + min_interval - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _stepfun_dialogue(lines: list[tuple[str, str]], settings: dict) -> bytes:
    """StepFun 一次只能一个音色，所以逐行合成再拼起来。

    Bruce 规则：回答（B 行）用男声，提问与教练（A 行）用女声。
    """
    from server import stepfun

    qv = str(settings.get("question_voice_id") or "lively-girl")
    av = str(settings.get("answer_voice_id") or "vibrant-youth")
    gap = float(settings.get("stepfun_gap_ms") or 280) / 1000.0

    pieces: list[Path] = []
    work = Path(tempfile.mkdtemp(prefix="oq-sf-"))
    try:
        for i, (speaker, text) in enumerate(lines):
            cleaned = stepfun.clean_text(for_tts(text))
            if not cleaned:
                continue
            voice = qv if speaker == "a" else av
            _throttle(settings)
            role = "question" if speaker == "a" else "answer"
            audio = stepfun.synthesize(cleaned, voice, settings,
                                       instruction=stepfun.role_instruction(role, cleaned))
            f = work / f"{i:03d}.mp3"
            f.write_bytes(audio)
            pieces.append(f)
            if gap > 0 and i < len(lines) - 1:
                pieces.append(make_silence(gap))
        if not pieces:
            raise RuntimeError("StepFun 没有产出任何一行")
        list_file = work / "concat.txt"
        list_file.write_text("\n".join(_concat_line(p) for p in pieces) + "\n", encoding="utf-8")
        merged = work / "merged.mp3"
        _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(list_file),
              "-ar", "44100", "-ac", "1", "-b:a", "128k", str(merged)])
        return merged.read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _raw_settings() -> dict:
    """直接读 data/settings.json。

    server.config.load_settings() 只保留 DEFAULT_SETTINGS 白名单里的键，
    所以工作流自己的 qwen_* 配置到不了引擎。刻意不改产品代码，这里自己读一次。
    """
    try:
        from server.config import SETTINGS_FILE

        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001  文件缺失或损坏时退回传入的 settings
        return {}


def _qwen_post(endpoint: str, key: str, text: str, voice: str, lang: str) -> str:
    """合成一行，返回 OSS 音频地址。"""
    import httpx

    resp = httpx.post(endpoint,
                      headers={"Authorization": f"Bearer {key}",
                               "Content-Type": "application/json"},
                      json={"model": "qwen3-tts-flash",
                            "input": {"text": text, "voice": voice, "language_type": lang}},
                      timeout=180)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:160]}")
    return resp.json()["output"]["audio"]["url"]


def _qwen_fetch(url: str) -> bytes:
    import urllib.request

    with urllib.request.urlopen(url, timeout=120) as fh:
        return fh.read()


def _qwen_dialogue(lines: list[tuple[str, str]], settings: dict) -> bytes:
    """qwen3-tts-flash：HTTP 逐行合成，取回 OSS wav 后统一转 44.1k 单声道 mp3。

    刻意不用 qwen-audio-3.1-tts-next：实测首字节 17.5 秒（对照组同样），
    且超过约 350 字符就被上游掐断（Remote cancelled grpc stream，3/3 复现），
    做不了批量教学音频。结论与原始数据见 eval/results.json。
    """
    import tempfile


    raw = _raw_settings()
    pick = lambda k, d="": str(settings.get(k) or raw.get(k) or d)  # noqa: E731

    base = pick("qwen_base_url").rstrip("/")
    key = pick("qwen_api_key")
    if not base or not key:
        raise RuntimeError("未配置 qwen_base_url / qwen_api_key（data/settings.json）")
    female = pick("qwen_voice_female", "Cherry")
    male = pick("qwen_voice_male", "Ethan")
    gap = float(pick("qwen_gap_ms", "300")) / 1000.0
    endpoint = base + "/api/v1/services/aigc/multimodal-generation/generation"

    pieces: list[Path] = []
    work = Path(tempfile.mkdtemp(prefix="oq-qwen-"))

    def retry(what, *args, attempts: int = 3):
        """一次课要发约 60 个请求，瞬时超时是常态，不能让整个轨道因为一次抖动前功尽弃。"""
        last: Exception | None = None
        for n in range(attempts):
            try:
                return what(*args)
            except Exception as exc:  # noqa: BLE001
                last = exc
                if n < attempts - 1:
                    time.sleep(2.0 * (n + 1))
        raise RuntimeError(f"Qwen 请求 {attempts} 次仍失败：{type(last).__name__}: {last}")

    try:
        for i, (speaker, text) in enumerate(lines):
            cleaned = for_tts(text)
            if not cleaned:
                continue
            has_cjk = any("一" <= ch <= "鿿" for ch in cleaned)
            voice = female if speaker == "a" else male
            lang = "Auto" if has_cjk else "English"
            url = retry(_qwen_post, endpoint, key, cleaned, voice, lang)
            raw = work / f"{i:03d}.src"
            raw.write_bytes(retry(_qwen_fetch, url))
            mp3 = work / f"{i:03d}.mp3"
            _run(["ffmpeg", "-y", "-v", "error", "-i", str(raw),
                  "-ar", "44100", "-ac", "1", "-b:a", "128k", str(mp3)])
            pieces.append(mp3)
            if gap > 0 and i < len(lines) - 1:
                pieces.append(make_silence(gap))
        if not pieces:
            raise RuntimeError("Qwen 没有产出任何一行")
        list_file = work / "concat.txt"
        joined = "\n".join(_concat_line(p) for p in pieces)
        list_file.write_text(joined + "\n", encoding="utf-8")
        merged = work / "merged.mp3"
        _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(list_file),
              "-ar", "44100", "-ac", "1", "-b:a", "128k", str(merged)])
        return merged.read_bytes()
    finally:
        shutil.rmtree(work, ignore_errors=True)


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
