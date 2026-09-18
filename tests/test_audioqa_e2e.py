"""M03 AC：注入异常音频（时长失控 + 违规标签）→ QA 检出 → 隔离 → 去标签重试。"""
import sys
import time
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient

from server import audio as audio_mod
from server import library, tts


@pytest.fixture()
def qa_env(tmp_path, monkeypatch):
    topics = tmp_path / "topics"
    episodes = tmp_path / "episodes"
    tmp = tmp_path / ".tmp"
    for d in (topics, episodes, tmp):
        d.mkdir(parents=True)
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    monkeypatch.setattr(library, "EPISODES_DIR", episodes)
    from server import assemble
    monkeypatch.setattr(assemble, "EPISODES_DIR", episodes)
    monkeypatch.setattr(audio_mod, "TMP_DIR", tmp)
    from server import config
    from server.main import app
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    with TestClient(app) as c:
        c.put(
            "/api/settings",
            json={"dry_run": True, "reference_id": "a", "reference_id_b": "b"},
        )
        yield c


def test_anomalous_audio_triggers_quarantine_and_retry(qa_env, monkeypatch):
    tid = qa_env.post("/api/topics", json={"name": "QA"}).json()["id"]
    src = "A: Hello there friend. [evil laughter]\nB: Oh hi!"
    iid = qa_env.post(
        f"/api/topics/{tid}/items", json={"podcast_text": src}
    ).json()["id"]

    real_synth = tts._synthesize_source
    calls = {"n": 0, "texts": []}

    def fake_synth(text, out_path, settings, force_monologue=False):
        calls["n"] += 1
        calls["texts"].append(text)
        result = real_synth(text, out_path, settings, force_monologue)
        if calls["n"] == 1:
            # 注入异常：追加 12 秒静音，时长比失控（模拟"笑了 12 秒"）
            padded = out_path.with_suffix(".padded.mp3")
            import subprocess
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(out_path),
                 "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=12",
                 "-filter_complex", "[0][1]concat=n=2:v=0:a=1",
                 "-ar", "44100", str(padded)],
                capture_output=True, timeout=120,
            )
            padded.replace(out_path)
        return result

    monkeypatch.setattr(tts, "_synthesize_source", fake_synth)

    r = qa_env.post(f"/api/topics/{tid}/items/{iid}/generate", json={"track": "podcast"})
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    deadline = time.time() + 180
    while time.time() < deadline:
        job = qa_env.get(f"/api/jobs/{job_id}").json()
        if job["state"] != "running":
            break
        time.sleep(0.3)
    assert job["state"] == "done" and not job["errors"], job

    ipath = library.item_path(tid, iid)
    # 重试确实发生：第二次调用使用去标签文本
    assert calls["n"] == 2, f"应触发重试，实际调用 {calls['n']} 次"
    assert "[evil laughter]" in calls["texts"][0]
    assert "[evil laughter]" not in calls["texts"][1]
    # 异常音频被隔离
    assert (ipath / "audio_podcast.rejected.mp3").exists()
    # 最终音频是重试产物（不含 12s 静音，时长正常）
    dur = audio_mod.probe_duration(ipath / "audio_podcast.mp3")
    assert dur < 10, f"重试后时长应正常，实际 {dur:.1f}s"
    # QA 报告落盘且最终通过
    import json
    report = json.loads((ipath / "qa_podcast.json").read_text(encoding="utf-8"))
    assert report["verdict"] in ("pass", "keep_warn")
    # alignment 指纹对应清理后的文本
    from server import alignment as align_mod
    cleaned = calls["texts"][1]
    doc = align_mod.load_alignment(
        ipath / "alignment_podcast.json",
        expect_text=cleaned,
        expect_audio=ipath / "audio_podcast.mp3",
    )
    assert doc is not None
    # meta 记录 QA 结论
    full = qa_env.get(f"/api/topics/{tid}/items/{iid}").json()
    assert full.get("qa_podcast") in ("pass", "keep_warn")
