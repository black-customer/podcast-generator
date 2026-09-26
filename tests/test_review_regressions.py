"""全项目审查发现的访问控制、生成一致性与导出回归测试。"""

import re
from email.utils import parsedate_to_datetime

import pytest
from fastapi.testclient import TestClient

from server import alignment, assemble, exports_media, jobs, library, pack, rewrite, tts
from server.main import app


def test_cross_origin_api_request_is_rejected():
    with TestClient(app) as client:
        response = client.get("/api/health", headers={"Origin": "https://untrusted.example"})
        image_probe = client.get("/api/health", headers={"Sec-Fetch-Site": "cross-site"})
    assert response.status_code == 403
    assert image_probe.status_code == 403


def test_lan_api_requires_pairing_token(monkeypatch):
    monkeypatch.setenv("IELTS_POD_LAN_TOKEN", "one-time-pairing-token")
    with TestClient(app, client=("192.168.1.44", 50000)) as client:
        assert client.get("/api/topics").status_code == 403
        assert client.get("/api/pack/export").status_code == 403


def test_lan_pairing_token_only_allows_pack_download(tmp_path, monkeypatch):
    archive = tmp_path / "pack.zip"
    archive.write_bytes(b"PK" + bytes(40))
    monkeypatch.setenv("IELTS_POD_LAN_TOKEN", "one-time-pairing-token")
    monkeypatch.setattr(
        pack, "build_pack",
        lambda **_kwargs: {"path": archive, "manifest": {}, "size_bytes": archive.stat().st_size},
    )
    headers = {"Origin": "https://localhost", "X-Lan-Token": "one-time-pairing-token"}
    with TestClient(app, client=("192.168.1.44", 50000)) as client:
        assert client.get("/api/topics", headers=headers).status_code == 403
        response = client.get("/api/pack/export", headers=headers)
        preflight = client.options(
            "/api/pack/export",
            headers={
                "Origin": "https://localhost",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "x-lan-token",
            },
        )
    assert response.status_code == 200 and response.content.startswith(b"PK")
    assert response.headers["access-control-allow-origin"] == "https://localhost"
    assert preflight.status_code == 200


def test_rewrite_rejects_single_speaker_script():
    texts = {
        "natural_english": "Hello there friend.",
        "podcast_text": "A: Hello there friend.",
        "podcast_script": "A: Hello there friend.",
    }
    assert rewrite.validate_texts(texts)


def test_stepfun_segments_respect_character_limit():
    from server import stepfun

    segments = tts.split_text("x" * 1300, stepfun.MAX_CHARS)
    assert len(segments) > 1
    assert all(len(segment) <= stepfun.MAX_CHARS for segment in segments)


def test_api_conflict_does_not_leave_created_item(tmp_path, monkeypatch):
    topics = tmp_path / "topics"
    topics.mkdir()
    monkeypatch.setattr(library, "TOPICS_DIR", topics)

    def conflict(*_args, **_kwargs):
        raise jobs.JobConflict("busy")

    monkeypatch.setattr(jobs, "start_api_generation", conflict)
    with TestClient(app) as client:
        response = client.post(
            "/api/generation-requests",
            json={
                "question": "A question?", "topic": "Review", "answer": "My answer.",
                "mode": "api",
            },
        )
    assert response.status_code == 409
    assert sum(t["stats"]["total"] for t in library.list_topics()) == 0
    assert library.list_topics() == []


def test_episode_audio_does_not_fall_back_to_other_track(tmp_path, monkeypatch):
    monkeypatch.setattr(assemble, "EPISODES_DIR", tmp_path)
    (tmp_path / "review.mp3").write_bytes(b"default audio")
    with TestClient(app) as client:
        response = client.get("/api/topics/review/episode/audio?track=podcast")
    assert response.status_code == 404


def test_subtitle_export_does_not_use_opposite_track(tmp_path, monkeypatch):
    topics = tmp_path / "topics"
    topics.mkdir()
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    topic_id = library.create_topic("Subtitle review")["id"]
    item_id = library.create_item(topic_id, {"monologue_text": "Hello."})["id"]
    item_dir = library.item_path(topic_id, item_id)
    audio_path = item_dir / "audio.mp3"
    audio_path.write_bytes(b"legacy audio")
    doc = alignment.build_alignment_doc(
        "measured", "Hello.", audio_path, [{"text": "Hello.", "start": 0, "end": 1}]
    )
    alignment.save_alignment(doc, item_dir / "alignment_monologue.json")
    assert exports_media._load_doc(topic_id, item_id, "podcast") is None


