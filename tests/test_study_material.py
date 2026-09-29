"""L02 逐句材料：原话证据、播报顺序、失效与旧数据兼容。"""
import json
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server import library, study


@pytest.fixture()
def item(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "TOPICS_DIR", tmp_path / "topics")
    (tmp_path / "topics").mkdir()
    topic = library.create_topic("After work")
    created = library.create_item(topic["id"], {
        "question": "What do you do after work?",
        "original_answer": "我去散步。It help me relaxed.",
        "natural_english": "I go for a walk. It helps me unwind.",
        "podcast_text": "A: What do you do after work?\nB: I go for a walk. It helps me unwind.",
    })
    path = library.item_path(topic["id"], created["id"])
    (path / "audio_podcast.mp3").write_bytes(b"audio")
    return topic["id"], created["id"], path


def material():
    return {
        "complete_chinese": "我下班去散步，这让我放松。",
        "sentences": [
            {"zh": "我去散步。", "en": "I go for a walk.",
             "explanation": "go for a walk 表示去散步。", "usage": "下班活动。"},
            {"zh": "这让我放松。", "en": "It helps me unwind.",
             "explanation": "help 后接动词原形。", "usage": "unwind 表示放松。",
             "original_error": {"quote": "It help me relaxed.",
                                "issue": "It 后用 helps，relaxed 应用动词原形。",
                                "correction": "It helps me relax."}},
        ],
    }


def test_material_roundtrip_and_order(item):
    tid, iid, path = item
    saved = study.save_material(tid, iid, material())
    assert saved["version"] == 1
    assert saved["sentences"][1]["en"] == "It helps me unwind."
    assert (path / "study_material.json").exists()
    assert not (path / "study_material.json.tmp~").exists()
    assert study.get_material(tid, iid)["status"] == "ready"


def test_rejects_made_up_errors_and_wrong_audio_text(item):
    tid, iid, path = item
    bad = material()
    bad["sentences"][1]["original_error"]["quote"] = "我去散步。"
    with pytest.raises(study.MaterialError):
        study.save_material(tid, iid, bad)
    assert not (path / "study_material.json").exists()
    bad = material()
    bad["sentences"][0]["en"] = "I walk after work."
    with pytest.raises(study.MaterialError):
        study.save_material(tid, iid, bad)


def test_chinese_input_has_no_personal_english_error(item):
    tid, iid, _ = item
    library.update_item_texts(tid, iid, {"original_answer": "我去散步，感觉放松。"})
    with pytest.raises(study.MaterialError):
        study.save_material(tid, iid, material())
    clean = material()
    clean["sentences"][1].pop("original_error")
    assert study.save_material(tid, iid, clean)["sentences"][1].get("original_error") is None


def test_english_input_can_cite_exact_original_error(item):
    tid, iid, _ = item
    library.update_item_texts(tid, iid, {"original_answer": "I go for a walk. It help me relaxed."})
    saved = study.save_material(tid, iid, material())
    assert saved["sentences"][1]["original_error"]["quote"] == "It help me relaxed."


def test_material_changes_when_source_changes_but_audio_survives(item):
    tid, iid, path = item
    study.save_material(tid, iid, material())
    library.update_item_texts(tid, iid, {"podcast_text": "A: Q?\nB: Different answer."})
    assert study.get_material(tid, iid)["status"] == "changed"
    assert path.joinpath("audio_podcast.mp3").exists()


def test_retry_status_overrides_stale_material_until_source_changes_again(item):
    tid, iid, _ = item
    study.save_material(tid, iid, material())
    library.update_item_texts(tid, iid, {"natural_english": "Revised answer."})
    assert study.get_material(tid, iid)["status"] == "changed"
    key = (tid, iid)
    with study._ACTIVE_LOCK:
        study._ACTIVE.add(key)
    try:
        study.set_status(tid, iid, "preparing")
        assert study.get_material(tid, iid)["status"] == "preparing"
    finally:
        with study._ACTIVE_LOCK:
            study._ACTIVE.discard(key)
    study.set_status(tid, iid, "failed", "synthetic failure")
    assert study.get_material(tid, iid)["status"] == "failed"
    library.update_item_texts(tid, iid, {"natural_english": "Revised again."})
    assert study.get_material(tid, iid)["status"] == "changed"


