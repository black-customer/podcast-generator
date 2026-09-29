"""StepFun StepAudio 2.5 TTS 客户端：清理指令、限流重试与采样率标准化。"""
from __future__ import annotations

import re
import subprocess
import threading
import time
from pathlib import Path

import httpx

from .audio import FFmpegError
from .audioqa import strip_all_tags
from .config import real_stepfun_api_key

API_URL = "https://api.stepfun.com/v1/audio/speech"
TEXT_API_URL = "https://api.stepfun.com/v1/chat/completions"
MODEL = "stepaudio-2.5-tts"
MAX_CHARS = 950
MAX_INSTRUCTION_CHARS = 200


class StepFunError(RuntimeError):
    pass


class StepFunCancelled(RuntimeError):
    pass


def clean_text(text: str) -> str:
    """移除 Fish 标签与会导致 StepFun 拖腔的标点，同时保留原有词句。"""
    cleaned, _ = strip_all_tags(text or "")
    cleaned = cleaned.replace("—", ",").replace("—", ",")
    cleaned = cleaned.replace("...", ", ").replace("…", ", ")
    cleaned = re.sub(r",\s*,+", ",", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().strip(",").strip()


def role_instruction(role: str, source: str = "") -> str:
    """把少量中立表演提示转为 StepFun 的全局自然语言 instruction。"""
    if role == "question":
        base = "Ask as a friendly IELTS interviewer: curious, clear, brief, and natural."
    else:
        base = (
            "Speak as a young English speaker chatting with someone familiar: relaxed, natural, "
            "and sincere, with unforced pacing and no announcer tone."
        )
    cues = []
    lowered = (source or "").lower()
    if "[uncertain]" in lowered:
        cues.append("Let genuine uncertainty show briefly.")
    if "[emphasis]" in lowered:
        cues.append("Use light emphasis only where the meaning needs it.")
    if "[break]" in lowered:
        cues.append("Allow one short thinking pause.")
    return " ".join([base, *cues])[:MAX_INSTRUCTION_CHARS]


def build_payload(
    text: str,
    voice: str,
    instruction: str = "",
    speed: float = 1.0,
) -> dict:
    return {
        "model": MODEL,
        "input": text,
        "voice": voice,
        "response_format": "mp3",
        "sample_rate": 24000,
        "speed": max(0.5, min(2.0, float(speed))),
        "instruction": (instruction or "")[:MAX_INSTRUCTION_CHARS],
    }


def _wait(seconds: float, cancel: threading.Event | None) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        if cancel is not None and cancel.is_set():
            raise StepFunCancelled("已取消")
        time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))


def synthesize(
    text: str,
    voice: str,
    settings: dict,
    instruction: str = "",
    cancel: threading.Event | None = None,
) -> bytes:
    """合成一个不超过 950 字符的段落；429/5xx 有限退避且可取消。"""
    key = real_stepfun_api_key(settings)
    if not key:
        raise StepFunError("未配置 StepFun API Key")
    payload = build_payload(
        text,
        voice=voice,
        instruction=instruction,
        speed=float(settings.get("speed") or 1.0),
    )
    last_error = ""
    for attempt in range(4):
        if cancel is not None and cancel.is_set():
            raise StepFunCancelled("已取消")
        try:
            response = httpx.post(
                API_URL,
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
                timeout=120,
            )
        except httpx.HTTPError as exc:
            last_error = f"网络错误: {exc}"
            if attempt < 3:
                _wait((1, 2, 5)[attempt], cancel)
            continue
        if response.status_code == 200 and len(response.content) > 100:
            return response.content
        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"StepFun API {response.status_code}: {(response.text or '')[:160]}"
            if attempt < 3:
                raw_delay = response.headers.get("Retry-After", "")
                try:
                    delay = float(raw_delay)
                except (TypeError, ValueError):
                    delay = (1, 2, 5)[attempt]
                _wait(min(45.0, max(0.0, delay)), cancel)
            continue
        raise StepFunError(
            f"StepFun API {response.status_code}: {(response.text or '')[:240]}"
        )
    raise StepFunError(f"StepFun 合成重试后仍失败。{last_error}")


def standardize_mp3(path: Path) -> Path:
    """StepFun 24kHz MP3 在拼接前统一到 44.1kHz/mono/128kbps。"""
    target = path.with_suffix(".std.mp3")
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(path),
                "-ar",
                "44100",
                "-ac",
                "1",
                "-b:a",
                "128k",
                str(target),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FFmpegError(f"StepFun 音频标准化失败: {exc}") from exc
    if result.returncode != 0:
        raise FFmpegError(f"StepFun 音频标准化失败: {(result.stderr or '')[-300:]}")
    target.replace(path)
    return path


def test_connection(settings: dict) -> dict:
    key = real_stepfun_api_key(settings)
    if not key:
        return {"ok": True, "mode": "dry_run", "message": "未配置 StepFun Key"}
    try:
        audio = synthesize(
            "Hi.",
            voice=(settings.get("answer_voice_id") or "vibrant-youth"),
            settings=settings,
            instruction="Brief, clear, and natural.",
        )
    except StepFunError as exc:
        return {"ok": False, "message": str(exc)}
    return {
        "ok": len(audio) > 100,
        "mode": "live",
        "message": f"连接成功，模型 {MODEL}",
    }


def test_text_connection(settings: dict) -> dict:
    key = real_stepfun_api_key(settings)
    if not key:
        return {"ok": False, "mode": "dry_run", "message": "未配置 StepFun Key"}
    model = str(settings.get("stepfun_text_model") or "step-5-preview")
    base = str(settings.get("stepfun_text_base_url") or "").rstrip("/")
    url = f"{base}/chat/completions" if base else TEXT_API_URL
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 8,
            },
            timeout=60,
        )
    except httpx.HTTPError as exc:
        return {"ok": False, "message": f"网络错误: {exc}"}
    if response.status_code == 200:
        return {"ok": True, "mode": "live", "message": f"连接成功，模型 {model}"}
    return {
        "ok": False,
        "message": f"StepFun 文本 API {response.status_code}: {(response.text or '')[:160]}",
    }
