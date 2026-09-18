"""M14/M16 测试：批量导入+lint+搜索+统计+自媒体草稿。"""
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient

from server import production


@pytest.fixture()
def prod_env(tmp_path, monkeypatch):
    from server import library as lib_mod

    topics = tmp_path / "topics"
    episodes = tmp_path / "episodes"
    for d in (topics, episodes, tmp_path / ".tmp"):
        d.mkdir(parents=True)
    monkeypatch.setattr(lib_mod, "TOPICS_DIR", topics)
    monkeypatch.setattr(lib_mod, "EPISODES_DIR", episodes)
    from server import assemble, audio, config, jobs
    monkeypatch.setattr(assemble, "EPISODES_DIR", episodes)
    monkeypatch.setattr(audio, "TMP_DIR", tmp_path / ".tmp")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(jobs, "JOBS_FILE", tmp_path / "jobs.json")
    from server.main import app
    with TestClient(app) as c:
        yield c


BATCH = """## Do you work or are you a student?
### 中文
我还是学生，学计算机。
### Natural English
I am technically still a student, majoring in computer science.

## Where is your hometown?
### 中文
我来自一个挺小的城市。
### Natural English
I am from a pretty small city, you know.
"""

BATCH_BAD = """## Bad item
### Natural English
[evil laughter] Totally fine sentence with CJK 汉字 mixed in.
"""


# ---------------------------------------------------------------- lint

def test_lint_script_detects_tags_and_cjk():
    r = production.lint_script("Nice line. [evil laughter] with 汉字")
    assert r["ok"] is False
    kinds = {w["kind"] for w in r["warnings"]}
    assert "disallowed_tags" in kinds and "cjk_in_script" in kinds
    assert "[evil laughter]" not in r["cleaned"]


def test_lint_script_clean():
    r = production.lint_script("Well, I am fine. [slight pause] You know it.")
    assert r["ok"] is True


# ---------------------------------------------------------------- 批量导入

def test_parse_batch(prod_env):
    entries = production.parse_batch(BATCH)
    assert len(entries) == 2
    assert entries[0]["question"] == "Do you work or are you a student?"
    assert "computer science" in entries[0]["natural_english"]
    assert "我还是学生" in entries[0]["chinese"]


def test_import_batch_creates_items(prod_env):
    c = prod_env
    r = c.post("/api/import-batch", json={"topic": "BatchT", "text": BATCH})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 2 and body["updated"] == 0
    items = c.get(f"/api/topics/{body['topic_id']}").json()["items"]
    assert len(items) == 2


def test_import_batch_dedup_and_reject(prod_env):
    c = prod_env
    r1 = c.post("/api/import-batch", json={"topic": "BatchD", "text": BATCH})
    tid = r1.json()["topic_id"]
    # 重复导入 → 更新而非新建
    r2 = c.post("/api/import-batch", json={"topic": "BatchD", "text": BATCH})
    assert r2.json()["updated"] == 2
    assert len(c.get(f"/api/topics/{tid}").json()["items"]) == 2
    # 空内容 + 全空脚本 → 拒绝
    r3 = c.post("/api/import-batch", json={"topic": "BatchD", "text": BATCH_BAD, "lint": True})
    body3 = r3.json()
    assert body3["rejected"] == 1


# ---------------------------------------------------------------- 搜索与统计

def test_search(prod_env):
    c = prod_env
    tid = c.post("/api/topics", json={"name": "S"}).json()["id"]
    payload = {"question": "Do you like coffee?", "chinese": "我喜欢咖啡"}
    c.post(f"/api/topics/{tid}/items", json=payload)
    r = c.get("/api/search", params={"q": "coffee"})
    hits = r.json()["results"]
    assert any("coffee" in h["title"].lower() for h in hits)


def test_stats(prod_env):
    c = prod_env
    s = c.get("/api/stats").json()
    assert {"topics", "items", "generated", "audio_sec"} <= set(s.keys())


# ---------------------------------------------------------------- 自媒体草稿

def test_content_drafts(prod_env):
    c = prod_env
    tid = c.post("/api/topics", json={"name": "Drafts"}).json()["id"]
    c.post(f"/api/topics/{tid}/items", json={
        "question": "Do you like coffee?",
        "chinese": "我超爱咖啡。",
        "natural_english": "I love coffee. It is my daily fuel. Every morning starts with it.",
    })
    r = c.get(f"/api/topics/{tid}/drafts")
    assert r.status_code == 200
    d = r.json()
    assert "I love coffee" in d["xiaohongshu"]
    assert "🧵" in d["thread"]
    assert "【Do you like coffee?】" in d["video_script"]
