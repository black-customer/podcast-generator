"""M11 导出测试：M4B 章节存在性 + SRT 生成。"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient


@pytest.fixture()
def exp_env(tmp_path, monkeypatch):
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
    monkeypatch.setattr("server.exports.EPISODES_DIR", episodes)
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


def test_m4b_export_has_chapters(exp_env, tmp_path):
    c = exp_env
    tid = c.post("/api/topics", json={"name": "Export"}).json()["id"]
    first = {"podcast_text": "A: First chapter line.\nB: And the reply."}
    c.post(f"/api/topics/{tid}/items", json=first)
    second = {"podcast_text": "A: Second chapter.\nB: Closing words."}
    c.post(f"/api/topics/{tid}/items", json=second)
    _wait(c, c.post(f"/api/topics/{tid}/generate", json={"track": "podcast"}).json()["job_id"])
    asm = c.post(f"/api/topics/{tid}/episode?track=podcast").json()
    _wait(c, asm["job_id"])

    r = c.post(f"/api/topics/{tid}/export/m4b?track=podcast")
    assert r.status_code == 200, r.text
    out_file = r.json()["file"]
    assert Path(out_file).exists() and Path(out_file).stat().st_size > 5000

    # AC：ffprobe 验证章节存在且标题正确
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_chapters", "-of", "json", out_file],
        capture_output=True, text=True, timeout=60,
    )
    chapters = __import__("json").loads(probe.stdout).get("chapters", [])
    assert len(chapters) == 2, f"应有 2 个章节，实际 {len(chapters)}"
    assert "First chapter line." in (chapters[0].get("tags", {}).get("title") or "")


def test_srt_export(exp_env):
    c = exp_env
    tid = c.post("/api/topics", json={"name": "Srt"}).json()["id"]
    iid = c.post(
        f"/api/topics/{tid}/items",
        json={"podcast_text": "A: Hello there friend.\nB: Oh hi! How are you?"},
    ).json()["id"]
    r = c.post(f"/api/topics/{tid}/items/{iid}/generate", json={"track": "podcast"})
    _wait(c, r.json()["job_id"])

    r = c.post(f"/api/topics/{tid}/items/{iid}/export/srt?track=podcast")
    assert r.status_code == 200, r.text
    body = r.json()
    content = Path(body["file"]).read_text(encoding="utf-8")
    assert "-->" in content
    assert "Hello there friend." in content
