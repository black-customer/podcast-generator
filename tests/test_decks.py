"""词书放量、真实掌握、便携边界与旧材料迁移回归。"""

import json
from datetime import date, timedelta

import pytest

from server import arcade, decks, oral_review, study, teaching_podcast


def test_builtin_decks_have_220_unique_cards():
    books = decks.public_catalog()
    assert {book["category"] for book in books.values()} == {"core", "daily", "ielts"}
    assert sorted(len(book["units"]) for book in books.values()) == [3, 3, 5]
    assert sum(len(unit["cards"]) for book in books.values() for unit in book["units"]) == 220


@pytest.fixture
def review(tmp_path, monkeypatch):
    path = tmp_path / "review.json"
    monkeypatch.setattr(oral_review, "REVIEW_FILE", path)
    monkeypatch.setattr(study, "LEGACY_UPGRADE_FILE", tmp_path / "upgrades.json")
    monkeypatch.setattr(decks, "DAILY_NEW_DEFAULT", 2)
    day = date(2026, 11, 28)
    monkeypatch.setattr(oral_review, "_today", lambda: day)
    return path, lambda next_day: monkeypatch.setattr(oral_review, "_today", lambda: next_day), day


def test_shared_daily_quota_and_listening_are_read_only(review):
    path, advance, day = review
    first, second, *_ = decks.public_catalog()
    assert arcade.home_cards(source="deck")["cards"] == []
    decks.toggle(first, True)
    decks.toggle(second, True)
    before = path.read_bytes()
    sample = arcade.home_cards(source="deck", deck_id=first, warmup=True)["cards"]
    assert len(sample) == 8
    assert path.read_bytes() == before
    a = arcade.home_cards(source="deck", deck_id=first)["cards"]
    b = arcade.home_cards(source="deck", deck_id=second)["cards"]
    assert len(a) == len(b) == 2
    selected = arcade.home_cards(deck_id=first, unit_id="connect")["cards"]
    assert len(selected) == 2 and all(row["unit_id"] == "connect" for row in selected)
    for index, row in enumerate(a):
        decks.grade(first, row["card_id"], row["source_fingerprint"], "good", str(index), False)
    assert arcade.home_cards(source="deck", deck_id=second)["cards"] == []
    with pytest.raises(ValueError, match="新卡"):
        decks.grade(second, b[0]["card_id"], b[0]["source_fingerprint"], "good", "b", False)
    advance(day + timedelta(days=1))
    assert len(arcade.home_cards(source="deck", deck_id=second)["cards"]) == 2


def test_mastery_requires_delayed_recall_and_transfer(review, monkeypatch):
    path, advance, day = review
    book = next(iter(decks.public_catalog()))
    decks.toggle(book, True)
    row = arcade.home_cards(source="deck", deck_id=book)["cards"][0]
    card, fp = row["card_id"], row["source_fingerprint"]
    assert row["mastery_stage"] == "unseen"
    with pytest.raises(ValueError, match="迁移"):
        decks.grade(book, card, fp, "easy", "forged", True)
    result = decks.grade(book, card, fp, "easy", "first", False)
    assert decks.grade(book, card, fp, "easy", "first", False) == result
    assert result["mastery_stage"] == "l1"
    due = date.fromisoformat(result["next_due_date"])
    advance(due)
    with pytest.raises(ValueError, match="迁移"):
        decks.grade(book, card, fp, "good", "early", True)
    delayed = decks.grade(book, card, fp, "good", "delayed", False)
    assert delayed["mastery_stage"] == "l2"
    assert delayed["transfer_ready"]
    done = decks.grade(book, card, fp, "good", "transfer", True)
    assert done["mastery_stage"] == "mastered"
    assert not done["schedule_adjusted"]
    assert done["next_due_date"] == delayed["next_due_date"]
    assert list(json.loads(path.read_bytes())["cards"]) == [row["id"]]
    assert decks.shelf()["decks"][0]["progress"]["mastered"] == 1
    monkeypatch.setattr(teaching_podcast, "generate", lambda q, points, *a, **kw: points)
    points = teaching_podcast.for_today("english", "am_puck")
    assert any(point.get("key_chunk") == row["key_chunk"] for point in points)