def test_rss_identity_survives_rebuild_and_date_is_valid(tmp_path, monkeypatch):
    episode = tmp_path / "episode.mp3"
    episode.write_bytes(b"audio")
    generated_at = ["2026-09-20T10:00:00", "2026-09-21T10:00:00"]
    monkeypatch.setattr(
        exports_media.library, "list_topics", lambda: [{"id": "topic", "name": "Topic"}]
    )
    monkeypatch.setattr(exports_media, "episode_path", lambda *_args, **_kwargs: episode)
    monkeypatch.setattr(
        exports_media,
        "load_manifest",
        lambda *_args, **_kwargs: {
            "topic_name": "Topic", "generated_at": generated_at[0], "total_sec": 60
        },
    )
    first = exports_media.build_rss("http://127.0.0.1:8765")
    generated_at[0] = generated_at[1]
    second = exports_media.build_rss("http://127.0.0.1:8765")
    guid = r"<guid isPermaLink=\"false\">([^<]+)</guid>"
    assert re.search(guid, first).group(1) == re.search(guid, second).group(1)
    pubdate = re.search(r"<pubDate>([^<]+)</pubDate>", second).group(1)
    assert parsedate_to_datetime(pubdate) is not None


def test_pack_requests_use_distinct_output_files(tmp_path, monkeypatch):
    paths = []
    monkeypatch.setattr("server.api.DATA_DIR", tmp_path)

    def fake_build_pack(out_path=None, topic_ids=None):
        del topic_ids
        paths.append(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"PK" + bytes(40))
        return {"path": out_path, "manifest": {}, "size_bytes": out_path.stat().st_size}

    monkeypatch.setattr(pack, "build_pack", fake_build_pack)
    with TestClient(app) as client:
        assert client.get("/api/pack/export").status_code == 200
        assert client.get("/api/pack/export").status_code == 200
    assert paths[0] is not None and paths[1] is not None and paths[0] != paths[1]
    assert not any(path.exists() for path in paths)


def test_assemble_rejects_active_generation(tmp_path, monkeypatch):
    class DormantThread:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        def start(self):
            pass

    active = {"id": "running", "kind": "generate", "topic_id": "topic", "state": "running"}
    monkeypatch.setattr(jobs, "JOBS", {"running": active})
    monkeypatch.setattr(jobs, "_ACTIVE_TOPICS", {"topic": "running"})
    monkeypatch.setattr(jobs, "JOBS_FILE", tmp_path / "jobs.json")
    monkeypatch.setattr(jobs.threading, "Thread", DormantThread)
    monkeypatch.setattr(library, "get_topic", lambda _topic_id: {"items": []})
    with pytest.raises(jobs.JobConflict):
        jobs.start_assemble("topic", track="podcast")


def test_generate_rechecks_topic_after_target_selection(tmp_path, monkeypatch):
    class DormantThread:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        def start(self):
            pass


    existing = {
        "id": "existing", "kind": "generate", "topic_id": "topic", "state": "running", "total": 1,
    }
    active = {}
    stored = {}
    monkeypatch.setattr(jobs, "JOBS", stored)
    monkeypatch.setattr(jobs, "_ACTIVE_TOPICS", active)
    monkeypatch.setattr(jobs, "JOBS_FILE", tmp_path / "jobs.json")
    monkeypatch.setattr(jobs.threading, "Thread", DormantThread)

    def topic_with_race(_topic_id):
        stored["existing"] = existing
        active["topic"] = "existing"
        return {"items": [{"id": "item", "status": "ready"}]}

    monkeypatch.setattr(library, "get_topic", topic_with_race)
    monkeypatch.setattr(
        library, "get_item_full", lambda *_args: {"podcast_text": "A: Hi.\nB: Hello."}
    )
    monkeypatch.setattr(
        library, "get_track_source_text",
        lambda *_args, **_kwargs: ("A: Hi.\nB: Hello.", "podcast_text"),
    )
    result = jobs.start_generate("topic", track="podcast")
    assert result["job_id"] == "existing" and result["already_running"] is True


def test_edit_during_generation_keeps_audio_stale(tmp_path, monkeypatch):
    topics = tmp_path / "topics"
    topics.mkdir()
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    topic_id = library.create_topic("Generation review")["id"]
    item_id = library.create_item(topic_id, {"podcast_text": "A: Old?\nB: Old answer."})["id"]
    monkeypatch.setattr(tts, "load_settings", lambda: {"tts_provider": "stepfun", "dry_run": True})

    def synthesize(_src, out_path, _settings, **_kwargs):
        out_path.write_bytes(b"audio")
        library.update_item_texts(topic_id, item_id, {"podcast_text": "A: New?\nB: New answer."})
        return ((1.0, 1, True, "test", [], []), {"verdict": "pass"}, _src, [])

    monkeypatch.setattr(tts, "_synthesize_with_qa", synthesize)
    monkeypatch.setattr(tts, "_save_track_outputs", lambda *_args, **_kwargs: None)
    tts.generate_item_audio(topic_id, item_id, track="podcast")
    assert library.get_item_full(topic_id, item_id)["stale"] is True
