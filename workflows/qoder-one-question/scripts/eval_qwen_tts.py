"""Qwen TTS 测评：qwen-audio-3.1-tts-next（WebSocket）vs qwen3-tts-flash（HTTP）vs StepFun。

为什么需要三个引擎对照：TTS 的"好不好"只有耳朵能判，我能做的是把同一批文本
在三个引擎下各合成一遍、量出客观指标（延迟/时长/响度/采样率），再给一个 A/B 页面
让人一次点完。自然度结论必须由人来下，脚本不下。

用法：
    .venv/Scripts/python scripts/eval_qwen_tts.py
产物：workflows/qoder-one-question/eval/ 下的音频 + results.json + index.html
"""
# ruff: noqa: E501  # 用例文本与 WS 报文是数据，折行会看不清

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import threading
import time
import wave

import httpx

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

OUT = HERE.parent / "eval"
OUT.mkdir(parents=True, exist_ok=True)

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass

MODEL_ANSWER = ("I don't really have a favourite teacher, as such. I've had good teachers, but I was "
                "never close to any of them — I'm the quiet one who sits at the back. They delivered "
                "the lesson, I took the notes, and that was that. If you ask who's actually taught me "
                "the most recently, what comes to mind isn't a person at all — it's an AI. It answers "
                "questions without judging me for asking them, which is exactly what I couldn't do in "
                "a classroom.")

CASES = [
    {"id": "zh-coach", "label": "纯中文（教练台词）", "voice_f": "Cherry", "voice_m": "Ethan",
     "text": "先看这一处。你的原话是，我没有特别喜欢的老师。"},
    {"id": "en-answer", "label": "纯英文（示范句）", "voice_f": "Cherry", "voice_m": "Ethan",
     "text": "I don't really have a favourite teacher, as such."},
    {"id": "mixed", "label": "中英混排（最难的）", "voice_f": "Cherry", "voice_m": "Ethan",
     "text": "先看这一处。你的原话是：I don't have kind of favorite teacher。"},
    {"id": "proper", "label": "专有名词与数字", "voice_f": "Cherry", "voice_m": "Ethan",
     "text": "J. Cole, 2016, band 6.5, and the phrase as such."},
    {"id": "long", "label": "长段落（84 词示范答案）", "voice_f": "Cherry", "voice_m": "Ethan",
     "text": MODEL_ANSWER},
    {"id": "instruct", "label": "语气指令（慢、温和）", "voice_f": "Cherry", "voice_m": "Ethan",
     "text": "I don't really have a favourite teacher, as such.",
     "instructions": "Speak slowly and warmly, with a slight smile, like a patient tutor."},
]


