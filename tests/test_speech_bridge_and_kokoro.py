import sys
import wave
from pathlib import Path

import pytest

from server import audio, config, speech_bridge, tts
from server.speech_bridge import SpeechBridge, SpeechError


def test_bridge_reuses_process_and_recovers_after_timeout(tmp_path):
    worker = tmp_path / "test_worker.py"
    worker.write_text(
        "import json, os, sys, time\n"
        "for line in sys.stdin:\n"
        " r = json.loads(line)\n"
        " if r['method'] == 'slow': time.sleep(10)\n"
        " print(json.dumps({'id': r['id'], 'result': {'pid': os.getpid()}}), flush=True)\n",
        encoding="utf-8",
    )
    bridge = SpeechBridge([sys.executable, "-u", str(worker)], tmp_path, idle_seconds=60)
    try:
        first = bridge.call("status")
        assert bridge.call("status") == first
        with pytest.raises(SpeechError, match="超时"):
            bridge.call("slow", timeout=0.1)
        assert bridge.call("status") != first
    finally:
        bridge.close()


def test_local_synthesis_offsets_measured_words(monkeypatch, tmp_path):
    voices = []

    def call(_settings, method, **params):
        assert method == "synthesize_line"
        voices.append(params["voice"])
        with wave.open(str(params["output"]), "wb") as wav:
            wav.setparams((1, 2, 24000, 0, "NONE", "not compressed"))
            wav.writeframes(b"\x00\x00" * 24000)
        return {"voice": params["voice"], "words": [
            {"text": params["text"].split()[0], "start": 0.1, "end": 0.2}
        ]}

    monkeypatch.setattr(speech_bridge, "request", call)
    monkeypatch.setattr(config, "speech_engine_available", lambda _settings: True)
    monkeypatch.setattr(tts, "TMP_DIR", tmp_path)
    monkeypatch.setattr(audio, "TMP_DIR", tmp_path)
    out = tmp_path / "对话.mp3"
    settings = {**config.DEFAULT_SETTINGS, "dry_run": False}
    duration, count, dialogue, _, segments, words = tts._synthesize_source(
        "A: Why?\nB: I swim. I run.", out, settings
    )
    assert count == 3 and dialogue and out.is_file()
    assert voices == ["af_bella", "golden_self", "golden_self"]
    assert [part["text"] for part in segments] == ["Why?", "I swim.", "I run."]
    assert [part["start"] for part in segments] == [0.0, 1.28, 2.4]
    assert [word["start"] for word in words] == [0.1, 1.38, 2.5]
    assert abs(duration - segments[-1]["end"]) < 0.05


def test_local_default_falls_back_without_environment(tmp_path: Path):
    settings = {**config.DEFAULT_SETTINGS, "speech_engine_dir": str(tmp_path)}
    assert settings["tts_provider"] == "kokoro_local"
    assert config.is_dry_run(settings)
