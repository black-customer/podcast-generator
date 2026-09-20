"""核心逻辑隔离测试：全部数据目录指向 pytest 临时目录，不依赖/不污染 data/ 真实数据。

运行：.venv/Scripts/python -m pytest tests/test_core.py -q
"""
import subprocess
import sys
import time
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient

from server import assemble, audio, library, tts


def _ffmpeg_ok() -> bool:
    try:
        proc = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=15)
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


FFMPEG_AVAILABLE = _ffmpeg_ok()


@pytest.fixture()
def lib_env(tmp_path, monkeypatch):
    """把数据目录全部指向临时目录。"""
    topics = tmp_path / "topics"
    episodes = tmp_path / "episodes"
    tmp = tmp_path / ".tmp"
    for d in (topics, episodes, tmp):
        d.mkdir(parents=True)
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    monkeypatch.setattr(library, "EPISODES_DIR", episodes)
    monkeypatch.setattr(assemble, "EPISODES_DIR", episodes)
    monkeypatch.setattr(audio, "TMP_DIR", tmp)
    yield {"topics": topics, "episodes": episodes, "tmp": tmp}


@pytest.fixture()
def client(lib_env, tmp_path, monkeypatch):
    """TestClient + 隔离的 settings.json（避免读到真实 API key 触发 live 模式）。"""
    from server import config
    from server.main import app

    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------- 单元

def test_slugify():
    assert library.slugify("Do you work? 你好") == "do-you-work-你好"
    assert library.slugify("///") == "untitled"


def test_parse_dialogue():
    assert tts.parse_dialogue("A: Hey\nB: Hi!") == [("a", "Hey"), ("b", "Hi!")]
    assert tts.parse_dialogue("Person A：One\nB: Two") == [("a", "One"), ("b", "Two")]
    assert tts.parse_dialogue("A: only one side") is None
    assert tts.parse_dialogue("A: Hey\n普通文本行\nB: Hi") is None


def test_split_text_sentence_boundaries():
    segs = tts.split_text("First sentence. Second one! Third? " + "x" * 100, 20)
    assert all(len(s) <= 40 for s in segs)
    assert "".join(segs).replace(" ", "").startswith("Firstsentence.")


def test_split_text_short_circuit():
    assert tts.split_text("short", 700) == ["short"]
    assert tts.split_text("", 700) == []


def test_split_text_never_cuts_inside_tag():
    """回归：超长句硬切不得把 [slight pause] 之类标签切断。"""
    text = "Intro. " + ("word " * 300) + "[slight pause] " + ("word " * 300) + "end."
    segs = tts.split_text(text, 100)
    for s in segs:
        assert s.count("[") == s.count("]"), f"标签被切断: {s!r}"
        assert "[slight" not in s or "[slight pause]" in s
    # 标签必须完整出现在某一段中
    assert any("[slight pause]" in s for s in segs)


# ---------------------------------------------------------------- 数据层

def test_topic_item_crud(lib_env):
    t = library.create_topic("My Studies")
    it = library.create_item(t["id"], {"question": "Q1?", "chinese": "中文回答"})
    full = library.get_item_full(t["id"], it["id"])
    assert full["question"] == "Q1?"
    assert full["chinese"] == "中文回答"
    assert full["natural_english"] == ""
    # question/chinese 不是可合成源，只有英文字段才算 ready
    assert full["status"] == "empty"

    # 部分更新：只改 question，其余字段必须原样保留（回归 PATCH 清空 bug）
    library.update_item_texts(t["id"], it["id"], {"question": "Q2?"})
    full = library.get_item_full(t["id"], it["id"])
    assert full["question"] == "Q2?"
    assert full["chinese"] == "中文回答"


def test_stale_detection_covers_all_tracks(lib_env):
    t = library.create_topic("T")
    it = library.create_item(t["id"], {"monologue_script": "mono v1", "question": "Q"})
    tid, iid = t["id"], it["id"]
    d = library.item_path(tid, iid)
    (d / "audio.mp3").write_bytes(b"\x00audio")
    library.update_item_meta(tid, iid)  # 刷新 status → generated

    # 改了独白轨文本 → stale
    library.update_item_texts(tid, iid, {"monologue_script": "mono v2"})
    assert library.get_item_full(tid, iid)["stale"] is True

    # 只改中文（非合成源）→ 不 stale
    library.update_item_meta(tid, iid, stale=False)
    library.update_item_texts(tid, iid, {"chinese": "只是中文"})
    assert library.get_item_full(tid, iid)["stale"] is False


def test_resolve_audio_file_priority(lib_env):
    """M08 语义修正：podcast/monologue 轨不再错误回退到语义不符的旧版 audio.mp3（审计 A9）。"""
    t = library.create_topic("T")
    it = library.create_item(t["id"], {"question": "Q"})
    d = library.item_path(t["id"], it["id"])
    assert library.resolve_audio_file(d, "default") is None

    # 旧版 audio.mp3（内容语义未知）：独白轨可回退、播客轨不可（防止把独白当播客）
    (d / "audio.mp3").write_bytes(b"x")
    assert library.resolve_audio_file(d, "monologue") == d / "audio.mp3"
    assert library.resolve_audio_file(d, "podcast") is None

    (d / "audio_monologue.mp3").write_bytes(b"x")
    assert library.resolve_audio_file(d, "monologue") == d / "audio_monologue.mp3"

    # meta 标记对话内容后，播客轨才允许回退到旧版 audio.mp3
    library.update_item_meta(t["id"], it["id"], dialogue=True)
    assert library.resolve_audio_file(d, "podcast") == d / "audio.mp3"

    (d / "audio_podcast.mp3").write_bytes(b"x")
    assert library.resolve_audio_file(d, "default") == d / "audio.mp3"


