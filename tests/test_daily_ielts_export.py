"""自媒体导出必须锚定原题、原音频，禁止把占位或旧稿当成成品。"""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from server.alignment import audio_signature, text_fingerprint

MODULE_PATH = Path(__file__).resolve().parents[1] / "workflows/daily-ielts/build.py"
spec = importlib.util.spec_from_file_location("daily_ielts_build", MODULE_PATH)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


@pytest.fixture
def source(tmp_path):
    question = "Do you enjoy walking?"
    answer = "Yes, I do. It helps me clear my head."
    transcript = f"A: {question}\nB: {answer}"
    lesson = {
        "question_id": "q_walk",
        "headline": "散步时，你在想什么？",
        "answer_origin": "原创示范",
        "sentences": [
            {"en": "Yes, I do.", "zh": "是的，我喜欢。"},
            {"en": "It helps me clear my head.", "zh": "散步能让我清醒一下。"},
        ],
        "chunks": [
            {"en": "clear my head", "zh": "让头脑清醒",
             "example": "A walk helps me clear my head."},
        ],
        "transfer_zh": "换成你的经历：你会怎样放松？",
    }
    bank = {
        "questions": [{"id": "q_walk", "text": question, "part": 1, "topic_id": "t_walk"}],
        "topics": [{"id": "t_walk", "name_en": "Walking"}],
        "sets": [],
    }
    (tmp_path / "question.txt").write_text(question, encoding="utf-8")
    (tmp_path / "podcast_text.txt").write_text(transcript, encoding="utf-8")
    (tmp_path / "audio_podcast.mp3").write_bytes(b"fixture audio")
    (tmp_path / "meta.json").write_text(json.dumps({"dry_run": False, "stale": False}))
    (tmp_path / "qa_podcast.json").write_text(json.dumps({"verdict": "pass"}))
    alignment = {
        "mode": "measured",
        "text_fingerprint": text_fingerprint(transcript),
        "audio_signature": audio_signature(tmp_path / "audio_podcast.mp3"),
    }
    (tmp_path / "alignment_podcast.json").write_text(json.dumps(alignment))
    return tmp_path, lesson, bank


def test_unverified_season_is_not_invented(source):
    item, lesson, bank = source
    result = exporter.validate_source(lesson, item, bank)
    assert result["season"] == "考季未核实"
    assert result["answer"] == "Yes, I do. It helps me clear my head."


def test_reject_question_not_matching_bank(source):
    item, lesson, bank = source
    bank = copy.deepcopy(bank)
    bank["questions"][0]["text"] = "Do you enjoy running?"
    with pytest.raises(ValueError, match="题干"):
        exporter.validate_source(lesson, item, bank)


def test_reject_rewritten_caption_over_old_audio(source):
    item, lesson, bank = source
    lesson["sentences"][1]["en"] = "It helps me sleep."
    with pytest.raises(ValueError, match="英文.*音频文稿"):
        exporter.validate_source(lesson, item, bank)


@pytest.mark.parametrize("flag", ["dry_run", "stale"])
def test_reject_placeholder_and_stale_audio(source, flag):
    item, lesson, bank = source
    (item / "meta.json").write_text(json.dumps({flag: True}))
    with pytest.raises(ValueError, match="占位|过期"):
        exporter.validate_source(lesson, item, bank)


def test_reject_changed_audio_signature(source):
    item, lesson, bank = source
    (item / "audio_podcast.mp3").write_bytes(b"changed audio with a different size")
    with pytest.raises(ValueError, match="音频签名"):
        exporter.validate_source(lesson, item, bank)


def test_reject_chunk_not_in_answer(source):
    item, lesson, bank = source
    lesson["chunks"][0]["en"] = "take a break"
    with pytest.raises(ValueError, match="重点表达"):
        exporter.validate_source(lesson, item, bank)


@pytest.mark.parametrize("origin", ["本人回答", "原创示范"])
def test_publish_copy_distinguishes_real_answer_and_authored_example(source, origin):
    item, lesson, bank = source
    lesson["answer_origin"] = origin
    validated = exporter.validate_source(lesson, item, bank)
    copy_text = exporter.publish_text(lesson, validated)
    if origin == "本人回答":
        assert "本人真实回答" in copy_text
        assert "示例经历并非本人经历" not in copy_text
    else:
        assert "示例经历并非本人经历" in copy_text