# ---------------------------------------------------------------- 引擎
def qwen_ws(case: dict) -> bytes:
    """qwen-audio-3.1-tts-next：DashScope 网关协议，文本放在 parameters.text_prompt。

    两条 SDK 路径都试过且都不通：QwenTtsRealtime 说 OpenAI 风格 realtime 协议，
    这个端点报 Missing required parameter 'header.action'；tts_v2.SpeechSynthesizer
    走网关协议但把文本塞在 payload.input.text，这个模型报 text_prompt must not be empty。
    实测唯一可用组合：网关协议 + parameters.text_prompt，音频以二进制帧返回。
    """
    import uuid

    import websocket

    st = _settings()
    base = st["qwen_base_url"].replace("https://", "wss://")
    buf = bytearray()
    done = threading.Event()
    err: list[str] = []
    tid = uuid.uuid4().hex

    last_byte = [0.0]

    def on_msg(ws, message):
        if isinstance(message, (bytes, bytearray)):
            buf.extend(message)
            last_byte[0] = time.monotonic()
            return
        try:
            ev = json.loads(message)
        except ValueError:
            return
        event = ev.get("header", {}).get("event", "")
        if event == "task-failed":
            err.append(ev["header"].get("error_message", "unknown"))
            done.set()
        elif event == "task-finished":
            done.set()

    ws = websocket.WebSocketApp(
        base + "/api-ws/v1/inference",
        header={"Authorization": f"Bearer {st['qwen_api_key']}"},
        on_message=on_msg,
        on_error=lambda w, e: (err.append(str(e)), done.set()),
        on_close=lambda *a: done.set())
    thread = threading.Thread(target=ws.run_forever, daemon=True)
    thread.start()
    time.sleep(1.0)
    ws.send(json.dumps({
        "header": {"action": "run-task", "task_id": tid, "streaming": "duplex"},
        "payload": {"task_group": "audio", "task": "tts", "function": "SpeechSynthesizer",
                    "model": "qwen-audio-3.1-tts-next",
                    "parameters": {"voice": case["voice_m"], "format": "pcm",
                                   "sample_rate": 24000, "text_prompt": case["text"],
                                   **({"instructions": case["instructions"]}
                                      if case.get("instructions") else {})},
                    "input": {}}}))
    ws.send(json.dumps({"header": {"action": "finish-task", "task_id": tid, "streaming": "duplex"},
                        "payload": {"input": {}}}))
    # 这个端点发完音频后不发 task-finished、连接挂着，所以不能只等终止事件：
    # 收到过音频且 3 秒没有新帧就视为结束，自己关连接。
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if done.wait(0.2):
            break
        if last_byte[0] and time.monotonic() - last_byte[0] > 3.0:
            break
    ws.close()
    if err:
        raise RuntimeError(f"task-failed: {err[0]}")
    if not buf:
        raise RuntimeError("没有收到任何音频帧")
    return _pcm_to_wav(bytes(buf), 24000)


def qwen_http(case: dict) -> bytes:
    """qwen3-tts-flash：DashScope 原生 HTTP，扁平 input，返回 OSS wav 链接。"""
    st = _settings()
    r = httpx.post(st["qwen_base_url"] + "/api/v1/services/aigc/multimodal-generation/generation",
                   headers={"Authorization": f"Bearer {st['qwen_api_key']}",
                            "Content-Type": "application/json"},
                   json={"model": "qwen3-tts-flash",
                         "input": {"text": case["text"], "voice": case["voice_m"],
                                   "language_type": "English" if case["text"][:1].isascii()
                                   and not any("一" <= ch <= "鿿" for ch in case["text"]) else "Chinese"},
                         "parameters": {"instructions": case.get("instructions", "")}
                         if case.get("instructions") else {}},
                   timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:160]}")
    url = r.json()["output"]["audio"]["url"]
    wav = httpx.get(url, timeout=60).content
    return wav


def stepfun(case: dict) -> bytes:
    from server import stepfun as sf

    st = _settings()
    return sf.synthesize(case["text"], st.get("answer_voice_id") or "vibrant-youth", st,
                         instruction=case.get("instructions", ""))


ENGINES = {
    "qwen-next-ws": qwen_ws,
    "qwen-flash-http": qwen_http,
    "stepfun": stepfun,
}


def _settings() -> dict:
    return json.loads((REPO / "data" / "settings.json").read_text(encoding="utf-8"))


def _pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    tmp = OUT / "_tmp.pcm"
    tmp.write_bytes(pcm)
    wav = OUT / "_tmp.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    data = wav.read_bytes()
    tmp.unlink(missing_ok=True)
    wav.unlink(missing_ok=True)
    return data


