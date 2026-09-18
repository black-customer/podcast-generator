"""M12 测试：VTT/LRC 字幕格式 + RSS feed。"""
import sys
import time
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient


def _wait(c, job_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["state"] != "running":
            return j
        time.sleep(0.2)
    pytest.fail("任务超时")



@pytest.fixture()
def media_env(tmp_path, monkeypatch):
    from server import library

    topics = tmp_path / "topics"
    episodes = tmp_path / "episodes"
    for d in (topics, episodes, tmp_path / ".tmp"):
        d.mkdir(parents=True)
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    monkeypatch.setattr(library, "EPISODES_DIR", episodes)
    from server import assemble, audio, config, jobs
    monkeypatch.setattr(assemble, "EPISODES_DIR", episodes)
    monkeypatch.setattr(audio, "TMP_DIR", tmp_path / ".tmp")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(jobs, "JOBS_FILE", tmp_path / "jobs.json")
    monkeypatch.setattr("server.exports_media.EPISODES_DIR", episodes)
    from server.main import app
    with TestClient(app) as c:
        c.put(
            "/api/settings",
            json={"dry_run": True, "reference_id": "a", "reference_id_b": "b"},
        )
        yield c


def _gen_one(c, tid, text="A: Hello there friend.\nB: Oh hi! How are you?"):
    iid = c.post(f"/api/topics/{tid}/items", json={"podcast_text": text}).json()["id"]
    r = c.post(f"/api/topics/{tid}/items/{iid}/generate", json={"track": "podcast"})
    deadline = time.time() + 120
    while time.time() < deadline:
        j = c.get(f"/api/jobs/{r.json()['job_id']}").json()
        if j["state"] != "running":
            break
        time.sleep(0.2)
    assert j["state"] == "done", j["errors"]
    return iid


def test_vtt_export_word_cues(media_env):
    c = media_env
    tid = c.post("/api/topics", json={"name": "Vtt"}).json()["id"]
    iid = _gen_one(c, tid)
    r = c.post(f"/api/topics/{tid}/items/{iid}/export/vtt?track=podcast")
    assert r.status_code == 200, r.text
    vtt_file = Path(r.json()["file"])
    content = vtt_file.read_text(encoding="utf-8")
    assert content.startswith("WEBVTT")
    assert "-->" in content
    assert r.json()["cues"] >= 2


def test_lrc_export(media_env):
    c = media_env
    tid = c.post("/api/topics", json={"name": "Lrc"}).json()["id"]
    iid = _gen_one(c, tid)
    r = c.post(f"/api/topics/{tid}/items/{iid}/export/lrc?track=podcast")
    assert r.status_code == 200
    content = Path(r.json()["file"]).read_text(encoding="utf-8")
    import re
    assert re.search(r"\[\d{2}:\d{2}\.\d{2}\]Hello", content)


def test_rss_feed_contains_episodes(media_env):
    c = media_env
    tid = c.post("/api/topics", json={"name": "Rss Topic"}).json()["id"]
    _gen_one(c, tid)
    m = c.post(f"/api/topics/{tid}/episode?track=podcast").json()
    _wait(c, m["job_id"])

    r = c.get("/api/rss.xml")
    assert r.status_code == 200
    body = r.text
    assert "<rss" in body and "<item>" in body
    assert "Bruce English Corpus" in body
    assert "/episode/audio?track=podcast" in body

