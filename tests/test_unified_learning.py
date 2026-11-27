"""统一复习队列保留雅思材料，并以同一日程调度新语块。"""

from datetime import date

import pytest

from server import arcade, capture_distill, captures, oral_review
from tests.test_captures import card, scene, store  # noqa: F401


@pytest.fixture
def review_env(store, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setattr(oral_review, "REVIEW_FILE", tmp_path / "review.json")
    monkeypatch.setattr(oral_review.study_progress, "PRIVATE_DIR", tmp_path / "study")
    monkeypatch.setattr(oral_review, "_today", lambda: date(2026, 11, 26))
    return tmp_path


def enroll(kind, index):
    if kind == "scene":
        id_ = captures.ingest_scenes([scene(f"note-{index}")])["capture_ids"][0]
    else:
        id_ = captures.ingest_snippet(text=f"Example {index}")["id"]
    capture_distill.complete_from_json(
        {"captures": [{"capture_id": id_, "cards": [card()]}]}, synthesize_audio=False,
    )
    row = captures.list_cards(capture_id=id_)[0]
    captures.approve_card(row["id"])
    return row["id"]


def test_unified_home_limits_and_interleaves_sources(review_env, monkeypatch):
    monkeypatch.setattr(arcade, "load_settings", lambda: {"daily_session_limit": 5})
    for i in range(9):
        enroll("scene" if i < 7 else "snippet", i)
    all_sources = arcade.home_cards(limit=5, include_pending=False)
    assert all_sources["due_total"] == 9 and all_sources["session_limit"] == 5
    sources = [row["source_type"] for row in all_sources["cards"]]
    assert len(sources) == 5 and "snippet" in sources[:4]
    assert arcade.home_cards(source="snippet", include_pending=False)["due_total"] == 2


def test_capture_fsrs_levels_and_suspend(review_env, monkeypatch):
    id_ = enroll("snippet", 1)
    assert oral_review.unified_due_cards()[0]["scaffolding_level"] == 1
    first = oral_review.grade_capture_card(id_, "good", "first")
    assert first["scaffolding_level"] == 2
    assert oral_review.grade_capture_card(id_, "good", "first") == first
    monkeypatch.setattr(oral_review, "_today", lambda: date(2026, 12, 15))
    easy = oral_review.grade_capture_card(id_, "easy", "easy")
    assert easy["scaffolding_level"] == 3 and easy["fsrs_grade"] == "easy"
    monkeypatch.setattr(oral_review, "_today", lambda: date(2027, 2, 1))
    assert oral_review.grade_capture_card(id_, "again", "again")["scaffolding_level"] == 2
    oral_review.suspend_card(id_)
    assert captures.get_card(id_)["status"] == "archived"
    assert oral_review.unified_due_cards() == []

def test_radio_interleaves_ielts_and_capture_sources(tmp_path, monkeypatch):
    from datetime import date

    from server import teaching_podcast as radio

    monkeypatch.setattr(captures, "CAPTURES_DIR", tmp_path / "captures")
    today = date.today().isoformat()
    ielts = {"en": "I take a short break.", "key_chunk": "take a short break"}
    attempt = {"topic_id": "demo", "item_id": "speaking", "sentence_index": 0,
               "en": ielts["en"], "question": "How do you rest?", "date": today}
    monkeypatch.setattr(radio.oral_review, "_load", lambda: {"cards": {}, "attempts": [attempt]})
    monkeypatch.setattr(radio.oral_review, "_today", lambda: date.fromisoformat(today))
    monkeypatch.setattr(radio.arcade, "_fresh_ielts", lambda *_: [])
    monkeypatch.setattr(radio, "_item_points", lambda *_: [ielts])
    monkeypatch.setattr(radio.library, "get_item_full",
                        lambda *_: {"question": attempt["question"]})
    monkeypatch.setattr(radio.study_progress, "get_progress", lambda *_: {})

    def row(id_, kind, en, chunk, group):
        return {"id": id_, "capture_id": id_, "en": en, "zh": "练习句",
                "target_chunk": chunk, "chunk_in_sentence": chunk, "status": "active",
                "capture": {"source_type": kind, "created_at": today, "title": group,
                            "source": {"series_id": group, "series_title": group}}}

    first = row("cap-a", "scene", "It makes sense.", "makes sense", "Show")
    second = row("cap-b", "scene", "I'll look into it.", "look into", "Show")
    third = row("cap-c", "scene", "Please keep going.", "keep going", "Other")
    excerpt = row("cap-d", "snippet", "It depends on the weather.", "depends on", "")
    monkeypatch.setattr(captures, "list_cards", lambda **_: [first, second, third, excerpt])
    monkeypatch.setattr(captures, "get_capture", lambda _: first["capture"])
    monkeypatch.setattr(radio, "generate", lambda _, points, *a, **kw: (points, kw))
    daily, _ = radio.for_today("en", "am_puck")
    assert [point["key_chunk"] for point in daily] == [
        "take a short break", "makes sense", "depends on", "look into",
    ]
    grouped, metadata = radio.for_capture("cap-a", "bilingual", "am_puck")
    assert [point["key_chunk"] for point in grouped] == ["makes sense", "look into"]
    assert metadata["capture_id"] == "cap-a"
    assert all("capture" not in point for point in grouped)

def test_agent_auto_approval_registers_card_in_shared_schedule(review_env):
    capture_id = captures.ingest_snippet(text="Do not put me on the spot.")["id"]
    result = capture_distill.complete_from_json(
        {"captures": [{"capture_id": capture_id, "cards": [card()]}]},
        auto_approve=True, synthesize_audio=False,
    )
    assert result["cards"] == 1
    card_id = captures.list_cards(capture_id=capture_id)[0]["id"]
    with oral_review._LOCK:
        scheduled = oral_review._load()["cards"][card_id]
    assert scheduled["capture_id"] == capture_id
    assert scheduled["due_date"] == "2026-11-26"


def test_home_preserves_ielts_card_when_old_chunk_cannot_be_clozed(monkeypatch):
    row = {"card_kind": "ielts", "source_type": "ielts", "audio_url": "/sample.mp3",
           "key_chunk": "used to study", "en": "I study at home.", "zh": "我在家学习。"}
    monkeypatch.setattr(arcade, "load_settings", lambda: {"daily_session_limit": 8})
    monkeypatch.setattr(oral_review, "unified_due_cards", lambda **_: [])
    monkeypatch.setattr(arcade, "_fresh_ielts", lambda *_: [row])
    monkeypatch.setattr(captures, "list_cards", lambda **_: [])
    monkeypatch.setattr(oral_review, "_load", lambda: {"cards": {}})
    cards = arcade.home_cards(source="ielts")["cards"]
    assert len(cards) == 1
    assert cards[0]["cloze_prompt"] == ""
    assert cards[0]["en"] == row["en"]