def _probe(path: pathlib.Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration:stream=sample_rate", "-of", "json", str(path)],
                         capture_output=True, text=True).stdout
    d = json.loads(out)
    sr = d["streams"][0].get("sample_rate") if d.get("streams") else None
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(path),
                          "-af", "ebur128=framelog=quiet", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    import re
    m = re.search(r"I:\s+(-?[\d.]+) LUFS", err)
    return {"duration_s": round(float(d["format"]["duration"]), 2),
            "sample_rate": int(sr) if sr else None,
            "integrated_lufs": float(m.group(1)) if m else None,
            "size_kb": path.stat().st_size // 1024}


def main() -> int:
    results = []
    for case in CASES:
        for name, fn in ENGINES.items():
            dest = OUT / f"{case['id']}__{name}.wav"
            t0 = time.time()
            try:
                audio = None
                last_exc = None
                for attempt in range(2):   # TTS 上游会偶发 cancel，重试一次
                    try:
                        audio = fn(case)
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_exc = exc
                        if attempt:
                            raise
                        time.sleep(3)
                if audio is None:
                    raise last_exc
                dest.write_bytes(audio)
                wall = round(time.time() - t0, 1)
                info = _probe(dest)
                info.update({"engine": name, "case": case["id"], "label": case["label"],
                             "wall_s": wall, "ok": True, "file": dest.name})
                print(f"✓ {case['id']:9s} {name:16s} {info['duration_s']:6.2f}s  "
                      f"wall {wall:5.1f}s  {info['sample_rate']}Hz  {info['integrated_lufs']} LUFS")
            except Exception as exc:  # noqa: BLE001
                info = {"engine": name, "case": case["id"], "label": case["label"],
                        "ok": False, "error": f"{type(exc).__name__}: {exc}"[:220],
                        "wall_s": round(time.time() - t0, 1)}
                print(f"✗ {case['id']:9s} {name:16s} {info['error'][:110]}")
            results.append(info)
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    _write_page(results)
    ok = sum(1 for r in results if r["ok"])
    print(f"\n{ok}/{len(results)} 条成功 → {OUT}")
    return 0


def _write_page(results: list[dict]) -> None:
    rows = []
    for case in CASES:
        cells = []
        for name in ENGINES:
            r = next((x for x in results if x["case"] == case["id"] and x["engine"] == name), None)
            if not r or not r["ok"]:
                cells.append(f"<td class='bad'>{(r or {}).get('error', '无记录')[:90]}</td>")
                continue
            cells.append(
                f"<td><audio controls src='{r['file']}' preload='none'></audio>"
                f"<div class='m'>{r['duration_s']}s · wall {r['wall_s']}s · "
                f"{r['sample_rate']}Hz · {r['integrated_lufs']} LUFS</div></td>")
        rows.append(f"<tr><th>{case['label']}<div class='q'>{case['text'][:60]}</div></th>"
                    + "".join(cells) + "</tr>")
    head = "<th></th>" + "".join(f"<th>{n}</th>" for n in ENGINES)
    (OUT / "index.html").write_text(f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Qwen TTS 测评 A/B</title>
<style>body{{margin:0;background:#0b0e13;color:#e6ecf2;font-family:"Segoe UI","Microsoft YaHei",sans-serif;
line-height:1.6}}.w{{max-width:1200px;margin:0 auto;padding:36px 18px}}h1{{font-size:26px}}
p.l{{color:#93a0af;font-size:15px}}table{{width:100%;border-collapse:collapse;font-size:14px}}
th,td{{padding:12px 10px;border-bottom:1px solid #1b232e;vertical-align:top;text-align:left}}
th{{color:#E8A33D;font-size:15px}}td audio{{width:260px;height:36px}}
.m{{color:#68757f;font-size:12px;margin-top:6px}}.q{{color:#68757f;font-size:12px;font-weight:400}}
.bad{{color:#e28c8c;font-size:12px}}</style></head><body><div class="w">
<h1>Qwen TTS 测评：同一批文本，三个引擎</h1>
<p class="l">自然度只有你的耳朵能判。逐行点播放对比；客观指标（时长/延迟/采样率/响度）在每条下面。
qwen-next-ws = qwen-audio-3.1-tts-next（WebSocket）；qwen-flash-http = qwen3-tts-flash（HTTP）；
stepfun = 现在工作流在用的 stepaudio-2.5-tts，作基线。</p>
<table><tr>{head}</tr>{''.join(rows)}</table>
</div></body></html>""", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
