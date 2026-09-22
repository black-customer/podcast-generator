"""剂量校验器的测试。

这些测试是工作流的一部分，不是可选装饰：剂量上限就是这个工作流存在的理由，
一个不会失败的上限等于没有上限。跑法：
    .venv/Scripts/python -m pytest workflows/qoder-one-question/scripts/test_one_question.py -q
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from one_question.build import CAPS, validate  # noqa: E402

BASE = json.loads((Path(__file__).resolve().parents[1] / "lessons"
                   / "01-favourite-teacher" / "lesson.json").read_text(encoding="utf-8"))


def test_baseline_lesson_passes():
    assert validate(BASE) == []


def test_rejects_fourth_error_fix():
    bad = copy.deepcopy(BASE)
    bad["fixes"].append({
        "id": "extra", "label_zh": "多余", "original": "I'm an introvert person",
        "fixed": "I'm quite introverted.", "core": "I'm quite introverted.",
        "rule_zh": "测试", "prompt_zh": "我很内向。"})
    assert any(f"上限 {CAPS['fixes_max']}" in e for e in validate(bad))


def test_rejects_fourth_chunk():
    bad = copy.deepcopy(BASE)
    bad["chunks"] = bad["chunks"] + [{
        "chunk": "take notes", "zh": "记笔记", "wrong": "learn knowledge",
        "example": "I took the notes and left.", "usage_zh": "测试"}]
    assert any("语块" in e for e in validate(bad))


def test_rejects_beautified_original():
    """不许把用户的错误原话改好——那是 noticing 的燃料。"""
    bad = copy.deepcopy(BASE)
    bad["fixes"][0]["original"] = "I don't have a favourite teacher"
    assert any("不是用户原话" in e for e in validate(bad))


def test_rejects_chunk_absent_from_example():
    bad = copy.deepcopy(BASE)
    bad["chunks"][0]["example"] = "I had good teachers but none I'd single out."
    assert any("没有真的出现在它的 example 里" in e for e in validate(bad))


def test_rejects_model_answer_that_drops_a_chunk():
    bad = copy.deepcopy(BASE)
    bad["model_answer"] = [
        "I've had good teachers, but I was never close to any of them.",
        "They delivered the lesson and I took the notes.",
        "It was fine, it just wasn't memorable.",
        "So no, nothing really stands out there.",
        "I'd rather learn from people my own age.",
    ]
    errs = validate(bad)
    assert any("没有用上这些语块" in e for e in errs)


def test_rejects_overlong_model_answer():
    bad = copy.deepcopy(BASE)
    bad["model_answer"] = bad["model_answer"] + [
        "And that is the honest truth about my schooling experience in China."]
    assert any("词，要求" in e for e in validate(bad))


def test_rejects_fix_that_fixes_nothing():
    bad = copy.deepcopy(BASE)
    bad["fixes"][1]["fixed"] = "I don't have a deep relationship with my favorite teachers"
    assert any("没修" in e for e in validate(bad))


def test_missing_required_field_is_reported():
    bad = copy.deepcopy(BASE)
    del bad["scaffold_zh"]
    assert any("scaffold_zh" in e for e in validate(bad))