def test_legacy_upgrade_validates_whole_batch_and_keeps_existing_audio(tmp_path, monkeypatch):
    from server import library

    monkeypatch.setattr(library, "TOPICS_DIR", tmp_path / "topics")
    monkeypatch.setattr(study, "LEGACY_UPGRADE_FILE", tmp_path / "private" / "upgrades.json")
    item = library.TOPICS_DIR / "topic" / "items" / "item"
    item.mkdir(parents=True)
    en = "I set aside time for walks."
    texts = {"original_answer": "我留时间散步。", "podcast_text": f"A: Why?\nB: {en}"}
    monkeypatch.setattr(library, "read_item_texts", lambda path: texts)
    monkeypatch.setattr(library, "load_meta", lambda path: {"tags": ["bruce-真实回答"]})
    audio = item / "audio_podcast.mp3"
    audio.write_bytes(b"existing audio")
    alignment = item / "alignment.json"
    alignment.write_bytes(b"existing alignment")
    monkeypatch.setattr(library, "resolve_audio_file", lambda *args: audio)
    original = study.validate_material({"complete_chinese": "我留时间散步。", "sentences": [
        {"en": en, "zh": "我专门留时间散步。", "explanation": "固定搭配", "usage": "留出时间"}]},
        texts)
    file = item / study.MATERIAL_FILE
    file.write_text(json.dumps(original), encoding="utf-8")
    exported = study.export_legacy_study_upgrade()["items"][0]
    patch = {key: exported[key] for key in ("topic_id", "item_id", "source_fingerprint")}
    patch["sentences"] = [{"sentence_index": 0, "key_chunk": "set aside time",
        "trigger_context": "周末特意留时间散步。", "disambiguator": "主动腾出时间。",
        "feynman_hook": "把一段时间先留给这件事。", "transfer_prompt_zh": "留时间复习。",
        "transfer_example": "I set aside time to review my notes."}]
    with pytest.raises(ValueError):
        study.apply_legacy_study_upgrade({"version": 1, "items": [patch, patch]})
    assert not study.LEGACY_UPGRADE_FILE.exists()
    assert study.apply_legacy_study_upgrade({"version": 1, "items": [patch]})["sentences"] == 1
    upgraded = study.get_material("topic", "item")["material"]
    assert upgraded["source_fingerprint"] == original["source_fingerprint"]
    assert upgraded["sentences"][0]["key_chunk"] == "set aside time"
    assert json.loads(file.read_bytes()) == original
    assert audio.read_bytes() == b"existing audio"
    assert alignment.read_bytes() == b"existing alignment"


def test_deck_audio_cache_keeps_text_and_voice_variants_separate(tmp_path, monkeypatch):
    monkeypatch.setattr(decks.study_progress, "PRIVATE_DIR", tmp_path)
    monkeypatch.setattr(decks, "TMP_DIR", tmp_path)
    monkeypatch.setattr(decks, "load_settings", lambda: {"dry_run": True})
    monkeypatch.setattr(decks.audioqa, "run_qa", lambda *a, **k: {"verdict": "pass"})
    calls = []

    def prepare(duration, path):
        calls.append(duration)
        path.write_bytes(b"audio")

    def master(wav, mp3, **kwargs):
        mp3.write_bytes(wav.read_bytes())
        return 1.5

    monkeypatch.setattr(decks.audio, "make_tone", prepare)
    monkeypatch.setattr(decks.mastering, "apply_mastering", master)
    row = decks.get_card("conversation-engine", "give-me-a-second")
    default = decks.audio_file(row)
    assert decks.audio_file(row) == default
    transfer = decks.audio_file(row, "af_bella", transfer=True)
    assert default != transfer and transfer.is_file()
    decks.audio_file({**row, "en": "Could you give me a second while I get my keys?"})
    assert len(calls) == 3 and default.is_file()


def test_personal_deck_reuses_original_even_without_sentence_span(monkeypatch):
    row = {"card_kind": "deck", "deck_id": decks.PERSONAL_ID, "topic_id": "topic",
           "item_id": "item", "sentence_index": 0}
    monkeypatch.setattr(arcade, "view", lambda *_: {
        "audio_url": "/original.mp3", "voice": None,
        "sentences": [{"audio": {"scope": "full_answer", "start": 0, "end": None}, "prosody": {}}],
        "answer_spans": [{"start": 2, "end": 14}],
    })
    card = arcade._practice_row(row, {})
    assert card["audio_url"] == "/original.mp3"
    assert card["audio"] == {"scope": "full_answer", "start": 2, "end": 14}
