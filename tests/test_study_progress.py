"""L03 私有进度、复习事实及录音版本回归。"""
import json
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server import library, study, study_progress


@pytest.fixture()
def item(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "TOPICS_DIR", tmp_path / "topics")
    monkeypatch.setattr(study_progress, "PRIVATE_DIR", tmp_path / "study_private")
    (tmp_path / "topics").mkdir()
    t = library.create_topic("T")
    i = library.create_item(t["id"], {"question": "What do you do?"})
    return t["id"], i["id"], tmp_path


def test_progress_roundtrip_and_atomic_write(item):
    tid, iid, tmp = item
    assert study_progress.get_progress(tid, iid)["before_started"] is False
    saved = study_progress.save_progress(tid, iid, {
        "stage": "dictation", "sentence_index": 2, "before_started": True,
        "draft": ["I", "would", "go"],
        "facts": {"1": {"hint_used": True, "wrong_attempts": 2, "favorite": True}},
    })
    assert saved["stage"] == "dictation"
    assert study_progress.get_progress(tid, iid)["before_started"] is True
    assert study_progress.get_progress(tid, iid)["draft"] == ["I", "would", "go"]
    assert json.loads((tmp / "study_private" / tid / iid / "state.json").read_text(
        encoding="utf-8"
    ))["facts"]["1"]["hint_used"] is True
    assert not list((tmp / "study_private").rglob("*.tmp~"))


def test_recording_versions_are_kept(item):
    tid, iid, _ = item
    first = study_progress.save_recording(tid, iid, "before", b"first", 2.5, "audio/webm")
    second = study_progress.save_recording(tid, iid, "before", b"second", 3.5, "audio/webm")
    assert first["id"] != second["id"]
    assert first["question"] == "What do you do?"
    assert study_progress.read_recording(tid, iid, first["id"])[0] == b"first"
    assert len(study_progress.get_progress(tid, iid)["recordings"]) == 2
    assert all(r["stage"] == "before" for r in study_progress.get_progress(tid, iid)["recordings"])


def test_review_pool_contains_wrong_hint_and_favorite(item):
    tid, iid, _ = item
    library.update_item_texts(tid, iid, {
        "original_answer": "I walk. Then I rest. I listen. I sleep.",
        "podcast_text": "A: What do you do?\nB: I walk. Then I rest. I listen. I sleep.",
    })
    (library.item_path(tid, iid) / "audio_podcast.mp3").write_bytes(b"audio")
    study.save_material(tid, iid, {"complete_chinese": "我散步，然后休息、听东西、睡觉。",
        "sentences": [{"zh": f"句子{n}", "en": en, "explanation": "说明", "usage": "用法"}
                      for n, en in enumerate(("I walk.", "Then I rest.", "I listen.",
                                             "I sleep."))]})
    study_progress.save_progress(tid, iid, {"facts": {
        "0": {"wrong_attempts": 1},
        "1": {"hint_used": True},
        "2": {"favorite": True},
        "3": {"wrong_attempts": 0},
    }})
    assert [r["sentence_index"] for r in study_progress.review_items()] == [0, 1, 2]


def test_invalid_stage_does_not_write(item):
    tid, iid, tmp = item
    with pytest.raises(ValueError):
        study_progress.save_progress(tid, iid, {"stage": "unknown"})
    with pytest.raises(ValueError):
        study_progress.save_progress(tid, iid, {
            "facts": {"0": {"wrong_attempts": "not-a-number"}},
        })
    assert not (tmp / "study_private" / tid / iid / "state.json").exists()


def test_review_pool_skips_hand_edited_non_numeric_keys(item, monkeypatch):
    """手改坏的非数字事实键不应让 /api/study/review 500，其余句子照常返回。"""
    tid, iid, tmp = item
    library.update_item_texts(tid, iid, {
        "original_answer": "I walk. I rest.",
        "podcast_text": "A: What do you do?\nB: I walk. I rest.",
    })
    (library.item_path(tid, iid) / "audio_podcast.mp3").write_bytes(b"audio")
    study.save_material(tid, iid, {"complete_chinese": "我散步，然后休息。",
        "sentences": [{"zh": f"句{n}", "en": en, "explanation": "说明", "usage": "用法"}
                      for n, en in enumerate(("I walk.", "I rest."))]})
    study_progress.save_progress(tid, iid, {"facts": {"0": {"wrong_attempts": 1}}})
    state_file = tmp / "study_private" / tid / iid / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["facts"]["bad-key"] = {"wrong_attempts": 1}
    state_file.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    rows = study_progress.review_items()
    assert [r["sentence_index"] for r in rows] == [0]
