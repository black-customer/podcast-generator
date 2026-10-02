"""Q05 私有草稿、播放位置与题库状态回归，全部使用临时合成数据。"""
import json

import pytest
from fastapi.testclient import TestClient

from server import bank, library
from server.main import app


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    from server import experience

    monkeypatch.setattr(library, "TOPICS_DIR", tmp_path / "topics")
    monkeypatch.setattr(experience, "PRIVATE_DIR", tmp_path / "private")
    snapshot = {"topics": [], "sets": [], "questions": [
        {"id": "q1", "part": 1, "topic_id": "", "text": "Your home?", "text_zh": "家"},
        {"id": "q2", "part": 1, "topic_id": "", "text": "Your work?", "text_zh": "工作"},
    ]}
    monkeypatch.setattr(bank, "load_bank", lambda *a: snapshot)
    topic = library.create_topic("Synthetic Q05")
    return experience, snapshot, topic, TestClient(app)


def test_filters_before_paging_and_random():
    snap = {"topics": [], "sets": [], "questions": [
        {"id": str(i), "part": 1, "topic_id": "", "text": f"Question {i}",
         "text_zh": ""} for i in range(25)]}
    answered = {bank.norm_title("Question 24"): {"has_audio": False}}
    result = bank.query_questions(snap, answered_map=answered, answer_status="answered")
    assert result["total"] == 1 and result["items"][0]["id"] == "24"
    result = bank.query_questions(snap, answered_map=answered, answer_status="unanswered",
                                 random_pick=True)
    assert result["total"] == 24 and result["items"][0]["id"] != "24"


def test_random_selection_can_restore_its_page(monkeypatch):
    import random
    monkeypatch.setattr(random, "choice", lambda rows: rows[-1])
    snap = {"topics": [], "sets": [], "questions": [
        {"id": str(i), "part": 1, "topic_id": "", "text": f"Question {i}",
         "text_zh": ""} for i in range(25)]}
    result = bank.query_questions(snap, random_pick=True)
    assert result["selected_page"] == 2 and result["items"][0]["id"] == "24"


def test_answers_empty_excluded_latest_creation_not_update(isolated):
    _, _, topic, client = isolated
    library.create_item(topic["id"], {"question": "Your work?"})
    old = library.create_item(topic["id"], {"question": "Your home?", "chinese": "旧回答"})
    new = library.create_item(topic["id"], {"question": "Your home?", "original_answer": "新回答"})
    for item, created, updated in [(old, "2020-01-01T00:00:00Z", "2030-01-01T00:00:00Z"),
                                    (new, "2021-01-01T00:00:00Z", "2021-01-01T00:00:00Z")]:
        d = library.item_path(topic["id"], item["id"])
        meta = json.loads((d / "meta.json").read_text())
        meta.update(created_at=created, updated_at=updated)
        (d / "meta.json").write_text(json.dumps(meta))
    result = client.get("/api/bank/questions?answer_status=answered").json()
    assert result["total"] == 1
    assert result["items"][0]["answered_item"]["item_id"] == new["id"]
    versions = client.get("/api/bank/questions/q1/answers").json()["answers"]
    assert [v["item_id"] for v in versions] == [new["id"], old["id"]]


def test_draft_revision_delete_conflict_and_changed_question(isolated):
    _, snap, _, client = isolated
    url = "/api/answer-drafts/q1"
    body = {"question_text": "Your home?", "answer": "my draft", "mode": "api", "revision": 0}
    saved = client.put(url, json=body).json()
    assert saved["revision"] == 1
    assert client.put(url, json=body).status_code == 409
    assert client.delete(url + "?revision=0").status_code == 409
    assert client.get(url).json()["answer"] == "my draft"
    snap["questions"][0]["text"] = "Changed question"
    assert client.get(url).json()["question_changed"]
    assert client.put(url, json={**body, "revision": 1}).status_code == 409
    assert client.delete(url + "?revision=1").status_code == 200
    assert client.get(url).json()["revision"] == 2


def test_corruption_and_atomic_failure_preserve_file(isolated, monkeypatch):
    exp, _, _, client = isolated
    url = "/api/answer-drafts/q1"
    body = {"question_text": "Your home?", "answer": "original", "revision": 0}
    assert client.put(url, json=body).status_code == 200
    path = exp.PRIVATE_DIR / "answer_drafts.v1.json"
    before = path.read_bytes()
    def fail(*args):
        raise OSError("synthetic atomic failure")
    monkeypatch.setattr(exp, "atomic_write_text", fail)
    assert client.put(url, json={**body, "answer": "new", "revision": 1}).status_code == 503
    assert path.read_bytes() == before
    path.write_text("{broken", encoding="utf-8")
    assert client.get(url).status_code == 503
    assert path.read_text() == "{broken"


