import sys
from datetime import date, timedelta
from types import SimpleNamespace

from server import (
    arcade,
    audio,
    library,
    oral_review,
    speech_bridge,
    speech_worker,
    study,
    study_progress,
    tts,
)


def test_fsrs_uses_elapsed_time_and_migrates_existing_schedules():
    today = date(2026, 11, 24)
    old = {"due_date": "2026-11-20", "last_reviewed": "2026-11-13", "interval_days": 7}
    delayed = oral_review.fsrs_review(old, "good", today)
    on_time = oral_review.fsrs_review(old, "good", today - timedelta(days=4))
    assert delayed["stability"] > on_time["stability"] > 7
    forgotten = oral_review.fsrs_review(delayed, "again", today + timedelta(days=1))
    assert forgotten["reps"] == delayed["reps"] + 1
    assert forgotten["lapses"] == 1 and forgotten["stability"] < delayed["stability"]


def test_fluency_counts_observed_words_and_strict_long_pauses():
    words = [
        {"word": "It", "start": 0.5, "end": 0.7},
        {"word": "helps", "start": 1.5, "end": 1.9},
        {"word": "me", "start": 2.9, "end": 3.0},
        {"word": "unwind", "start": 3.05, "end": 3.5},
    ]
    assert speech_worker.analyze_words(words) == {"word_count": 4, "wpm": 80, "long_pauses": 1}
    phrases = ["helps me unwind", "help", "me swim"]
    assert speech_worker.matched_chunks("It helps me unwind.", phrases) == ["helps me unwind"]


def test_mixed_blind_detection_keeps_original_timeline(monkeypatch):
    samples = object()
    chinese = SimpleNamespace(word="游泳", start=0.1, end=1.0)
    english = SimpleNamespace(word="twice a week", start=2.1, end=3.2)
    segments = [SimpleNamespace(text=word.word, words=[word]) for word in (chinese, english)]

    def transcribe(source, **options):
        assert source is samples
        assert options["clip_timestamps"] == [0.0, 1.1, 2.0, 3.3]
        assert options["multilingual"] and not options["condition_on_previous_text"]
        assert not options["vad_filter"]
        return segments, None

    monkeypatch.setitem(sys.modules, "faster_whisper.audio", SimpleNamespace(
        decode_audio=lambda *_args, **_kwargs: samples,
    ))
    monkeypatch.setitem(sys.modules, "faster_whisper.vad", SimpleNamespace(
        VadOptions=lambda **kwargs: kwargs,
        get_speech_timestamps=lambda *_: [{"start": 0, "end": 17600},
                                          {"start": 32000, "end": 52800}],
    ))
    monkeypatch.setattr(speech_worker, "_whisper", lambda _: SimpleNamespace(transcribe=transcribe))
    result = speech_worker.transcribe_and_analyze("synthetic.wav", chunks=["twice a week"])
    assert result["transcript"] == "游泳 twice a week"
    assert result["wpm"] is None and result["long_pauses"] == 1
    assert result["matched_chunks"] == ["twice a week"]


def test_arcade_export(monkeypatch, tmp_path):
    temp = tmp_path / "tmp"
    for module in (arcade, audio, tts):
        monkeypatch.setattr(module, "TMP_DIR", temp)
    monkeypatch.setattr(library, "TOPICS_DIR", tmp_path / "t")
    monkeypatch.setattr(study_progress, "PRIVATE_DIR", tmp_path / "p")
    monkeypatch.setattr(oral_review, "REVIEW_FILE", tmp_path / "oral_review.json")
    settings = {"tts_provider": "kokoro_local", "dry_run": True}
    monkeypatch.setattr(tts, "load_settings", lambda: settings)
    monkeypatch.setattr(arcade, "load_settings", lambda: settings)
    calls = []

    def speech(_settings, method, **params):
        calls.append((method, params))
        return {"transcript": "I swim twice a week", "wpm": 132, "long_pauses": 1,
                "matched_chunks": params.get("chunks", [])}

    monkeypatch.setattr(speech_bridge, "request", speech)
    tid = library.create_topic("游")["id"]
    iid = library.create_item(tid, {"question": "Swim?",
        "original_answer": "I swim two time a week", "podcast_text":
        "A: How often do you swim?\nB: I swim twice a week."})["id"]
    tts.generate_item_audio(tid, iid, track="podcast")
    podcast = library.item_path(tid, iid) / "audio_podcast.mp3"
    tts_duration = audio.probe_duration(podcast)
    library.update_item_meta(tid, iid, dry_run=False)
    row = {"zh": "我每周游两次。", "en": "I swim twice a week.", "explanation": "频率",
           "usage": "次数搭配", "key_chunk": "twice a week", "original_error": {
               "quote": "two time", "issue": "可数名词漏复数", "correction": "two times"}}
    study.save_material(tid, iid, {"complete_chinese": row["zh"], "sentences": [row]})
    take = audio.make_tone(0.9, temp / "take.mp3").read_bytes()
    saved = arcade.transcribe_blind(take, "audio/mpeg", 0.9, "en")
    arcade.attach_blind(saved["blind_token"], tid, iid)
    first = arcade.view(tid, iid)
    assert first["blind"]["analysis"]["long_pauses"] == 1
    assert first["sentences"][0]["audio"]["scope"] == "full_answer"
    assert first["final"] is None

    kwargs = {"upload_key": "retry-1", "fingerprint": first["source_fingerprint"]}
    final = arcade.record(tid, iid, "final", take, "audio/mpeg", 0.9, **kwargs)
    assert final == arcade.record(tid, iid, "final", take, "audio/mpeg", 0.9, **kwargs)
    assert len(calls) == 2 and calls[1][1]["language"] == "en"
    assert arcade.view(tid, iid)["final"]["analysis"]["matched_chunks"] == [row["key_chunk"]]
    assert arcade.recording(tid, iid, final["id"])[0].is_relative_to(tmp_path / "p")

    grade = oral_review.grade_arcade(tid, iid, 0, first["source_fingerprint"], "again", "same-try")
    assert grade == oral_review.grade_arcade(
        tid, iid, 0, first["source_fingerprint"], "again", "same-try"
    )
    expected = [{"category": "plural", "label": "单复数", "count": 1}]
    board = arcade.error_board()
    assert board["top"] == expected
    assert "twice a week" in board["prompt"] and "单复数" in board["prompt"]
    exported = arcade.export(tid, iid)
    answer = first["answer_spans"][0]
    assert abs(audio.probe_duration(exported) - (2.5 + answer["end"] - answer["start"])) < 0.2
    assert exported.is_relative_to(temp) and audio.probe_duration(podcast) == tts_duration

    library.update_item_texts(tid, iid, {"original_answer": "I swim every day."})
    assert arcade.view(tid, iid)["final"] is None
    assert not arcade.error_board()["top"]
