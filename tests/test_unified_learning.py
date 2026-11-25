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
