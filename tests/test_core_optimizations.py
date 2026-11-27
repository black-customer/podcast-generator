"""核心链路的本地、可重复回归。"""

import json
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from server import (
    alignment,
    arcade,
    audioqa,
    bank,
    capture_distill,
    captures,
    config,
    jobs,
    library,
    mastering,
    oral_review,
    speech_bridge,
    speech_worker,
    study_progress,
    timeline,
    tts,
)
from server.main import app


@pytest.fixture
def item(monkeypatch, tmp_path):
    monkeypatch.setattr(library, "TOPICS_DIR", tmp_path / "topics")
    monkeypatch.setattr(study_progress, "PRIVATE_DIR", tmp_path / "private")
    monkeypatch.setattr(tts, "TMP_DIR", tmp_path / "work")
    topic = library.create_topic("Synthetic")["id"]
    item_id = library.create_item(topic, {"question": "Why?",
                                         "podcast_text": "A: Why?\nB: It helps me unwind."})["id"]
    return topic, item_id, library.item_path(topic, item_id)


def test_bridge_keeps_broken_pipe_cleanup_idempotent(tmp_path):
    bridge = speech_bridge.SpeechBridge([], tmp_path)
    stdin = Mock()
    stdin.close.side_effect = BrokenPipeError
    bridge.process = Mock(stdin=stdin)
    bridge.close()
    bridge.close()
    stdin.close.assert_called_once()


def test_bridge_timeout_counts_wait_for_lock(tmp_path):
    bridge = speech_bridge.SpeechBridge([], tmp_path)
    hold = threading.Event()
    acquired = threading.Event()

    def reserve():
        with bridge.lock:
            acquired.set()
            hold.wait(1)

    worker = threading.Thread(target=reserve)
    worker.start()
    try:
        assert acquired.wait(1)
        with pytest.raises(speech_bridge.SpeechError, match="超时"):
            bridge.call("status", timeout=0.01)
    finally:
        hold.set()
        worker.join()


def test_whisper_shares_multilingual_model(monkeypatch):
    load = Mock(side_effect=lambda *args, **kwargs: object())
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=load))
    try:
        zh = speech_worker._whisper("zh")
        assert speech_worker._whisper(None) is zh
        assert speech_worker._whisper("en") is not zh
        assert [call.args[0] for call in load.call_args_list] == ["base", "base.en"]
    finally:
        if reset := getattr(getattr(speech_worker, "_whisper_model", None), "cache_clear", None):
            reset()


def test_qa_ignores_tags_and_serializes_silent_peak(monkeypatch, tmp_path):
    monkeypatch.setattr(audioqa.subprocess, "run", lambda *a, **k: SimpleNamespace(
        stderr="[Parsed_astats] Peak level dB: -inf\n",
    ))
    text = "A: Why?\nB: It helps."
    assert audioqa.check_duration_ratio("[slowly] " * 60 + text, 2) == (
        audioqa.check_duration_ratio(text, 2)
    )
    json.dumps(audioqa.check_clipping(tmp_path / "silent.mp3"), allow_nan=False)


def test_missing_audio_does_not_return_old_timeline(item):
    topic, item_id, folder = item
    timeline.save_timeline([{"id": 0, "start": 0, "end": 4}], folder / "timeline_podcast.json")
    assert timeline.get_or_create_timeline(topic, item_id)["lines"] == []


def test_default_timeline_uses_recorded_legacy_source_when_tracks_differ(item):
    topic, item_id, folder = item
    script = "A: Why?\nB: It keeps me focused."
    library.update_item_texts(topic, item_id, {"fish_script": script})
    library.update_item_meta(topic, item_id, dialogue=True, tts_source="fish_script")
    audio = folder / "audio.mp3"
    audio.write_bytes(b"fixture audio")
    doc = alignment.build_alignment_doc(
        mode="measured", source_text=script, audio_path=audio,
        segments=[{"text": "Why?", "speaker": "a", "start": 0, "end": 1}],
        track="podcast",
    )
    alignment.save_alignment(doc, folder / "alignment_podcast.json")
    assert timeline.get_or_create_timeline(topic, item_id, "default")["mode"] == "measured"


def test_background_update_cannot_restore_deleted_item(item):
    topic, item_id, folder = item
    library.delete_item(topic, item_id)
    with pytest.raises(FileNotFoundError):
        library.update_item_meta(topic, item_id, stale=False)
    assert not folder.exists()


