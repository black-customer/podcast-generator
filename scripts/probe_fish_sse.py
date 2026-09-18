"""一次性探针：探测 Fish /v1/tts/stream/with-timestamp 的真实 SSE 格式。

输出保存到 data/.tmp/sse_probe.txt（原始事件）供分析，不入库。
用法：.venv/Scripts/python scripts/probe_fish_sse.py
"""
import base64
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx

from server.config import load_settings, real_api_key

ENDPOINT = "https://api.fish.audio/v1/tts/stream/with-timestamp"
OUT = Path("data/.tmp/sse_probe.txt")


def main() -> None:
    s = load_settings()
    key = real_api_key(s)
    if not key:
        print("无 API key，跳过")
        return
    headers = {
        "Authorization": f"Bearer {key}",
        "model": s.get("model") or "s2.1-pro-free",
        "Content-Type": "application/json",
    }
    payload = {
        "text": "Well, I mean, I am technically still a student. "
        "But here is the thing: I switched majors.",
        "format": "mp3",
        "mp3_bitrate": 64,
        "latency": "normal",
        "normalize": True,
        "chunk_length": 100,
    }
    ref = (s.get("reference_id") or "").strip()
    if ref:
        payload["reference_id"] = ref

    OUT.parent.mkdir(parents=True, exist_ok=True)
    events = []
    audio_bytes = bytearray()
    with httpx.stream("POST", ENDPOINT, headers=headers, json=payload, timeout=120) as r:
        print("status:", r.status_code)
        for line in r.iter_lines():
            if not line:
                continue
            events.append(line)
            if line.startswith("data:"):
                try:
                    data = json.loads(line[5:].strip())
                    payload = data.get("audio") or data.get("audio_base64") or ""
                    audio_bytes += base64.b64decode(payload)
                except Exception:
                    pass
    OUT.write_text("\n".join(events), encoding="utf-8")
    (OUT.parent / "sse_probe_audio.mp3").write_bytes(bytes(audio_bytes))
    print(f"events: {len(events)} -> {OUT}")
    print(f"audio bytes: {len(audio_bytes)}")
    # 打印前几个事件的骨架（去掉 base64 大块）
    shown = 0
    for e in events:
        if e.startswith("data:"):
            try:
                d = json.loads(e[5:].strip())
                slim = {
                    k: (f"<{len(v)} chars>" if isinstance(v, str) and len(v) > 80 else v)
                    for k, v in d.items()
                }
                print("DATA:", json.dumps(slim, ensure_ascii=False)[:600])
                shown += 1
            except Exception:
                print("RAW:", e[:200])
                shown += 1
        else:
            print("LINE:", e[:120])
        if shown > 8:
            break


if __name__ == "__main__":
    main()
