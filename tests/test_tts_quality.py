"""Q02：共享 TTS 参数、音色预设与安全替换回归测试。"""
from pathlib import Path

import pytest

from server import audioqa, production, tts


def test_build_tts_payload_applies_quality_controls():
    payload = tts._build_tts_payload(
        "Hello there.",
        {
            "model": "s2.1-pro-free",
            "speed": 1.03,
            "temperature": 0.78,
        },
        reference_id="voice-a",
    )

    assert payload["reference_id"] == "voice-a"
    assert payload["temperature"] == pytest.approx(0.78)
    assert payload["top_p"] == pytest.approx(0.70)
    assert payload["repetition_penalty"] == pytest.approx(1.20)
    assert payload["condition_on_previous_chunks"] is True
    assert payload["latency"] == "normal"
    assert payload["features"] == ["quality-guard"]
    assert payload["prosody"] == {
        "speed": pytest.approx(1.03),
        "volume": 0,
        "normalize_loudness": True,
    }


def test_tts_headers_reject_paid_model():
    with pytest.raises(tts.TTSError, match="只允许免费模型"):
        tts._tts_headers({"fish_api_key": "k", "model": "s2.1-pro"})


def test_quality_guard_falls_back_when_backend_rejects_it(monkeypatch):
    seen = []

    class Response:
        def __init__(self, status_code, content=b""):
            self.status_code = status_code
            self.content = content
            self.text = "unsupported feature"

    def fake_post(_url, headers, json, timeout):
        del headers, timeout
        seen.append(dict(json))
        return Response(422) if len(seen) == 1 else Response(200, b"audio")

    monkeypatch.setattr(tts.httpx, "post", fake_post)
    got = tts._post_tts({"text": "Hi"}, {"fish_api_key": "k"})
    assert got == b"audio"
    assert seen[0]["features"] == ["quality-guard"]
    assert "features" not in seen[1]


def test_dialogue_reference_order_keeps_male_answer_first():
    refs = tts._dialogue_reference_ids(
        {"reference_id": "male", "reference_id_b": "female", "answer_voice_male": True}
    )
    assert refs == ["male", "female"]


def test_voice_specific_settings_override_global_defaults(monkeypatch):
    monkeypatch.setattr(
        production,
        "find_voice",
        lambda _ref: {"reference_id": "chosen", "speed": 0.98, "temperature": 0.65},
    )
    got = production.voice_generation_settings(
        {"reference_id": "current", "speed": 1.08, "temperature": 0.88}, "chosen"
    )
    assert got["reference_id"] == "chosen"
    assert got["speed"] == pytest.approx(0.98)
    assert got["temperature"] == pytest.approx(0.65)


def test_male_voice_catalog_is_the_fixed_youthful_shortlist():
    males = [v for v in production.get_voice_catalog() if v.get("gender") == "male"]
    assert {v["id"] for v in males} == {
        "alex_young_adult",
        "cand_ethan",
        "cand_elite",
        "cand_adam",
    }
    assert all(v.get("accent") == "American" for v in males)
    assert all(v.get("speed") is not None and v.get("temperature") is not None for v in males)


def test_new_performance_tags_are_allowed():
    src = "[curious] Really? [relaxed] I guess [uncertain] maybe [break] yes."
    cleaned, removed = audioqa.strip_disallowed_tags(src)
    assert cleaned == src
    assert removed == []


def test_podcast_script_has_priority_but_legacy_text_still_falls_back():
    from server import library

    src, field = library.get_track_source_text(
        {"podcast_text": "A: clean\nB: answer", "podcast_script": "A: directed\nB: answer"},
        "podcast",
    )
    assert (src, field) == ("A: directed\nB: answer", "podcast_script")
    src, field = library.get_track_source_text(
        {"podcast_text": "A: legacy\nB: answer", "podcast_script": ""}, "podcast"
    )
    assert (src, field) == ("A: legacy\nB: answer", "podcast_text")


def test_atomic_synthesis_keeps_existing_audio_on_failure(tmp_path, monkeypatch):
    out = tmp_path / "audio_podcast.mp3"
    out.write_bytes(b"old-audio")

    def fail_synthesis(_src, staged, _settings, _force=False, cancel=None):
        Path(staged).write_bytes(b"partial-new-audio")
        raise tts.TTSError("synthetic failure")

    monkeypatch.setattr(tts, "_synthesize_source", fail_synthesis)
    with pytest.raises(tts.TTSError, match="synthetic failure"):
        tts._synthesize_with_qa("A: Hi\nB: Hello", out, {"dry_run": True})

    assert out.read_bytes() == b"old-audio"
    assert not list(tmp_path.glob("*.staging.mp3"))


def test_atomic_synthesis_replaces_existing_only_after_qa_pass(tmp_path, monkeypatch):
    out = tmp_path / "audio_podcast.mp3"
    out.write_bytes(b"old-audio")

    def synth(_src, staged, _settings, _force=False, cancel=None):
        Path(staged).write_bytes(b"new-audio")
        return (1.0, 1, True, "dialogue_single_pass", None, [])

    monkeypatch.setattr(tts, "_synthesize_source", synth)
    monkeypatch.setattr(
        audioqa,
        "run_qa",
        lambda *_a, **_k: {"verdict": "pass", "checks": [], "issues": []},
    )

    result, report, effective, words = tts._synthesize_with_qa(
        "A: Hi\nB: Hello", out, {"dry_run": True}
    )
    assert result[0] == pytest.approx(1.0)
    assert report["verdict"] == "pass"
    assert effective == "A: Hi\nB: Hello"
    assert words == []
    assert out.read_bytes() == b"new-audio"
