"""桌面韵律标注与双人电台的材料、路由、保存回归。"""
import json
from datetime import date
from pathlib import Path

import pytest


def test_prosody_marks_boundaries_and_weak_forms():
    from server import prosody

    text = "Do you want to get it, or pick some water for lunch?"
    result = prosody.annotate_sentence(text)
    assert result["weak_words"]["3"] == "tə"
    assert result["weak_words"]["10"] == "fər"
    assert result["focus_words"] and result["nuclear_word"] == 11
    assert result["break_after"] == [5]
    assert result["intonation"] == "↗"
    assert {pair["type"] for pair in result["linking_pairs"]} >= {
        "held_stop", "flap_t", "reduction",
    }
    assert 9 in result["flap_t_words"]
    assert prosody.annotate_sentence("Why do you enjoy it?")["intonation"] == "↘"


def test_radio_drafts_from_original_context_and_splits_mixed_fallback(monkeypatch):
    from server import teaching_podcast as radio

    context = {"question": "How do you relax?", "original_answer": "It help me.",
               "chinese_intent": "我想说放松", "points": [{"key_chunk": "helps me unwind"}]}

    def chat(_settings, messages, _cancel):
        assert json.loads(messages[-1]["content"]) == context
        return json.dumps({"title": "下班后怎么放松", "highlights": ["helps me unwind"],
                           "turns": [{"speaker": "A", "text": "可以说 helps me unwind."},
                                     {"speaker": "B", "text": "我明白了。"}]})

    monkeypatch.setattr(radio.rewrite, "_chat", chat)
    episode = radio.draft_episode_with_llm(context, "bilingual", None)
    assert episode["highlights"] == ["helps me unwind"]
    assert episode["turns"][0]["segments"] == [
        {"lang": "zh", "text": "可以说"}, {"lang": "en", "text": "helps me unwind."},
    ]
    with pytest.raises(ValueError, match="全英文"):
        radio.draft_episode_with_llm(context, "en", None)


def test_teaching_script_requires_two_voices_with_target_and_no_silent_directions():
    from server import teaching_podcast as radio

    lines = [{"speaker": "A", "text": "Try saying sesame dressing."},
             {"speaker": "B", "text": "Hmm, I usually use sesame dressing."}]
    radio.validate_script(lines, ["sesame dressing"])
    assert {line["speaker"] for line in lines} == {"A", "B"}
    assert any("Hmm" in line["text"] for line in lines if line["speaker"] == "B")
    for bad in (lines[:1], [{"speaker": "A", "text": "Hello"},
                            {"speaker": "B", "text": "[3s silence] sesame dressing"}]):
        with pytest.raises(ValueError):
            radio.validate_script(bad, ["sesame dressing"])
    with pytest.raises(ValueError):
        radio.validate_script(lines, ["pick it up"])


def test_today_draws_gaps_from_practised_items_and_old_fsrs_cards(monkeypatch):
    from server import teaching_podcast as radio

    today = "2026-11-25"
    items = {
        ("topic", "today"): [
            {"en": "I read after work.", "key_chunk": "after work"},
            {"en": "It helps me unwind.", "key_chunk": "helps me unwind",
             "original_error": {"quote": "It help"}},
            {"en": "I use sesame dressing.", "key_chunk": "sesame dressing",
             "gap_kind": "explicit_gap"},
        ],
        ("topic", "old"): [{"en": "I take a short break.", "key_chunk": "take a short break"}],
    }
    attempt = {"topic_id": "topic", "item_id": "today", "sentence_index": 0, "date": today,
               "question": "What do you do after work?", "en": "I read after work."}
    old = {"topic_id": "topic", "item_id": "old", "sentence_index": 0, "id": "old",
           "paused": False, "due_date": today, "en": "I take a short break."}
    monkeypatch.setattr(radio.oral_review, "_load", lambda: {
        "attempts": [attempt], "cards": {"old": old},
    })
    monkeypatch.setattr(radio.oral_review, "_today", lambda: date.fromisoformat(today))
    monkeypatch.setattr(radio.arcade, "_fresh_ielts", lambda *_: [])
    monkeypatch.setattr(radio.captures, "list_cards", lambda **_: [])
    monkeypatch.setattr(radio, "_item_points", lambda *key: items[key])
    monkeypatch.setattr(radio.library, "get_item_full",
                        lambda *_: {"question": attempt["question"]})
    monkeypatch.setattr(radio.study_progress, "get_progress", lambda *_: {})
    monkeypatch.setattr(radio, "generate", lambda _, points, *args, **kwargs: points)
    assert [p["key_chunk"] for p in radio.for_today("en", "am_puck")] == [
        "helps me unwind", "sesame dressing", "take a short break",
    ]


@pytest.mark.parametrize(("mode", "voice", "expected"), [
    ("en", "am_puck", {"af_bella", "am_puck"}),
    ("en", "golden_self", {"af_bella", "golden_self"}),
    ("bilingual", "am_puck", {"af_bella", "am_puck", "zf_xiaoxiao", "zm_yunxi"}),
    ("bilingual", "golden_self", {"af_bella", "golden_self", "zf_xiaoxiao", "zm_yunxi"}),
])
def test_radio_uses_selected_voice_pair_and_persists_episode(monkeypatch, tmp_path, mode,
                                                            voice, expected):
    from server import teaching_podcast as radio

    used, progress = set(), []
    monkeypatch.setattr(radio, "EPISODE_DIR", tmp_path / "episodes")
    monkeypatch.setattr(radio, "TMP_DIR", tmp_path / "tmp")
    monkeypatch.setattr(radio, "load_settings", lambda: {})
    monkeypatch.setattr(radio, "draft_episode_with_llm", lambda context, mode, cancel:
                        radio._dry_script(context["question"], context["points"], mode, None))

    def local(_settings, method, **params):
        if method == "profile_revision":
            return {"profile_hash": "a"}
        assert method == "preview_line"
        used.add(params["voice"])
        assert params["lang"] == ("cmn" if params["voice"] in {"zf_xiaoxiao", "zm_yunxi"}
                                  else "en-us")
        Path(params["output"]).write_bytes(b"fake-wav")

    def render(_paths, target):
        target.write_bytes(b"final-mp3")
        return 67.0, [(i * 8.0, (i + 1) * 8.0) for i in range(len(_paths))]

    monkeypatch.setattr(radio.speech_bridge, "request", local)
    monkeypatch.setattr(radio, "_join_audio", render)
    point = {"en": "I use sesame dressing.", "zh": "我会用芝麻酱。", "key_chunk": "sesame dressing"}
    episode = radio.generate("What do you use?", [point], mode, voice,
                             on_progress=lambda *row: progress.append(row))
    assert progress[0][0] == "script" and progress[-1][0] == "master"
    assert progress[-2][1:3] == (len(episode["lines"]), len(episode["lines"]))
    assert "lines" not in radio.public_episode(episode)
    assert used == expected
    assert radio.get_episode(episode["id"]) == episode
    assert radio.audio_file(episode["id"]).read_bytes() == b"final-mp3"
    assert radio.list_episodes() == [episode]
    assert episode["lines"][0]["end"] > 0
    assert list(radio.TMP_DIR.iterdir()) == []
