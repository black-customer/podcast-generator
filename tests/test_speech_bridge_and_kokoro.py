import sys
import wave
from pathlib import Path
from types import ModuleType

import pytest

from server import audio, config, speech_bridge, speech_worker, tts
from server.speech_bridge import SpeechBridge, SpeechError


def test_status_does_not_load_torch(monkeypatch, tmp_path):
    backend = ModuleType("backend")
    backend.config = ModuleType("backend.config")
    backend.config.KOKORO_MODEL_PATH = tmp_path / "model"
    backend.config.KOKORO_VOICES_PATH = tmp_path / "voices"
    backend.config.KOKORO_MODEL_PATH.touch()
    backend.config.KOKORO_VOICES_PATH.touch()
    profile = ModuleType("backend.engine.voice_profile")
    profile.get_voice_profile = lambda: {"finetuned": False}
    monkeypatch.setitem(sys.modules, "backend", backend)
    monkeypatch.setitem(sys.modules, "backend.engine", ModuleType("backend.engine"))
    monkeypatch.setitem(sys.modules, "backend.engine.voice_profile", profile)
    monkeypatch.setitem(sys.modules, "torch", None)

    info = speech_worker.status()
    assert info["kokoro"] and info["profile"]["finetuned"] is False
    assert info["gpu"] is None


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


def test_bridge_restarts_after_worker_reports_memory_failure(tmp_path):
    worker = tmp_path / "worker.py"
    worker.write_text(
        "import json, os, sys\n"
        "for line in sys.stdin:\n"
        " r = json.loads(line)\n"
        " data = {'error': '内存不足', 'reset': True} if r['method'] == 'clone' else "
        "{'result': {'pid': os.getpid()}}\n"
        " print(json.dumps({'id': r['id'], **data}), flush=True)\n",
        encoding="utf-8",
    )
    bridge = SpeechBridge([sys.executable, "-u", str(worker)], tmp_path)
    try:
        before = bridge.call("status")
        with pytest.raises(SpeechError, match="内存不足"):
            bridge.call("clone")
        assert bridge.call("status") != before
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


def test_reference_word_boundaries_correct_bias_without_crossing():
    aligned = {"duration": 0.4, "words": [
        {"word": "I", "start": 0.04, "end": 0.1},
        {"word": "swim", "start": 0.14, "end": 0.24},
        {"word": "fast", "start": 0.32, "end": 0.39},
        {"word": "today", "start": 0, "end": 0},
    ]}

    words = speech_worker.reference_playback_words(aligned)

    assert [row["text"] for row in words] == ["I", "swim", "fast"]
    assert words[0]["start"] == 0 and words[-1]["end"] == 0.4
    assert words[0]["end"] == words[1]["start"] == 0.104
    assert words[1]["end"] == words[2]["start"] == 0.264
    assert aligned["words"][0]["start"] == 0.04


def test_reference_alignment_keeps_time_for_spoken_numbers(tmp_path):
    calls = []
    wav = tmp_path / "sample.wav"

    def align(path, text, *, reference):
        assert path == wav and reference
        calls.append(text)
        spoken = "in two thousand twenty three"
        rows = [("in", 0.08, 1.14)] if text == "In 2023?" else [
            ("in", 0.08, 0.18), ("two", 0.22, 0.36), ("thousand", 0.37, 0.63),
            ("twenty", 0.65, 0.84), ("three", 0.86, 1.14),
        ]
        return {"duration": 1.23, "greedy_transcript": spoken, "words": [
            {"word": word, "start": start, "end": end} for word, start, end in rows
        ]}

    words = speech_worker.align_reference_words(wav, "In 2023?", align)

    assert calls == ["In 2023?", "in two thousand twenty three"]
    assert [row["text"] for row in words] == ["In", "2023"]
    assert words[0]["end"] == words[1]["start"] == 0.184
    assert words[1]["end"] == 1.166


@pytest.mark.parametrize("text", ["I swim.", "I swim 200 metres."])
def test_reference_alignment_uses_original_result_when_number_reading_is_unclear(tmp_path, text):
    calls = []

    def align(_path, reference_text, **_kwargs):
        calls.append(reference_text)
        return {"duration": 1.4, "greedy_transcript": "i swing", "words": [
            {"word": "I", "start": 0.08, "end": 0.16},
            {"word": "swim", "start": 0.2, "end": 0.37},
        ]}

    words = speech_worker.align_reference_words(tmp_path / "sample.wav", text, align)

    assert calls == [text]
    assert [row["text"] for row in words] == ["I", "swim"]
