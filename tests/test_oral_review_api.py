"""L04 API：无录音自评、提示限制和私有口答录音。"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server import library, oral_review, study, study_progress


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    topics = tmp_path / "topics"
    topics.mkdir()
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    monkeypatch.setattr(study_progress, "PRIVATE_DIR", tmp_path / "study_private")
    monkeypatch.setattr(oral_review, "REVIEW_FILE", tmp_path / "study_private" / "oral_review.json")
    monkeypatch.setattr(oral_review, "_today", lambda: __import__("datetime").date(2026, 9, 30))
    monkeypatch.setattr(oral_review, "_now_iso", lambda: "2026-09-30T10:00:00+08:00")
    monkeypatch.setattr(library, "now_iso", lambda: "2026-09-30T10:00:00")
    t = library.create_topic("T")
    i = library.create_item(t["id"], {"question": "What do you do?",
        "original_answer": "I walk.", "natural_english": "I go for a walk.",
        "podcast_text": "A: What do you do?\nB: I go for a walk."})
    tid, iid = t["id"], i["id"]
    (library.item_path(tid, iid) / "audio_podcast.mp3").write_bytes(b"audio")
    study.save_material(tid, iid, {"complete_chinese": "我去散步。", "sentences": [{
        "zh": "我去散步。", "en": "I go for a walk.",
        "explanation": "常见表达。", "usage": "日常活动。"}]})
    study_progress.save_progress(tid, iid, {"stage": "summary", "facts": {
        "0": {"passed": True, "hint_used": True}}})
    from server.main import app

    with TestClient(app) as client:
        yield client, tid, iid


def test_oral_review_api_hides_answer_then_records_self_report(setup):
    client, tid, iid = setup
    overview = client.get("/api/study/today")
    assert overview.status_code == 200
    assert overview.json()["due_count"] == 0
    client.post(f"/api/topics/{tid}/items/{iid}/study/oral-review")
    session = client.post("/api/study/review-sessions", json={
        "topic_id": tid, "item_id": iid, "sentence_index": 0,
    }).json()
    sid = session["id"]
    assert "en" not in session["current_card"]
    answer = client.post(f"/api/study/review-sessions/{sid}/actions", json={
        "action": "answered_without_recording", "action_id": "a-1",
    })
    assert answer.status_code == 200
    assert answer.json()["current_card"]["en"] == "I go for a walk."
    saved = client.post(f"/api/study/review-sessions/{sid}/attempts", json={
        "rating": "independent", "submission_id": "s-1",
    })
    assert saved.status_code == 200
    assert saved.json()["recorded"] is False
    assert saved.json()["spoken_self_report"] is True
    assert client.post(f"/api/study/review-sessions/{sid}/attempts", json={
        "rating": "independent", "submission_id": "s-1",
    }).json() == saved.json()
    history = client.get("/api/study/history").json()
    assert history["days"][0]["attempt_count"] == 1
    assert history["dictation_passed_total"] == 1


def test_review_recording_is_separate_from_three_full_answer_stages(setup):
    client, tid, iid = setup
    client.post(f"/api/topics/{tid}/items/{iid}/study/oral-review")
    sid = client.post("/api/study/review-sessions", json={
        "topic_id": tid, "item_id": iid, "sentence_index": 0,
    }).json()["id"]
    response = client.post(f"/api/study/review-sessions/{sid}/recording?duration_sec=2.5",
                           content=b"spoken", headers={"Content-Type": "audio/webm"})
    assert response.status_code == 200
    records = client.get(f"/api/topics/{tid}/items/{iid}/study/progress").json()["recordings"]
    assert len(records) == 1
    assert records[0]["stage"] == "oral_review"
    assert records[0]["sentence_index"] == 0
    assert records[0]["session_id"] == sid
    restored = client.get(f"/api/study/review-sessions/{sid}").json()
    assert restored["phase"] == "compare"
    assert restored["recording_id"] == records[0]["id"]
    audio_url = f"/api/topics/{tid}/items/{iid}/study/recordings/{records[0]['id']}"
    assert client.get(audio_url).content == b"spoken"
    submitted = client.post(f"/api/study/review-sessions/{sid}/attempts", json={
        "rating": "independent", "submission_id": "recorded-attempt",
    })
    assert submitted.status_code == 200
    assert submitted.json()["recorded"] is True
    client.delete(audio_url)
    assert client.get("/api/study/history").json()["days"][0]["attempts"][0][
        "recording_available"
    ] is False