def test_mastering_clears_partial_files_and_keeps_published_audio(monkeypatch, tmp_path):
    from pathlib import Path

    source = tmp_path / "合成.wav"
    output = tmp_path / "示范.mp3"
    source.write_bytes(b"fixture source")
    output.write_bytes(b"previous audio")

    def timeout(command, **kwargs):
        Path(command[-1]).write_bytes(b"partial")
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(mastering.subprocess, "run", timeout)
    with pytest.raises(mastering.FFmpegError):
        mastering.apply_mastering(source, output)
    assert output.read_bytes() == b"previous audio"
    assert set(tmp_path.iterdir()) == {source, output}


@pytest.mark.parametrize("payload", [{"stage": None}, {"draft": None}, {"facts": None},
                                     {"sentence_index": True}, {"sentence_index": None}])
def test_progress_rejects_invalid_explicit_values(item, payload):
    with pytest.raises(ValueError):
        study_progress.save_progress(*item[:2], payload)


def test_topic_summary_cache_is_not_exposed(item):
    folder = item[2]
    summary = library.item_summary(folder)
    summary["title"] = "Changed outside library"
    assert library.item_summary(folder)["title"] == "Why?"


def test_cancelled_rewrite_does_not_mark_item_error(monkeypatch):
    cancel = threading.Event()
    job = {"id": "fixture", "kind": "api_generate", "topic_id": "topic", "state": "running",
           "done": 0, "errors": [], "cancel_event": cancel}
    monkeypatch.setattr(jobs, "JOBS", {"fixture": job})
    monkeypatch.setattr(jobs, "_ACTIVE_TOPICS", {})
    monkeypatch.setattr(jobs, "_persist_locked", lambda: None)
    error = Mock()
    monkeypatch.setattr(jobs, "library_update_error", error)

    def cancelled(*args, **kwargs):
        cancel.set()
        raise speech_bridge.SpeechCancelled("已取消")

    monkeypatch.setattr(tts, "generate_item_audio", cancelled)
    jobs._run_api_generate("fixture", "topic", "item", None, None)
    assert job["state"] == "cancelled" and job["errors"] == [] and job["done"] == 0
    error.assert_not_called()


def test_today_overview_accepts_capture_reviews(monkeypatch, tmp_path):
    monkeypatch.setattr(oral_review, "REVIEW_FILE", tmp_path / "review.json")
    monkeypatch.setattr(oral_review, "_pending_learning", list)
    monkeypatch.setattr(oral_review, "_reconcile", lambda *args: None)
    state = oral_review._load()
    state["cards"]["capture"] = {"card_kind": "capture", "paused": False, "superseded": False}
    oral_review._write(state)
    assert oral_review.today_overview()["needs_material_count"] == 0


def test_transfer_rejects_stale_sentence(monkeypatch):
    monkeypatch.setattr(oral_review, "_load", lambda: {"cards": {"fixture": {
        "topic_id": "topic", "item_id": "item", "source_fingerprint": "before",
        "sentence_index": 0,
    }}})
    monkeypatch.setattr(arcade.study, "get_material", lambda *args: {"status": "changed"})
    with pytest.raises(ValueError, match="更新|变化"):
        arcade.check_card_transfer("fixture", b"recording", "audio/webm", 1)


def test_model_error_is_not_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(captures, "CAPTURES_DIR", tmp_path / "captures")
    meta = captures.ingest_snippet(text="I keep my options open.")
    request = Mock(return_value='{"error": "模型拒绝提炼"}')
    monkeypatch.setattr(capture_distill.rewrite, "_chat", request)
    with pytest.raises(ValueError):
        capture_distill.distill_capture_api(meta["id"])
    request.assert_called_once()


def test_question_bank_cache_invalidates_on_replace(monkeypatch, tmp_path):
    path = tmp_path / "bank.json"
    path.write_text('{"questions": []}', encoding="utf-8")
    reads = []
    parse = json.loads

    def counted(data, *args, **kwargs):
        reads.append(data)
        return parse(data, *args, **kwargs)

    monkeypatch.setattr(bank.json, "loads", counted)
    assert bank.load_bank(path) == bank.load_bank(path)
    assert len(reads) == 1
    config.atomic_write_text(path, '{"questions": [{"id": "updated"}]}')
    assert bank.load_bank(path)["questions"][0]["id"] == "updated"
    assert len(reads) == 2


def test_study_upload_checks_stream_limit(monkeypatch):
    monkeypatch.setattr(arcade, "MAX_RECORDING_BYTES", 4)
    save = Mock(return_value={"ok": True})
    monkeypatch.setattr(study_progress, "save_recording", save)
    with TestClient(app) as client:
        reply = client.post("/api/topics/topic/items/item/study/recordings",
                            params={"stage": "before", "duration_sec": 1},
                            content=iter([b"abc", b"def"]))
    assert reply.status_code == 413
    save.assert_not_called()
