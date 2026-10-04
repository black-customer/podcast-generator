"""Agent 个人交换文件先校验再输出；测试只读写临时合成语料。"""
import hashlib
import json

import pytest


def sample():
    messages = [{"id": "m1", "role": "user", "text": "How do I say dietary fiber?"}]
    fingerprint = hashlib.sha256(json.dumps(
        messages, ensure_ascii=False, separators=(",", ":")
    ).encode()).hexdigest()
    cid = fingerprint[:24]
    return cid, {"version": 1, "type": "personal_learning_exchange", "topics": {},
                 "conversations": {cid: {"id": cid, "title": "Synthetic", "messages": messages,
                                         "source_fingerprint": fingerprint, "dialogue": [],
                                         "notes": []}}}


def result():
    return {"dialogue": [{"speaker": "A", "en": "What would you like to say?", "zh": "想说什么？"},
                         {"speaker": "B", "en": "Mushrooms have dietary fiber.",
                          "zh": "蘑菇含纤维。"}],
            "notes": [{"kind": "explicit_gap", "target": "dietary fiber", "prompt_zh": "说说蘑菇。",
                       "reference_en": "Mushrooms have dietary fiber.", "explanation": "搭配",
                       "sources": [{"message_id": "m1", "quote": "dietary fiber"}]}]}


def test_exchange_complete_preserves_source_and_rejects_invented_evidence():
    from server import conversation_exchange as exchange

    cid, original = sample()
    updated = exchange.complete(original, cid, result())
    assert updated["conversations"][cid]["messages"] == original["conversations"][cid]["messages"]
    assert original["conversations"][cid]["dialogue"] == []
    assert updated["conversations"][cid]["status"] == "text_ready"
    bad = result()
    bad["notes"][0]["sources"][0]["quote"] = "invented"
    with pytest.raises(ValueError):
        exchange.complete(original, cid, bad)


def test_exchange_rejects_changed_source_and_unknown_version():
    from server import conversation_exchange as exchange

    cid, original = sample()
    original["conversations"][cid]["messages"][0]["text"] = "changed"
    with pytest.raises(ValueError):
        exchange.complete(original, cid, result())
    with pytest.raises(ValueError):
        exchange.complete({**original, "version": 99}, cid, result())


def test_ielts_exchange_preserves_original_and_checks_spoken_lines():
    from server import conversation_exchange as exchange

    _, original = sample()
    original["topics"] = {"t": {"id": "t", "name": "Synthetic", "items": {
        "i": {"id": "i", "texts": {"question": "Food?", "original_answer": "Rice."}}}}}
    generated = {"natural_english": "I like rice.", "podcast_text": "A: Food?\nB: I like rice.",
                 "podcast_script": "A: Food?\nB: I like rice.", "dialogue": [
                     {"speaker": "A", "en": "Food?", "zh": "饮食？"},
                     {"speaker": "B", "en": "I like rice.", "zh": "我喜欢米饭。"}]}
    output = exchange.complete_ielts(original, "t", "i", generated)
    assert output["topics"]["t"]["items"]["i"]["texts"]["original_answer"] == "Rice."
    assert original["topics"]["t"]["items"]["i"]["texts"].get("podcast_text") is None
    with pytest.raises(ValueError):
        exchange.complete_ielts(original, "t", "i", {**generated, "dialogue": []})
