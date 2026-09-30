"""L04 口答日程：旧记录、间隔、改稿、跨日与原子提交。"""
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server import library, oral_review, study, study_progress


@pytest.fixture()
def env(tmp_path, monkeypatch):
    topics = tmp_path / "topics"
    topics.mkdir()
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    monkeypatch.setattr(study_progress, "PRIVATE_DIR", tmp_path / "study_private")
    monkeypatch.setattr(oral_review, "REVIEW_FILE", tmp_path / "study_private" / "oral_review.json")
    day = [date(2026, 9, 30)]
    monkeypatch.setattr(oral_review, "_today", lambda: day[0])
    monkeypatch.setattr(oral_review, "_now_iso", lambda: f"{day[0].isoformat()}T10:00:00+08:00")
    monkeypatch.setattr(library, "now_iso", lambda: f"{day[0].isoformat()}T10:00:00")
    topic = library.create_topic("Daily life")
    return {"topic": topic["id"], "day": day, "root": tmp_path}


def add_sentence(env, n: int, legacy: bool = False) -> tuple[str, str]:
    tid = env["topic"]
    item = library.create_item(tid, {
        "question": f"What do you do on day {n}?",
        "original_answer": "I walk every day.",
        "natural_english": "I go for a walk.",
        "podcast_text": f"A: What do you do on day {n}?\nB: I go for a walk.",
    })
    iid = item["id"]
    (library.item_path(tid, iid) / "audio_podcast.mp3").write_bytes(b"audio")
    study.save_material(tid, iid, {"complete_chinese": "我去散步。", "sentences": [{
        "zh": "我去散步。", "en": "I go for a walk.",
        "explanation": "常见表达。", "usage": "描述日常活动。",
    }]})
    study_progress.save_progress(tid, iid, {"stage": "summary", "facts": {
        "0": {"passed": True, "hint_used": True},
    }})
    if legacy:
        state_path = study_progress.PRIVATE_DIR / tid / iid / "state.json"
        import json

        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["facts"]["0"].pop("passed_at", None)
        state["facts"]["0"].pop("passed_source_fingerprint", None)
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    return tid, iid


def test_legacy_import_and_ten_card_round(env):
    for n in range(12):
        add_sentence(env, n, legacy=True)
    today = oral_review.today_overview()
    assert today["due_count"] == 12
    assert len(today["due_preview"]) == 10
    assert today["history"]["undated_legacy_count"] == 12
    first = oral_review.start_session()
    assert len(first["card_ids"]) == 10
    assert oral_review.start_session()["id"] == first["id"]
    assert oral_review.get_session(first["id"])["current_index"] == 0


def test_interval_idempotency_and_actual_completion_day(env):
    tid, iid = add_sentence(env, 1)
    env["day"][0] = date(2026, 10, 1)
    session = oral_review.start_session()
    sid = session["id"]
    oral_review.session_action(sid, "answered_without_recording", "action-1")
    submitted = oral_review.submit_attempt(sid, "attempt-1", "independent")
    assert submitted["next_due_date"] == "2026-10-04"
    assert oral_review.submit_attempt(sid, "attempt-1", "independent") == submitted
    early = oral_review.start_session(tid, iid, 0)
    oral_review.session_action(early["id"], "answered_without_recording", "action-2")
    again = oral_review.submit_attempt(early["id"], "attempt-2", "independent")
    assert again["next_due_date"] == "2026-10-04"
    assert again["schedule_adjusted"] is False
    env["day"][0] = date(2026, 10, 4)
    third = oral_review.start_session()
    oral_review.session_action(third["id"], "answered_without_recording", "action-3")
    assert oral_review.submit_attempt(third["id"], "attempt-3", "independent") [
        "next_due_date"
    ] == "2026-10-11"


def test_hint_blocks_independent_and_failure_resets_next_day(env):
    add_sentence(env, 2)
    env["day"][0] = date(2026, 10, 1)
    sid = oral_review.start_session()["id"]
    oral_review.session_action(sid, "hint", "hint-1")
    oral_review.session_action(sid, "answered_without_recording", "answer-1")
    with pytest.raises(ValueError):
        oral_review.submit_attempt(sid, "attempt-1", "independent")
    result = oral_review.submit_attempt(sid, "attempt-2", "needs_hint")
    assert result["next_due_date"] == "2026-10-02"
    env["day"][0] = date(2026, 10, 2)
    sid2 = oral_review.start_session()["id"]
    oral_review.session_action(sid2, "show_answer", "show-1")
    assert oral_review.submit_attempt(sid2, "attempt-3", "unable")[
        "next_due_date"
    ] == "2026-10-03"


