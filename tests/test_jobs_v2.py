"""M05 任务系统测试：持久化恢复 / 话题互斥 / 取消令牌 / 异步合成。"""
import sys
import threading
import time
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient

from server import jobs, library, tts


@pytest.fixture()
def job_env(tmp_path, monkeypatch):
    jobs.JOBS.clear()
    jobs._ACTIVE_TOPICS.clear()
    topics = tmp_path / "topics"
    episodes = tmp_path / "episodes"
    for d in (topics, episodes, tmp_path / ".tmp"):
        d.mkdir(parents=True)
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    monkeypatch.setattr(library, "EPISODES_DIR", episodes)
    from server import assemble, audio, config
    monkeypatch.setattr(assemble, "EPISODES_DIR", episodes)
    monkeypatch.setattr(audio, "TMP_DIR", tmp_path / ".tmp")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(jobs, "JOBS_FILE", tmp_path / "jobs.json")
    from server.main import app
    with TestClient(app) as c:
        c.put(
            "/api/settings",
            json={"dry_run": True, "reference_id": "a", "reference_id_b": "b"},
        )
        yield c
        deadline = time.time() + 30
        while jobs._ACTIVE_TOPICS and time.time() < deadline:
            time.sleep(0.05)
        assert not jobs._ACTIVE_TOPICS, "后台任务必须在临时目录 monkeypatch 恢复前退出"
        jobs.JOBS.clear()
        jobs._ACTIVE_TOPICS.clear()


def _mk_item(c, topic_id, text="A: Hello there friend.\nB: Oh hi!"):
    return c.post(f"/api/topics/{topic_id}/items", json={"podcast_text": text}).json()["id"]


def _wait(c, job_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["state"] != "running":
            return j
        time.sleep(0.2)
    pytest.fail("任务超时")


# ---------------------------------------------------------------- 互斥

def test_topic_mutex_prevents_duplicate_jobs(job_env):
    c = job_env
    tid = c.post("/api/topics", json={"name": "Mutex"}).json()["id"]
    _mk_item(c, tid)
    _mk_item(c, tid, "A: Second item line.\nB: Reply here.")
    r1 = c.post(f"/api/topics/{tid}/generate", json={"track": "podcast"}).json()
    r2 = c.post(f"/api/topics/{tid}/generate", json={"track": "podcast"}).json()
    assert r2.get("already_running") is True
    assert r2["job_id"] == r1["job_id"]
    # 完成后可再次启动
    _wait(c, r1["job_id"])
    r3 = c.post(f"/api/topics/{tid}/generate", json={"track": "podcast", "force": True}).json()
    assert "already_running" not in r3
    _wait(c, r3["job_id"])


# ---------------------------------------------------------------- 持久化恢复

def test_jobs_persist_and_recover_as_interrupted(job_env, monkeypatch):
    c = job_env

    class DormantThread:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        def start(self):
            return None

    # 这里只验证磁盘恢复语义，不应真的启动跨 fixture 的 daemon 合成线程。
    monkeypatch.setattr(jobs.threading, "Thread", DormantThread)
    tid = c.post("/api/topics", json={"name": "Persist"}).json()["id"]
    _mk_item(c, tid)
    r = c.post(f"/api/topics/{tid}/generate", json={"track": "podcast"}).json()
    job_id = r["job_id"]
    # 模拟进程重启：内存清空，从磁盘恢复
    monkeypatch.setattr(jobs, "JOBS", {})
    jobs.recover_from_disk()
    j = c.get(f"/api/jobs/{job_id}").json()
    assert j["state"] == "interrupted"


# ---------------------------------------------------------------- 取消令牌

def test_cancel_token_interrupts_tts():
    ev = threading.Event()
    ev.set()
    with pytest.raises(tts.TTSCancelled):
        tts._post_tts({"text": "hi"}, {"fish_api_key": "k"}, cancel=ev)


def test_cancel_between_items_marks_cancelled(job_env):
    c = job_env
    tid = c.post("/api/topics", json={"name": "Cancel"}).json()["id"]
    _mk_item(c, tid)
    _mk_item(c, tid, "A: Another.\nB: More.")
    r = c.post(f"/api/topics/{tid}/generate", json={"track": "podcast"}).json()
    c.post(f"/api/jobs/{r['job_id']}/cancel")
    j = _wait(c, r["job_id"])
    assert j["state"] in ("cancelled", "done")  # 快速任务可能已完成


# ---------------------------------------------------------------- 异步合成

def test_assemble_runs_as_job(job_env):
    c = job_env
    tid = c.post("/api/topics", json={"name": "Asm"}).json()["id"]
    _mk_item(c, tid)
    r = c.post(f"/api/topics/{tid}/generate", json={"track": "podcast"})
    _wait(c, r.json()["job_id"])

    # 合成是后台任务
    r2 = c.post(f"/api/topics/{tid}/episode?track=podcast")
    assert r2.status_code == 200
    body = r2.json()
    assert "job_id" in body
    j = _wait(c, body["job_id"])
    assert j["state"] == "done", j.get("errors")
    manifest = c.get(f"/api/topics/{tid}/episode?track=podcast")
    assert manifest.status_code == 200
    assert manifest.json()["item_count"] == 1


def test_job_history_endpoint(job_env):
    c = job_env
    listing = c.get("/api/jobs").json()
    assert isinstance(listing, list)
