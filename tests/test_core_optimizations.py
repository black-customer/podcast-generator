"""核心链路的本地、可重复回归。"""

import errno
import json
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from server import (
    alignment,
    api,
    arcade,
    audioqa,
    bank,
    capture_distill,
    captures,
    config,
    exports,
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


@pytest.mark.parametrize("windows_error", [False, True], ids=["exdev", "winerror-17"])
def test_atomic_replace_falls_back_across_devices(monkeypatch, tmp_path, windows_error):
    source = tmp_path / "source" / "clip.mp3"
    target = tmp_path / "target" / "clip.mp3"
    for path, contents in ((source, b"new audio"), (target, b"published audio")):
        path.parent.mkdir()
        path.write_bytes(contents)
    replace = config.os.replace

    def replace_on_same_volume(old, new):
        if old.parent != new.parent:
            error = OSError(errno.EINVAL if windows_error else errno.EXDEV, "different volume")
            if windows_error:
                error.winerror = 17
            raise error
        assert new.read_bytes() == b"published audio"
        replace(old, new)

    monkeypatch.setattr(config.os, "replace", replace_on_same_volume)
    config.atomic_replace(source, target)
    assert target.read_bytes() == b"new audio"
    assert not source.exists()
    assert list(target.parent.iterdir()) == [target]


def test_load_bank_mutations_do_not_corrupt_cache(monkeypatch, tmp_path):
    path = tmp_path / "bank.json"
    original = {
        "counts": {"questions": 1},
        "topics": [{"id": "t", "name_zh": "原话题"}],
        "questions": [{"id": "q", "text": "Why?", "topic_id": "t", "part": 1}],
        "sets": [{"id": "s", "start_month": 1, "end_month": 4, "question_ids": ["q"]}],
    }
    path.write_text(json.dumps(original), encoding="utf-8")
    parse = Mock(wraps=json.loads)
    monkeypatch.setattr(bank.json, "loads", parse)
    monkeypatch.setattr(bank, "BANK_PATH", path)
    snapshot = bank.load_bank()
    snapshot["counts"]["questions"] = 0
    snapshot["topics"].append({"id": "new", "name_zh": "新话题"})
    snapshot["topics"][0]["name_zh"] = "改写"
    snapshot["sets"][0]["question_ids"].clear()
    snapshot["questions"].clear()
    assert bank.load_bank() == original
    assert bank.question_part(" Why? ") == 1
    snapshot["questions"].append({
        "id": "fresh", "text": "How?", "topic_id": "new", "part": 2,
    })
    assert bank.find_question(snapshot, "fresh")["part"] == 2
    assert bank.query_questions(snapshot)["items"][0]["topic_name"] == "新话题"
    parse.assert_called_once()


def test_render_dialogue_falls_back_without_voice_profile(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "TMP_DIR", tmp_path)
    monkeypatch.setattr(tts, "is_dry_run", lambda _: False)
    request = Mock()
    monkeypatch.setattr(speech_bridge, "request", request)
    monkeypatch.setattr(tts.audio, "_run", Mock())
    monkeypatch.setattr(tts.audio, "concat_mp3", Mock())

    tts.render_dialogue([("b", "I take the bus.")], tmp_path / "sample.mp3",
                        {"kokoro_answer_voice": "golden_self"})
    assert request.call_args.args[1] == "preview_line"
    assert request.call_args.kwargs["require_profile"] is False


def test_export_m4b_decodes_ffmpeg_output_as_utf8(monkeypatch, tmp_path):
    src = tmp_path / "合成集.mp3"
    src.touch()
    monkeypatch.setattr(exports, "EPISODES_DIR", tmp_path / "episodes")
    monkeypatch.setattr(exports, "episode_path", lambda *a, **kw: src)
    monkeypatch.setattr(exports, "load_manifest", lambda *a, **kw: {"item_count": 0})

    def ffmpeg(cmd, **kwargs):
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        Path(cmd[-1]).write_bytes(b"m4b")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(exports.subprocess, "run", ffmpeg)
    assert exports.export_m4b("话题")["size"] == 3


@pytest.mark.parametrize("method,path,body,status", [
    ("POST", "/api/topics/missing/items/bulk", {"text": "Why?"}, 404),
    ("POST", "/api/topics/bad%20id/items/bulk", {"text": "Why?"}, 400),
    ("GET", "/api/topics/topic/items/bad%20id/agent-task", None, 400),
    ("POST", "/api/topics/topic/items/bad%20id/retry-api", None, 400),
    ("GET", "/api/topics/topic/items/bad%20id/arcade/sentences/0/voice/am_puck"
            "?source_fingerprint=old", None, 400),
    ("GET", "/api/topics/topic/items/bad%20id/study/audio/0", None, 400),
    ("POST", "/api/topics/bad%20id/episode", None, 400),
    ("POST", "/api/topics/bad%20id/export/m4b", None, 400),
    ("GET", "/api/topics/bad%20id/drafts", None, 400),
    ("GET", "/api/pack/export?topics=bad%20id", None, 400),
    ("POST", "/api/topics/topic/items/bad%20id/export/vtt", None, 400),
    ("POST", "/api/topics/topic/items/bad%20id/export/lrc", None, 400),
    ("POST", "/api/topics/topic/items/bad%20id/export/srt", None, 400),
])
def test_api_rejects_invalid_ids_with_400(item, monkeypatch, method, path, body, status):
    monkeypatch.setattr(api, "_require_llm_configured", lambda: None)
    with TestClient(app, raise_server_exceptions=False) as client:
        reply = client.request(method, path, json=body)
    assert reply.status_code == status, reply.text


@pytest.mark.parametrize("method,path,body,operation", [
    ("GET", "/api/study/review-sessions/example", None, "get_session"),
    ("PATCH", "/api/study/review-cards/example", {"paused": True}, "set_card_paused"),
])
def test_review_read_and_pause_map_value_errors(monkeypatch, method, path, body, operation):
    monkeypatch.setattr(oral_review, operation, Mock(side_effect=ValueError("口答记录无效")))
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.request(method, path, json=body).status_code == 400


def test_pack_export_cleans_partial_file_on_value_error(monkeypatch, tmp_path):
    exports_dir = tmp_path / "exports"
    exports_dir.mkdir()
    monkeypatch.setattr(api, "DATA_DIR", tmp_path)

    def fail(out_path, **kwargs):
        out_path.write_bytes(b"partial")
        raise ValueError("无效话题")

    monkeypatch.setattr(api.pack, "build_pack", fail)
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/api/pack/export?topics=example").status_code == 400
    assert not list(exports_dir.iterdir())


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