def test_search_original_dialogue_paging_compat(isolated):
    _, _, topic, client = isolated
    for i in range(22):
        library.create_item(topic["id"], {"question": f"Synthetic {i}",
                                        "original_answer": "私密needle",
                                        "podcast_text": "A: UNIQUE dialogue"})
    assert len(client.get("/api/search?q=needle").json()["results"]) == 22
    result = client.get("/api/search?q=NEEDLE&page=2&page_size=20").json()
    assert result["total"] == 22 and len(result["results"]) == 2
    assert "needle" in result["results"][0]["snippet"]
    assert len(client.get("/api/search?q=unique").json()["results"]) == 22


def test_progress_track_change_completion_and_deletion(isolated, monkeypatch):
    exp, _, topic, client = isolated
    monkeypatch.setattr(exp.audio, "probe_duration", lambda p: 20.0)
    item = library.create_item(topic["id"], {"question": "Your home?", "chinese": "回答"})
    d = library.item_path(topic["id"], item["id"])
    (d / "audio_monologue.mp3").write_bytes(b"synthetic old audio")
    query = f"?topic_id={topic['id']}&item_id={item['id']}&track=monologue"
    info = client.get("/api/listening-progress" + query).json()
    body = {"topic_id": topic["id"], "item_id": item["id"], "track": "monologue",
            "audio_fingerprint": info["audio_fingerprint"], "position": 8, "completed": False}
    assert client.put("/api/listening-progress", json=body).status_code == 200
    assert client.get("/api/listening-progress" + query).json()["position"] == 8
    assert client.get("/api/listening-progress/latest").json()["position"] == 8
    (d / "audio_monologue.mp3").write_bytes(b"synthetic new audio")
    assert client.get("/api/listening-progress" + query).json()["state"] == "audio_changed"
    assert client.put("/api/listening-progress", json=body).status_code == 409
    info = client.get("/api/listening-progress" + query).json()
    body["audio_fingerprint"] = info["audio_fingerprint"]
    assert client.put("/api/listening-progress", json={**body, "position": 20,
                                                      "completed": True}).status_code == 200
    assert client.get("/api/listening-progress" + query).json()["position"] == 0
    (d / "audio_monologue.mp3").write_bytes(b"third audio version")
    changed = client.get("/api/listening-progress" + query).json()
    assert changed["state"] == "audio_changed" and changed["completed"] is False
    library.delete_item(topic["id"], item["id"])
    assert client.get("/api/listening-progress/latest").json()["latest"] is None


def test_full_cue_card_and_random_api(isolated):
    _, snap, topic, client = isolated
    cue = "Describe your home.\nYou should say: where it is."
    snap["questions"][0]["text"] = cue
    library.create_item(topic["id"], {"question": cue, "chinese": "房子在河边"})
    assert client.get("/api/bank/questions?answer_status=answered").json()["total"] == 1
    result = client.get("/api/bank/questions?answer_status=answered&random=1").json()
    assert len(result["items"]) == 1
    assert client.get("/api/bank/questions?answer_status=unanswered&q=work&random=1").json()[
        "items"][0]["id"] == "q2"


@pytest.mark.parametrize("content", ['[]', '{"version":2,"records":{}}',
                                    '{"version":1,"records":{"q1":{"revision":"bad"}}}',
                                    '{"version":1,"records":{"q1":{"revision":0,"answer":"x"}}}'])
def test_invalid_private_schema_never_overwritten(isolated, content):
    exp, _, _, client = isolated
    exp.PRIVATE_DIR.mkdir()
    path = exp.PRIVATE_DIR / "answer_drafts.v1.json"
    path.write_text(content, encoding="utf-8")
    body = {"answer": "x", "revision": 0, "question_text": "Your home?"}
    assert client.put("/api/answer-drafts/q1", json=body).status_code == 503
    assert path.read_text() == content


