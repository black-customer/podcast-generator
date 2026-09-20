"""R02：StepFun provider 参数、限流、角色音色与主链分发。"""
from pathlib import Path

import pytest

from server import config, production, tts


def test_stepfun_payload_is_bounded_and_uses_fixed_model():
    from server import stepfun

    payload = stepfun.build_payload(
        "Hello there.",
        voice="vibrant-youth",
        instruction="x" * 260,
        speed=1.1,
    )
    assert payload == {
        "model": "stepaudio-2.5-tts",
        "input": "Hello there.",
        "voice": "vibrant-youth",
        "response_format": "mp3",
        "sample_rate": 24000,
        "speed": pytest.approx(1.1),
        "instruction": "x" * 200,
    }


def test_stepfun_cleaning_strips_fish_cues_but_keeps_words():
    from server import stepfun

    cleaned = stepfun.clean_text("[relaxed] Well—I guess... that works. [break]")
    assert "[" not in cleaned
    assert "Well" in cleaned and "that works" in cleaned
    assert "—" not in cleaned and "..." not in cleaned


def test_stepfun_retries_429_without_leaking_key(monkeypatch):
    from server import stepfun

    seen = []

    class Response:
        def __init__(self, status_code, content=b"", headers=None):
            self.status_code = status_code
            self.content = content
            self.headers = headers or {}
            self.text = "rate limited"

    audio_bytes = b"a" * 200
    responses = [Response(429, headers={"Retry-After": "0"}), Response(200, audio_bytes)]

    def fake_post(url, headers, json, timeout):
        del url, json, timeout
        seen.append(dict(headers))
        return responses.pop(0)

    monkeypatch.setattr(stepfun.httpx, "post", fake_post)
    got = stepfun.synthesize(
        "Hi.",
        voice="lively-girl",
        settings={"stepfun_api_key": "secret-step-key"},
    )
    assert got == audio_bytes
    assert len(seen) == 2
    assert all(h["Authorization"] == "Bearer secret-step-key" for h in seen)


def test_stepfun_standardize_uses_44100_mono(monkeypatch, tmp_path):
    from server import stepfun

    src = tmp_path / "line.mp3"
    src.write_bytes(b"raw")
    commands = []

    class Result:
        returncode = 0
        stderr = ""

    def fake_run(cmd, **kwargs):
        del kwargs
        commands.append(cmd)
        Path(cmd[-1]).write_bytes(b"standard")
        return Result()

    monkeypatch.setattr(stepfun.subprocess, "run", fake_run)
    stepfun.standardize_mp3(src)
    assert src.read_bytes() == b"standard"
    assert "44100" in commands[0]
    assert commands[0][commands[0].index("-ac") + 1] == "1"


def test_stepfun_voice_catalog_has_both_genders():
    voices = [v for v in production.get_voice_catalog() if v.get("provider") == "stepfun"]
    assert len([v for v in voices if v["gender"] == "male"]) >= 2
    assert len([v for v in voices if v["gender"] == "female"]) >= 2
    assert all(v.get("voice_id") and v.get("accent") for v in voices)


def test_provider_defaults_and_legacy_fish_migration(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", settings_file)
    assert config.load_settings()["tts_provider"] == "stepfun"

    settings_file.write_text('{"fish_api_key":"fish-key"}', encoding="utf-8")
    assert config.load_settings()["tts_provider"] == "fish"


def test_tts_dispatches_stepfun_provider(monkeypatch, tmp_path):
    called = {}

    def fake_stepfun(src, out_path, settings, force_monologue=False, cancel=None):
        called.update(src=src, settings=settings, force=force_monologue, cancel=cancel)
        Path(out_path).write_bytes(b"audio")
        return (1.0, 1, False, "stepfun_monologue", [], [])

    monkeypatch.setattr(tts, "_synthesize_stepfun_source", fake_stepfun)
    result = tts._synthesize_source(
        "Hello", tmp_path / "out.mp3", {"tts_provider": "stepfun", "dry_run": True}
    )
    assert result[3] == "stepfun_monologue"
    assert called["src"] == "Hello"