def test_text_change_suspends_old_card_and_voice_change_keeps_it(env):
    tid, iid = add_sentence(env, 3, legacy=True)
    assert oral_review.today_overview()["due_count"] == 1
    oral_review.start_session()
    audio = library.item_path(tid, iid) / "audio_podcast.mp3"
    audio.write_bytes(b"new-voice")
    assert oral_review.today_overview()["due_count"] == 1
    library.update_item_texts(tid, iid, {"natural_english": "Revised answer."})
    assert oral_review.today_overview()["due_count"] == 0
    assert oral_review.today_overview()["needs_material_count"] == 1


def test_atomic_failure_preserves_previous_schedule(env, monkeypatch):
    add_sentence(env, 4, legacy=True)
    sid = oral_review.start_session()["id"]
    oral_review.session_action(sid, "answered_without_recording", "answer-1")
    before = oral_review.REVIEW_FILE.read_bytes()

    def fail_write(path, content):
        raise OSError("disk full")

    monkeypatch.setattr(oral_review, "atomic_write_text", fail_write)
    with pytest.raises(OSError):
        oral_review.submit_attempt(sid, "attempt-1", "independent")
    assert oral_review.REVIEW_FILE.read_bytes() == before


def test_deleted_source_is_not_executable(env):
    tid, iid = add_sentence(env, 5, legacy=True)
    sid = oral_review.start_session()["id"]
    library.delete_item(tid, iid)
    assert oral_review.today_overview()["due_count"] == 0
    assert oral_review.get_session(sid)["current_card"]["availability"] == "missing"
    skipped = oral_review.session_action(sid, "skip", "skip-1")
    assert skipped["state"] == "completed"


def test_today_shows_real_continue_time(env):
    tid = env["topic"]
    iid = library.create_item(tid, {"question": "What do you do after work?"})["id"]
    study_progress.save_progress(tid, iid, {"stage": "dictation", "before_started": True})
    listed = oral_review.today_overview()["continue_learning"]
    assert listed[0]["item_id"] == iid
    assert listed[0]["last_activity_at"] == "2026-09-30T10:00:00"


def test_unpersisted_old_pass_does_not_enroll_revised_material(env):
    tid, iid = add_sentence(env, 6)
    assert oral_review.today_overview()["due_count"] == 0
    library.update_item_texts(tid, iid, {"natural_english": "Revised answer."})
    study.save_material(tid, iid, {"complete_chinese": "我去散步。", "sentences": [{
        "zh": "我去散步。", "en": "I go for a walk.",
        "explanation": "新的讲解。", "usage": "日常活动。",
    }]})
    assert oral_review.today_overview()["due_count"] == 0
    assert oral_review.get_card_for_sentence(tid, iid, 0)["status"] == "not_enrolled"


def test_pausing_current_card_blocks_attempt_until_restored(env):
    add_sentence(env, 7, legacy=True)
    session = oral_review.start_session()
    card_id = session["current_card"]["id"]
    oral_review.set_card_paused(card_id, True)
    assert oral_review.get_session(session["id"])["current_card"]["availability"] == "paused"
    with pytest.raises(ValueError):
        oral_review.session_action(session["id"], "answered_without_recording", "answer-1")
    oral_review.set_card_paused(card_id, False)
    assert oral_review.get_session(session["id"])["current_card"]["availability"] == "ready"


def test_explicit_no_recording_clears_recording_evidence(env):
    tid, iid = add_sentence(env, 8, legacy=True)
    session = oral_review.start_session()
    record = study_progress.save_recording(tid, iid, "oral_review", b"audio", 2.0,
                                           "audio/webm", 0, session["id"])
    oral_review.attach_recording(session["id"], record["id"])
    changed = oral_review.session_action(session["id"], "answered_without_recording", "answer-1")
    assert changed["recording_id"] is None
    result = oral_review.submit_attempt(session["id"], "attempt-1", "independent")
    assert result["recorded"] is False
    assert study_progress.read_recording(tid, iid, record["id"])[0] == b"audio"


def test_deleted_recording_cannot_be_claimed_as_evidence(env):
    tid, iid = add_sentence(env, 9, legacy=True)
    session = oral_review.start_session()
    record = study_progress.save_recording(tid, iid, "oral_review", b"audio", 2.0,
                                           "audio/webm", 0, session["id"])
    oral_review.attach_recording(session["id"], record["id"])
    study_progress.delete_recording(tid, iid, record["id"])
    with pytest.raises(ValueError):
        oral_review.submit_attempt(session["id"], "attempt-1", "independent")


def test_cross_midnight_round_keeps_snapshot_and_uses_completion_day(env):
    for n in range(2):
        add_sentence(env, n, legacy=True)
    session = oral_review.start_session()
    ids = session["card_ids"]
    oral_review.session_action(session["id"], "answered_without_recording", "answer-1")
    env["day"][0] = date(2026, 10, 1)
    assert oral_review.get_session(session["id"])["card_ids"] == ids
    assert oral_review.submit_attempt(session["id"], "attempt-1", "independent")[
        "next_due_date"
    ] == "2026-10-04"