def test_delete_topic_cleans_episodes(lib_env):
    t = library.create_topic("T")
    tid = t["id"]
    ep = lib_env["episodes"]
    (ep / f"{tid}.mp3").write_bytes(b"x")
    (ep / f"{tid}_podcast.json").write_text("{}", encoding="utf-8")
    (ep / "unrelated.mp3").write_bytes(b"x")

    library.delete_topic(tid)
    assert not (ep / f"{tid}.mp3").exists()
    assert not (ep / f"{tid}_podcast.json").exists()
    assert (ep / "unrelated.mp3").exists()


def test_safe_path_traversal():
    with pytest.raises(ValueError):
        library.topic_dir("../evil")
    with pytest.raises(ValueError):
        library.item_path("ok-topic", "..\\evil")


# ---------------------------------------------------------------- API

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["mode"] == "dry_run"  # 隔离环境下没有 key


def test_voice_direct_request_contains_question_and_light_direction(client):
    tid = client.post("/api/topics", json={"name": "Prompt"}).json()["id"]
    iid = client.post(
        f"/api/topics/{tid}/items",
        json={"question": "Do you like your hometown?", "natural_english": "Yeah, I do."},
    ).json()["id"]
    r = client.get(f"/api/topics/{tid}/items/{iid}/voice-direct-request")
    assert r.status_code == 200
    text = r.json()["text"]
    assert "Do you like your hometown?" in text
    assert "[relaxed]" in text and "[curious]" in text


def test_settings_reject_paid_tts_model(client):
    r = client.put("/api/settings", json={"model": "s2.1-pro"})
    assert r.status_code == 422


def test_api_patch_partial_update_regression(client, lib_env):
    """回归：PATCH 只传一个字段时，其他字段不能被清空。"""
    tid = client.post("/api/topics", json={"name": "T"}).json()["id"]
    r = client.post(f"/api/topics/{tid}/items", json={"question": "Q1", "chinese": "中文"})
    iid = r.json()["id"]

    r = client.patch(f"/api/topics/{tid}/items/{iid}", json={"chinese": "新中文"})
    assert r.status_code == 200
    full = client.get(f"/api/topics/{tid}/items/{iid}").json()
    assert full["chinese"] == "新中文"
    assert full["question"] == "Q1", "PATCH 不应清空未提交的字段"

    # 空 PATCH → 400 而不是静默清空
    assert client.patch(f"/api/topics/{tid}/items/{iid}", json={}).status_code == 400


def test_api_track_validation(client, lib_env):
    tid = client.post("/api/topics", json={"name": "T"}).json()["id"]
    iid = client.post(f"/api/topics/{tid}/items", json={"question": "Q"}).json()["id"]

    r = client.post(f"/api/topics/{tid}/items/{iid}/generate", json={"track": "bogus"})
    assert r.status_code == 422
    assert client.post(f"/api/topics/{tid}/generate", json={"track": "bogus"}).status_code == 422
    assert client.get(f"/api/topics/{tid}/episode?track=bogus").status_code == 422


@pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="需要 ffmpeg")
def test_dry_run_generate_and_assemble(client, lib_env):
    """dry-run 全流程：建条目 → 生成播客轨 → 音频/时间轴可读 → 合成整集。"""
    tid = client.post("/api/topics", json={"name": "E2E"}).json()["id"]
    iid = client.post(
        f"/api/topics/{tid}/items",
        json={"question": "Q?", "podcast_text": "A: Hello there.\nB: Wow, hi!"},
    ).json()["id"]
    client.put("/api/settings", json={"dry_run": True})

    r = client.post(f"/api/topics/{tid}/items/{iid}/generate", json={"track": "podcast"})
    assert r.status_code == 200
    job_id = r.json()["job_id"]

    deadline = time.time() + 90
    job = None
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] != "running":
            break
        time.sleep(0.3)
    assert job and job["state"] == "done", f"任务未完成: {job}"

    full = client.get(f"/api/topics/{tid}/items/{iid}").json()
    assert full["status"] == "generated"

    # 音频端点
    r_audio = client.get(f"/api/topics/{tid}/items/{iid}/audio/podcast")
    assert r_audio.status_code == 200
    assert len(r_audio.content) > 1000

    # 时间轴端点（dry-run 逐段实测 + 指纹校验；载荷含 lines/words/mode）
    tl = client.get(f"/api/topics/{tid}/items/{iid}/timeline/podcast").json()
    assert len(tl["lines"]) == 2
    assert tl["lines"][0]["start"] == 0
    assert tl["lines"][-1]["end"] >= tl["lines"][-1]["start"]
    assert tl["mode"] == "measured"

    # 合成整集（后台任务，M05）+ 清单
    m = client.post(f"/api/topics/{tid}/episode?track=podcast")
    assert m.status_code == 200
    job_id = m.json()["job_id"]
    asm_deadline = time.time() + 90
    asm_job = None
    while time.time() < asm_deadline:
        asm_job = client.get(f"/api/jobs/{job_id}").json()
        if asm_job["state"] != "running":
            break
        time.sleep(0.2)
    assert asm_job and asm_job["state"] == "done", asm_job
    manifest = asm_job["result"]
    assert manifest["item_count"] == 1
    assert client.get(f"/api/topics/{tid}/episode?track=podcast").json()["file"] == manifest["file"]

    # 删除话题应连带清理整集产物
    client.delete(f"/api/topics/{tid}")
    assert client.get(f"/api/topics/{tid}/episode").status_code == 404