def test_invalid_completion_flag_is_preserved_not_treated_as_finished(isolated):
    exp, _, _, client = isolated
    exp.PRIVATE_DIR.mkdir()
    path = exp.PRIVATE_DIR / "listening_progress.v1.json"
    row = {"kind": "item", "topic_id": "t1", "item_id": "i1", "track": "podcast",
           "audio_fingerprint": "f" * 64, "position": 8, "completed": "false",
           "duration": 20, "saved_at": "2026-10-02T00:00:00+00:00"}
    path.write_text(json.dumps({"version": 1, "records": {"source": row}}))
    before = path.read_bytes()
    assert client.get("/api/listening-progress/latest").status_code == 503
    assert path.read_bytes() == before


def test_orphan_draft_and_invalid_ids(isolated):
    _, snap, _, client = isolated
    body = {"answer": "保留原草稿", "revision": 0, "question_text": "Your home?"}
    assert client.put("/api/answer-drafts/q1", json=body).status_code == 200
    snap["questions"] = []
    orphan = client.get("/api/answer-drafts").json()["drafts"][0]
    assert orphan["question_missing"] and orphan["answer"] == "保留原草稿"
    assert client.get("/api/answer-drafts/invalid.id").status_code == 422
    assert client.get("/api/listening-progress?topic_id=..&item_id=x").status_code == 422


def test_progress_default_alias_and_episode(isolated, tmp_path, monkeypatch):
    exp, _, topic, client = isolated
    from server import assemble
    monkeypatch.setattr(exp.audio, "probe_duration", lambda p: 20.0)
    monkeypatch.setattr(assemble, "EPISODES_DIR", tmp_path / "episodes")
    assemble.EPISODES_DIR.mkdir()
    item = library.create_item(topic["id"], {"question": "Your home?", "chinese": "回答"})
    path = library.item_path(topic["id"], item["id"])
    (path / "audio.mp3").write_bytes(b"legacy")
    info = client.get(f"/api/listening-progress?topic_id={topic['id']}&item_id={item['id']}"
                      "&track=default").json()
    assert info["track"] == "monologue"
    body = {**info, "position": 1000}
    assert client.put("/api/listening-progress", json=body).json()["position"] < 20
    assert client.get(f"/api/listening-progress?topic_id={topic['id']}&item_id={item['id']}"
                      "&track=monologue").json()["position"] > 19
    assemble.episode_path(topic["id"], "default").write_bytes(b"legacy episode")
    info = client.get(f"/api/listening-progress?kind=episode&topic_id={topic['id']}"
                      "&track=default").json()
    assert client.put("/api/listening-progress", json={**info, "position": 4}).status_code == 200


def test_progress_atomic_failure_and_pack_privacy(isolated, tmp_path, monkeypatch):
    exp, _, topic, client = isolated
    import zipfile

    from server import pack
    monkeypatch.setattr(exp.audio, "probe_duration", lambda p: 20.0)
    item = library.create_item(topic["id"], {"question": "Your home?", "chinese": "公开回答"})
    (library.item_path(topic["id"], item["id"]) / "audio_monologue.mp3").write_bytes(b"audio")
    info = client.get(f"/api/listening-progress?topic_id={topic['id']}&item_id={item['id']}"
                      "&track=monologue").json()
    assert client.put("/api/listening-progress", json={**info, "position": 8}).status_code == 200
    path = exp.PRIVATE_DIR / "listening_progress.v1.json"
    before = path.read_bytes()
    def fail(*args):
        raise OSError("synthetic disk failure")
    monkeypatch.setattr(exp, "atomic_write_text", fail)
    assert client.put("/api/listening-progress", json={**info, "position": 9}).status_code == 503
    assert path.read_bytes() == before
    result = pack.build_pack(out_path=tmp_path / "pack.zip", topic_ids=[topic["id"]])
    with zipfile.ZipFile(result["path"]) as archive:
        assert not any("private" in name or "draft" in name for name in archive.namelist())


def test_answer_times_missing_invalid_and_timezone_order(isolated):
    _, _, topic, client = isolated
    created = []
    for time in ["2026-01-01T10:00:00+08:00", "2026-01-01T05:00:00+00:00", "invalid", None]:
        item = library.create_item(topic["id"], {"question": "Your home?", "chinese": "回答"})
        path = library.item_path(topic["id"], item["id"]) / "meta.json"
        meta = json.loads(path.read_text())
        meta["created_at"] = time
        path.write_text(json.dumps(meta))
        created.append(item["id"])
    versions = client.get("/api/bank/questions/q1/answers").json()["answers"]
    assert versions[0]["item_id"] == created[1]
    assert versions[-1]["created_at"] == ""