def test_history_can_filter_by_question_and_day(env):
    tid, iid = add_sentence(env, 10, legacy=True)
    add_sentence(env, 11, legacy=True)
    session = oral_review.start_session()
    for n in range(2):
        oral_review.session_action(session["id"], "answered_without_recording", f"answer-{n}")
        oral_review.submit_attempt(session["id"], f"attempt-{n}", "independent")
    history = oral_review.get_history(day="2026-09-30", topic_id=tid, item_id=iid)
    assert history["days"][0]["attempt_count"] == 1
    assert history["days"][0]["attempts"][0]["item_id"] == iid


def test_today_distinguishes_no_records_and_provides_material_recovery(env):
    assert oral_review.today_overview()["has_learning_records"] is False
    tid, iid = add_sentence(env, 12, legacy=True)
    oral_review.start_session()
    assert oral_review.today_overview()["has_learning_records"] is True
    library.update_item_texts(tid, iid, {"natural_english": "Changed answer."})
    recovery = oral_review.today_overview()["needs_material"][0]
    assert recovery["item_id"] == iid
    assert recovery["source_exists"] is True


def test_all_intervals_saturate_at_thirty_and_hint_resets(env):
    add_sentence(env, 13, legacy=True)
    for n, interval in enumerate((3, 7, 14, 30, 30)):
        session = oral_review.start_session()
        oral_review.session_action(session["id"], "answered_without_recording", f"answer-{n}")
        result = oral_review.submit_attempt(session["id"], f"attempt-{n}", "independent")
        expected = env["day"][0] + timedelta(days=interval)
        assert result["next_due_date"] == expected.isoformat()
        env["day"][0] = expected
    session = oral_review.start_session()
    oral_review.session_action(session["id"], "hint", "hint-reset")
    oral_review.session_action(session["id"], "answered_without_recording", "answer-reset")
    result = oral_review.submit_attempt(session["id"], "attempt-reset", "needs_hint")
    assert result["next_due_date"] == (env["day"][0] + timedelta(days=1)).isoformat()


def test_skip_does_not_postpone_card(env):
    add_sentence(env, 14, legacy=True)
    session = oral_review.start_session()
    original = session["current_card"]["due_date"]
    oral_review.session_action(session["id"], "skip", "skip-1")
    overview = oral_review.today_overview()
    assert overview["due_count"] == 1
    assert overview["due_preview"][0]["due_date"] == original


def test_concurrent_duplicate_submission_is_only_one_attempt(env):
    import threading

    add_sentence(env, 15, legacy=True)
    session = oral_review.start_session()
    oral_review.session_action(session["id"], "answered_without_recording", "answer-1")
    replies = []
    threads = [threading.Thread(target=lambda: replies.append(oral_review.submit_attempt(
        session["id"], "same-submission", "independent"
    ))) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    assert len(replies) == 2
    assert replies[0] == replies[1]
    assert oral_review.get_history()["days"][0]["attempt_count"] == 1


def test_oral_records_remain_outside_public_corpus_pack(env, monkeypatch):
    from server import pack

    tid, iid = add_sentence(env, 16, legacy=True)
    session = oral_review.start_session()
    oral_review.save_session_recording(session["id"], b"private-voice", 2.0, "audio/webm")
    oral_review.submit_attempt(session["id"], "private-attempt", "independent")
    monkeypatch.setattr(pack, "DATA_DIR", env["root"])
    out = pack.build_pack(out_path=env["root"] / "public.zip", topic_ids=[tid])
    with zipfile.ZipFile(out["path"]) as archive:
        names = archive.namelist()
        assert not any("study_private" in name or "oral_review" in name for name in names)
        assert not any(name.endswith(".webm") for name in names)
    assert study_progress.get_progress(tid, iid)["recordings"][0]["stage"] == "oral_review"


def test_manual_new_version_replaces_recovery_without_erasing_history(env):
    tid, iid = add_sentence(env, 17, legacy=True)
    session = oral_review.start_session()
    oral_review.session_action(session["id"], "answered_without_recording", "answer-1")
    oral_review.submit_attempt(session["id"], "attempt-1", "independent")
    library.update_item_texts(tid, iid, {"natural_english": "Revised answer."})
    study.save_material(tid, iid, {"complete_chinese": "我去散步。", "sentences": [{
        "zh": "我去散步。", "en": "I go for a walk.",
        "explanation": "复核后的讲解。", "usage": "日常活动。",
    }]})
    assert oral_review.today_overview()["needs_material"][0]["material_ready"] is True
    oral_review.enroll_card(tid, iid, 0)
    assert oral_review.today_overview()["needs_material_count"] == 0
    assert oral_review.get_history()["days"][0]["attempt_count"] == 1
