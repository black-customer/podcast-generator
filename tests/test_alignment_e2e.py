"""M02 端到端：dry-run 生成 → alignment_podcast.json（measured）→ 编辑失效。"""
import sys
import time
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

import subprocess

from fastapi.testclient import TestClient

from server import alignment as align_mod
from server import jobs, library


def _ffmpeg_ok() -> bool:
    try:
        proc = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=15)
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


FFMPEG_AVAILABLE = _ffmpeg_ok()
pytestmark = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="需要 ffmpeg")

@pytest.fixture()
def gen_env(tmp_path, monkeypatch):
    topics = tmp_path / "topics"
    episodes = tmp_path / "episodes"
    tmp = tmp_path / ".tmp"
    for d in (topics, episodes, tmp):
        d.mkdir(parents=True)
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    monkeypatch.setattr(library, "EPISODES_DIR", episodes)
    from server import assemble, audio
    monkeypatch.setattr(assemble, "EPISODES_DIR", episodes)
    monkeypatch.setattr(audio, "TMP_DIR", tmp)
    from server import config
    from server.main import app
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(jobs, 'JOBS_FILE', tmp_path / 'jobs.json')
    with TestClient(app) as c:
        # dry-run + 双音色：对话文本走逐行合成路径（单次合成需网络，dry-run 本就走逐行）
        c.put(
            "/api/settings",
            json={"dry_run": True, "reference_id": "voice-a", "reference_id_b": "voice-b"},
        )
        yield c


def _wait_job(client, job_id: str, timeout: float = 120) -> dict:
    deadline = time.time() + timeout
    job = None
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.3)
    pytest.fail(f"任务超时: {job}")


def test_generation_writes_measured_alignment(gen_env):
    tid = gen_env.post("/api/topics", json={"name": "Align"}).json()["id"]
    iid = gen_env.post(
        f"/api/topics/{tid}/items",
        json={"podcast_text": "A: Hello there friend.\nB: Oh hi! How are you?"},
    ).json()["id"]

    r = gen_env.post(f"/api/topics/{tid}/items/{iid}/generate", json={"track": "podcast"})
    assert r.status_code == 200
    job = _wait_job(gen_env, r.json()["job_id"])
    assert job["state"] == "done", job["errors"]
    assert not job["errors"], job["errors"]

    ipath = library.item_path(tid, iid)
    doc = align_mod.load_alignment(
        ipath / "alignment_podcast.json",
        expect_text="A: Hello there friend.\nB: Oh hi! How are you?",
        expect_audio=ipath / "audio_podcast.mp3",
    )
    assert doc is not None, "alignment 文档缺失或指纹不匹配"
    assert doc["mode"] == "measured", f"逐行 dry-run 应为 measured，实际 {doc['mode']}"
    segs = doc["segments"]
    assert len(segs) == 2
    assert segs[0]["start"] == 0.0
    assert segs[0]["end"] <= segs[1]["start"]  # 换行 gap > 0
    assert segs[1]["speaker"] == "b"
    # 时间轴端点消费 alignment（载荷含 lines/words/mode）
    tl = gen_env.get(f"/api/topics/{tid}/items/{iid}/timeline/podcast").json()
    assert len(tl["lines"]) == 2
    assert tl["lines"][0]["start"] == segs[0]["start"] and tl["lines"][0]["speaker"] == "A"
    assert tl["mode"] == "measured"


def test_text_edit_invalidates_alignment(gen_env):
    tid = gen_env.post("/api/topics", json={"name": "Inval"}).json()["id"]
    iid = gen_env.post(
        f"/api/topics/{tid}/items",
        json={"podcast_text": "A: First line.\nB: Second line."},
    ).json()["id"]
    r = gen_env.post(f"/api/topics/{tid}/items/{iid}/generate", json={"track": "podcast"})
    _wait_job(gen_env, r.json()["job_id"])
    ipath = library.item_path(tid, iid)
    assert (ipath / "alignment_podcast.json").exists()

    # 编辑英文源文本 → 缓存文件被删除（审计 A2 回归）
    gen_env.patch(
        f"/api/topics/{tid}/items/{iid}",
        json={"podcast_text": "A: Changed line.\nB: Second line."},
    )
    assert not (ipath / "alignment_podcast.json").exists()
    assert not (ipath / "timeline_podcast.json").exists()
    # stale 标记
    full = gen_env.get(f"/api/topics/{tid}/items/{iid}").json()
    assert full["stale"] is True


def test_monologue_measured_alignment(gen_env):
    tid = gen_env.post("/api/topics", json={"name": "Mono"}).json()["id"]
    iid = gen_env.post(
        f"/api/topics/{tid}/items",
        json={
            "monologue_text": (
                "I woke up early today. It felt great. Then I made coffee and started working."
            )
        },
    ).json()["id"]
    r = gen_env.post(f"/api/topics/{tid}/items/{iid}/generate", json={"track": "monologue"})
    job = _wait_job(gen_env, r.json()["job_id"])
    assert job["state"] == "done" and not job["errors"]

    ipath = library.item_path(tid, iid)
    doc = align_mod.load_alignment(
        ipath / "alignment_monologue.json",
        expect_audio=ipath / "audio_monologue.mp3",
    )
    assert doc is not None and doc["mode"] == "measured"
    # 句子级粒度（3 句），块内分配
    assert len(doc["segments"]) == 3
    starts = [s["start"] for s in doc["segments"]]
    assert starts == sorted(starts)
