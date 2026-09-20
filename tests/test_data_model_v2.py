"""M04 数据模型 v2 测试：原子写 / settings 脱敏 / 排序>100 / 参数校验。"""
import sys
import threading
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient

from server import library


@pytest.fixture()
def env(tmp_path, monkeypatch):
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
    from server.main import app
    with TestClient(app) as c:
        yield {"client": c, "topics": topics}


# ---------------------------------------------------------------- 原子写

def test_meta_write_is_atomic_no_corrupt_on_concurrent_writes(env):
    """并发 update_item_meta 不产生损坏的 meta.json（旧实现 write_text 直接覆盖）。"""
    t = library.create_topic("T")
    it = library.create_item(t["id"], {"question": "Q"})
    d = library.item_path(t["id"], it["id"])

    stop = threading.Event()
    errors = []

    def writer(n: int) -> None:
        i = 0
        while not stop.is_set() and i < 200:
            try:
                library.update_item_meta(t["id"], it["id"], **{f"counter_{n}": i})
            except Exception as exc:
                errors.append(str(exc))
            i += 1
        # 最后留一个正常 meta
        library.update_item_meta(t["id"], it["id"], final=True)

    threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(timeout=30)
    stop.set()

    assert not errors[:3]
    meta = library.load_meta(d)
    assert meta.get("final") is True
    assert meta.get("status")  # 结构完整


# ---------------------------------------------------------------- settings 脱敏

def test_get_settings_masks_api_key(env):
    c = env["client"]
    c.put(
        "/api/settings",
        json={
            "fish_api_key": "sk-fish-SECRETKEY123",
            "stepfun_api_key": "sk-step-SECRETKEY456",
        },
    )
    s = c.get("/api/settings").json()
    assert "SECRETKEY123" not in str(s)
    assert "SECRETKEY456" not in str(s)
    assert s.get("fish_api_key_set") is True
    assert s.get("stepfun_api_key_set") is True
    # test_connection 端点也不回传
    r = c.post("/api/settings/test").json()
    assert "SECRETKEY123" not in str(r)


# ---------------------------------------------------------------- 排序 > 100

def test_topic_ordering_beyond_100(env):
    """审计 A11：第 100+ 个话题应排在 099 之后、不落在 010 前。"""
    ids = []
    for i in range(103):
        ids.append(library.create_topic(f"T{i:03d}")["id"])
    listed = [t["id"] for t in library.list_topics()]
    assert listed == sorted(listed, key=lambda x: int(x.split("-")[0])), (
        f"排序断裂: {[x for x in listed if x.startswith('10')]}"
    )
    assert len(listed) == 103


# ---------------------------------------------------------------- settings 参数校验

def test_settings_validation_rejects_bad_values(env):
    c = env["client"]
    # segment_chars <= 0 会触发 split_text 无限循环（审计 A33）
    assert c.put("/api/settings", json={"segment_chars": 0}).status_code == 422
    assert c.put("/api/settings", json={"segment_chars": -5}).status_code == 422
    assert c.put("/api/settings", json={"speed": 5.0}).status_code == 422
    assert c.put("/api/settings", json={"temperature": 2.0}).status_code == 422
    assert c.put("/api/settings", json={"gap_ms": -100}).status_code == 422
    # 合法值照常通过
    assert c.put("/api/settings", json={"segment_chars": 500}).status_code == 200
    assert c.put("/api/settings", json={"speed": 1.05, "temperature": 0.7}).status_code == 200


def test_stepfun_settings_and_voice_filters(env):
    c = env["client"]
    saved = c.put(
        "/api/settings",
        json={
            "tts_provider": "stepfun",
            "question_voice_id": "lively-girl",
            "answer_voice_id": "vibrant-youth",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["tts_provider"] == "stepfun"

    female = c.get("/api/voices", params={"provider": "stepfun", "gender": "female"})
    assert female.status_code == 200
    assert len(female.json()) >= 2
    assert all(v["provider"] == "stepfun" and v["gender"] == "female" for v in female.json())

    sample = c.get("/api/voices/stepfun/lively-girl/sample")
    assert sample.status_code == 400
    assert "StepFun Key" in sample.json()["detail"]

    connection = c.post("/api/settings/test", params={"provider": "stepfun"})
    assert connection.status_code == 200
    assert connection.json()["stepfun"]["mode"] == "dry_run"
    assert c.put("/api/settings", json={"stepfun_tts_model": "stepaudio-3-tts"}).status_code == 422
