"""L02/L03 状态接口、单次材料调用与私有录音 API。"""
import json
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server import library, pack, rewrite, study, study_progress


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    from server import config

    topics = tmp_path / "topics"
    topics.mkdir()
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    monkeypatch.setattr(study_progress, "PRIVATE_DIR", tmp_path / "study_private")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(pack, "DATA_DIR", tmp_path)
    config.atomic_write_text(config.SETTINGS_FILE, json.dumps({"dry_run": False}))
    t = library.create_topic("T")
    i = library.create_item(t["id"], {
        "question": "What do you do?", "original_answer": "我散步。",
        "natural_english": "I go for a walk.",
        "podcast_text": "A: What do you do?\nB: I go for a walk.",
    })
    path = library.item_path(t["id"], i["id"])
    (path / "audio_podcast.mp3").write_bytes(b"dummy-audio")
    from server.main import app
    with TestClient(app) as client:
        yield client, t["id"], i["id"], tmp_path


def _material():
    return {"complete_chinese": "我去散步。", "sentences": [{
        "zh": "我去散步。", "en": "I go for a walk.",
        "explanation": "go for a walk 是常见搭配。", "usage": "描述散步。",
    }]}


def test_prepare_is_independent_and_calls_text_once(setup, monkeypatch):
    client, tid, iid, _ = setup
    calls = []

    def fake_chat(settings, messages, cancel):
        calls.append(messages)
        return json.dumps(_material(), ensure_ascii=False)

    monkeypatch.setattr(rewrite, "_chat", fake_chat)
    url = f"/api/topics/{tid}/items/{iid}/study"
    assert client.get(url).json()["status"] == "needs_input"
    assert client.post(url + "/prepare").json()["status"] == "preparing"
    for _ in range(100):
        result = client.get(url).json()
        if result["status"] != "preparing":
            break
        time.sleep(.02)
    assert result["status"] == "ready", result
    assert len(calls) == 1
    assert client.get(url + "/audio/0").json()["scope"] == "full_answer"
    assert client.get(f"/api/topics/{tid}/items/{iid}").json()["has_audio"] is True


def test_recording_api_versions_not_in_pack(setup):
    client, tid, iid, tmp = setup
    study.save_material(tid, iid, _material())
    base = f"/api/topics/{tid}/items/{iid}/study"
    client.patch(base + "/progress", json={"stage": "dictation", "draft": ["I"]})
    for payload in (b"first", b"second"):
        response = client.post(base + "/recordings?stage=before&duration_sec=2.5",
                               content=payload, headers={"Content-Type": "audio/webm"})
        assert response.status_code == 200, response.text
    records = client.get(base + "/progress").json()["recordings"]
    assert len(records) == 2
    assert client.get(base + "/recordings/" + records[0]["id"]).content == b"first"
    exported = pack.build_pack(out_path=tmp / "test.zip", topic_ids=[tid])
    with zipfile.ZipFile(exported["path"]) as archive:
        names = archive.namelist()
        assert not any("study_private" in name or "recording" in name for name in names)
    assert client.delete(base + "/recordings/" + records[0]["id"]).status_code == 200
    assert len(client.get(base + "/progress").json()["recordings"]) == 1


def test_material_failure_keeps_audio_and_recording_history(setup, monkeypatch):
    client, tid, iid, _ = setup
    base = f"/api/topics/{tid}/items/{iid}/study"
    first = client.post(base + "/recordings?stage=before&duration_sec=2.5",
                        content=b"first", headers={"Content-Type": "audio/webm"}).json()

    def fail_chat(settings, messages, cancel):
        raise rewrite.RewriteError("synthetic text failure")

    monkeypatch.setattr(rewrite, "_chat", fail_chat)
    assert client.post(base + "/prepare").status_code == 200
    for _ in range(100):
        result = client.get(base).json()
        if result["status"] != "preparing":
            break
        time.sleep(.02)
    assert result["status"] == "failed"
    assert client.get(f"/api/topics/{tid}/items/{iid}/audio/podcast").status_code == 200
    assert client.get(base + "/recordings/" + first["id"]).content == b"first"


@pytest.mark.parametrize("command", ["complete", "study"])
def test_pipeline_invalid_json_returns_nonzero(command, tmp_path):
    result = tmp_path / "invalid.json"
    result.write_text("{}", encoding="utf-8")
    run = subprocess.run(
        [sys.executable, str(BASE_DIR / "pipeline.py"), command,
         "--topic-id", "missing", "--item-id", "missing", "--result-json", str(result)],
        capture_output=True, text=True, timeout=10,
    )
    assert run.returncode == 2


def test_failed_background_material_task_does_not_recreate_deleted_item(setup, monkeypatch):
    client, tid, iid, _ = setup
    started = threading.Event()
    release = threading.Event()

    def fail_after_delete(topic_id, item_id):
        started.set()
        release.wait(timeout=5)
        raise study.MaterialError("synthetic failure")

    monkeypatch.setattr(study, "generate_material", fail_after_delete)
    assert client.post(f"/api/topics/{tid}/items/{iid}/study/prepare").status_code == 200
    assert started.wait(timeout=5)
    assert client.delete(f"/api/topics/{tid}").status_code == 200
    release.set()
    for _ in range(100):
        with study._ACTIVE_LOCK:
            if (tid, iid) not in study._ACTIVE:
                break
        time.sleep(.02)
    assert not library.item_path(tid, iid).exists()
