"""M10 整集体验测试：manifest 章节偏移 + 过期检测 + 一键重建。"""
import sys
import time
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient


@pytest.fixture()
def ep_env(tmp_path, monkeypatch):
    topics = tmp_path / "topics"
    episodes = tmp_path / "episodes"
    for d in (topics, episodes, tmp_path / ".tmp"):
        d.mkdir(parents=True)
    from server import library
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    monkeypatch.setattr(library, "EPISODES_DIR", episodes)
    from server import assemble, audio, config, jobs
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


def _wait(c, job_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = c.get(f"/api/jobs/{job_id}").json()
        if j["state"] != "running":
            return j
        time.sleep(0.2)
    pytest.fail("任务超时")


def test_episode_offsets_staleness_and_rebuild(ep_env):
    c = ep_env
    tid = c.post("/api/topics", json={"name": "Ep"}).json()["id"]
    c.post(f"/api/topics/{tid}/items", json={"podcast_text": "A: First one here.\nB: And a reply."})
    second = {"podcast_text": "A: Second question.\nB: Second answer."}
    c.post(f"/api/topics/{tid}/items", json=second)

    # 生成两条
    r = c.post(f"/api/topics/{tid}/generate", json={"track": "podcast"})
    _wait(c, r.json()["job_id"])

    # 合成 → manifest 带章节偏移
    m = c.post(f"/api/topics/{tid}/episode?track=podcast").json()
    _wait(c, m["job_id"])
    manifest = c.get(f"/api/topics/{tid}/episode?track=podcast").json()
    assert manifest["item_count"] == 2
    offs = [it["offset_sec"] for it in manifest["items"]]
    assert offs[0] == 0.0 and offs[1] > offs[0], f"章节偏移应递增: {offs}"
    assert manifest["stale"] is False

    # 条目重生成 → 剧集应标记过期
    iid = manifest["items"][0]["id"]
    r2 = c.post(f"/api/topics/{tid}/items/{iid}/generate", json={"track": "podcast", "force": True})
    _wait(c, r2.json()["job_id"])
    manifest2 = c.get(f"/api/topics/{tid}/episode?track=podcast").json()
    assert manifest2["stale"] is True, "条目重生成后剧集应标记过期"

    # 一键重建 → 过期消除，偏移刷新
    m3 = c.post(f"/api/topics/{tid}/episode?track=podcast").json()
    _wait(c, m3["job_id"])
    manifest3 = c.get(f"/api/topics/{tid}/episode?track=podcast").json()
    assert manifest3["stale"] is False
    offs3 = [it["offset_sec"] for it in manifest3["items"]]
    assert offs3 == sorted(offs3) and offs3[0] == 0.0