def test_old_item_needs_original_answer(item):
    tid, iid, _ = item
    library.update_item_texts(tid, iid, {"original_answer": ""})
    assert study.get_material(tid, iid)["status"] == "needs_input"


@pytest.fixture()
def legacy_item(tmp_path, monkeypatch):
    """旧版流水线条目：原始回答在 chinese.txt，没有 original_answer.txt。"""
    monkeypatch.setattr(library, "TOPICS_DIR", tmp_path / "topics")
    (tmp_path / "topics").mkdir()
    topic = library.create_topic("Legacy waves")
    created = library.create_item(topic["id"], {
        "question": "What do you do after work?",
        "chinese": "我下班去散步。这让我放松。",
        "natural_english": "I go for a walk. It helps me unwind.",
        "podcast_text": "A: What do you do after work?\nB: I go for a walk. It helps me unwind.",
    })
    path = library.item_path(topic["id"], created["id"])
    (path / "audio_podcast.mp3").write_bytes(b"audio")
    assert library.read_item_texts(path)["original_answer"] == ""
    return topic["id"], created["id"], path


def test_legacy_chinese_answer_unlocks_material_chain(legacy_item):
    """旧语料的 chinese 原话按回退语义生效：不再卡在「缺少原始回答」。"""
    tid, iid, path = legacy_item
    found = study.get_material(tid, iid)
    assert found["status"] == "needs_input"
    assert "缺少原始回答" not in found["reason"]
    full = library.get_item_full(tid, iid)
    assert full["original_answer"] == ""
    assert full["original_answer_effective"] == "我下班去散步。这让我放松。"

    clean = material()
    clean["sentences"][1].pop("original_error")  # 中文原话没有英文证据
    saved = study.save_material(tid, iid, clean)
    assert saved["sentences"][0]["en"] == "I go for a walk."
    assert study.get_material(tid, iid)["status"] == "ready"


def test_legacy_generate_material_sends_chinese_original(legacy_item, monkeypatch):
    """API 准备的模型输入使用回退后的原话，而不是空字符串。"""
    tid, iid, _ = legacy_item
    captured = {}

    def fake_chat(settings, messages, cancel):
        captured["original"] = json.loads(messages[1]["content"])["original_answer"]
        clean = material()
        clean["sentences"][1].pop("original_error")
        return json.dumps(clean, ensure_ascii=False)

    monkeypatch.setattr(study.rewrite, "_chat", fake_chat)
    monkeypatch.setattr(study, "load_settings", lambda: {"dry_run": False})
    study.generate_material(tid, iid)
    assert captured["original"] == "我下班去散步。这让我放松。"


def test_malformed_material_reports_failure_instead_of_crashing(item):
    tid, iid, path = item
    (path / "study_material.json").write_text("[]", encoding="utf-8")
    assert study.get_material(tid, iid)["status"] == "failed"
    (path / "study_material.json").write_text('{"version": 999}', encoding="utf-8")
    assert study.get_material(tid, iid)["status"] == "failed"


def test_audio_position_uses_only_verified_alignment(item, monkeypatch):
    tid, iid, _ = item
    study.save_material(tid, iid, material())
    monkeypatch.setattr(study.timeline, "get_or_create_timeline", lambda *a: {
        "mode": "estimated", "lines": [{"speaker": "B", "text": "I go for a walk.",
                                        "start": 2, "end": 4}]})
    assert study.sentence_audio(tid, iid, 0)["scope"] == "full_answer"
    monkeypatch.setattr(study.timeline, "get_or_create_timeline", lambda *a: {
        "mode": "sse", "lines": [{"speaker": "B", "text": "I go for a walk.",
                                  "start": 2, "end": 4}]})
    assert study.sentence_audio(tid, iid, 0)["scope"] == "sentence"


def test_voice_rebuild_keeps_material_when_text_unchanged(item):
    tid, iid, path = item
    study.save_material(tid, iid, material())
    (path / "audio_podcast.mp3").write_bytes(b"new-audio-version")
    assert study.get_material(tid, iid)["status"] == "ready"
    assert study.sentence_audio(tid, iid, 0)["scope"] == "full_answer"
