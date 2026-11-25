"""Q02：共享 TTS 参数、音色预设与安全替换回归测试。"""
from pathlib import Path

import pytest

from server import audioqa, production, tts


def test_clean_text_preserves_words_in_legacy_scripts():
    assert tts.clean_text("[relaxed] Well—I guess... that works. [break]") == (
        "Well, I guess, that works."
    )


def test_catalog_contains_six_local_voices_and_clone():
    voices = production.get_voice_catalog()
    assert {v["voice_id"] for v in voices} == {
        "af_bella", "af_heart", "am_puck", "am_liam", "am_michael", "am_fenrir", "golden_self",
    }
    assert {v["provider"] for v in voices} == {"kokoro_local"}


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
