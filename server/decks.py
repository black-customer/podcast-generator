"""公开与个人口语词书、共享复习日程和本机示范缓存。"""

import hashlib
import json
import re
import threading
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

from . import (
    audio,
    audioqa,
    captures,
    library,
    mastering,
    oral_review,
    speech_bridge,
    study,
    study_progress,
    tts,
)
from .config import DATA_DIR, TMP_DIR, atomic_replace, is_dry_run, load_settings
from .speech_worker import matched_chunks, tokens

DECKS_DIR = DATA_DIR / "spoken_decks"
PERSONAL_ID = "my-speaking"
DAILY_NEW_DEFAULT = 5
CATEGORIES = {"core": "通用口语", "daily": "日常生活与社交", "ielts": "雅思口语专项",
              "personal": "个人词书"}
_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_BAN = {"raining cats and dogs", "every coin has two sides", "aforementioned", "hereinafter"}
_AUDIO_LOCK = threading.Lock()
_WARM_LOCK = threading.Lock()
_warm_thread: threading.Thread | None = None
_warm_rows: list[dict] = []


def _text(row: dict, key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"词书缺少 {key}")
    return value.strip()


def _identifier(row: dict) -> str:
    value = _text(row, "id")
    if not _ID.fullmatch(value):
        raise ValueError("词书、单元或卡片编号无效")
    return value


@lru_cache(maxsize=4)
def _public_catalog(files: tuple) -> dict:
    result, all_cards, phrases = {}, set(), set()
    for path, _, _ in files:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or raw.get("version") != 1:
                raise ValueError("词书版本不受支持")
            book_id = _identifier(raw)
            if book_id != path.stem or raw.get("category") not in ("core", "daily", "ielts"):
                raise ValueError("词书文件名或分类无效")
            book = {key: _text(raw, key) for key in (
                "id", "category", "title", "level_from", "level_to", "goal", "basis")}
            units = raw.get("units")
            if not isinstance(units, list) or not units:
                raise ValueError("词书需要至少一个单元")
            book["units"] = []
            unit_ids = set()
            for unit in units:
                unit_id = _identifier(unit)
                entries = unit.get("cards")
                if unit_id in unit_ids or not isinstance(entries, list) or len(entries) != 20:
                    raise ValueError("单元编号不可重复，每单元必须包含 20 张卡")
                unit_ids.add(unit_id)
                cards = []
                for entry in entries:
                    card_id = _identifier(entry)
                    row = captures.validate_card_payload({**entry, "status": "active"})
                    phrase = " ".join(tokens(row["target_chunk"]))
                    if (card_id in all_cards or phrase in phrases or phrase in _BAN
                            or not 2 <= len(tokens(phrase)) <= 12
                            or not matched_chunks(row["transfer_example_en"], [row["target_chunk"]])
                            or not row["disambiguator"]
                            or _text(entry, "cloze_prompt") != row["cloze_prompt"]):
                        raise ValueError(f"卡片 {card_id} 重复，或挖空 / 迁移示范无效")
                    all_cards.add(card_id)
                    phrases.add(phrase)
                    identity = f"deck:{book_id}:{card_id}"
                    cards.append({**row, "id": identity, "card_id": card_id, "deck_id": book_id,
                                  "deck_title": book["title"], "unit_id": unit_id})
                book["units"].append({"id": unit_id, "title": _text(unit, "title"),
                                      "goal": _text(unit, "goal"), "cards": cards})
            result[book_id] = book
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(f"{path.name} · {exc}") from exc
    return result


def public_catalog() -> dict:
    files = []
    for path in sorted(DECKS_DIR.glob("*.json")):
        stat = path.stat()
        files.append((path, stat.st_mtime_ns, stat.st_size))
    return _public_catalog(tuple(files))


def _personal_book() -> dict:
    title = "我的真实口语本"
    book = {"id": PERSONAL_ID, "category": "personal", "title": title, "level_from": "我的回答",
            "level_to": "独立复用", "goal": "从自己说过的内容中提取语块，换一个情境也能开口。",
            "basis": "本机真实回答与原有示范", "units": []}
    cards = []
    for key, patch in study.legacy_upgrades().items():
        tid, iid = key.split("/", 1)
        try:
            found = study.get_material(tid, iid)
        except (OSError, ValueError):
            continue
        material = found.get("material", {})
        fp = material.get("source_fingerprint")
        if found["status"] != "ready" or fp != patch["fingerprint"]:
            continue
        rows = material["sentences"]
        for index in map(int, patch["sentences"]):
            if index >= len(rows) or not rows[index].get("key_chunk"):
                continue
            row = rows[index]
            identity = oral_review._card_id(tid, iid, index, fp)
            cards.append({**row, "id": identity, "card_id": identity, "deck_id": PERSONAL_ID,
                          "deck_title": title, "topic_id": tid, "item_id": iid,
                          "sentence_index": index, "source_fingerprint": fp,
                          "target_chunk": row["key_chunk"], "chunk_in_sentence": row["key_chunk"],
                          "transfer_example_en": row.get("transfer_example", ""),
                          "usage_boundary": row["usage"],
                          "cloze_prompt": captures.make_cloze(row["en"], row["key_chunk"])})
    for offset in range(0, len(cards), 20):
        seq = offset // 20 + 1
        unit_id = f"unit-{seq}"
        book["units"].append({"id": unit_id, "title": f"第 {seq} 单元",
                              "goal": "先听原句，再在新场景使用表达。",
                              "cards": [{**row, "unit_id": unit_id}
                                        for row in cards[offset:offset + 20]]})
    return book


def _books(deck_id: str | None = None, *, personal: bool = True) -> dict:
    books = public_catalog()
    if deck_id is not None:
        if deck_id == PERSONAL_ID:
            return {PERSONAL_ID: _personal_book()}
        if deck_id not in books:
            raise FileNotFoundError("词书不存在")
        return {deck_id: books[deck_id]}
    return {**books, PERSONAL_ID: _personal_book()} if personal else books


def get_card(deck_id: str, card_id: str) -> dict:
    book = _books(deck_id)[deck_id]
    for unit in book["units"]:
        for row in unit["cards"]:
            if row["card_id"] == card_id:
                return row
    raise FileNotFoundError("词书卡片不存在")


def _fingerprint(row: dict) -> str:
    return row.get("source_fingerprint") or row["content_fingerprint"]


def _schedule(state: dict, row: dict) -> dict:
    old = state["cards"].get(row["id"], {})
    return old if old.get("source_fingerprint") == _fingerprint(row) else {}


def _progress(rows: list[dict], state: dict) -> dict:
    counts = dict(unseen=0, learning=0, mastered=0)
    for row in rows:
        stage = oral_review.mastery_stage(_schedule(state, row))
        counts[stage if stage in counts else "learning"] += 1
    return counts


def _active_units(book: dict, state: dict) -> list[dict]:
    units = book["units"]
    selected = state.get("active_unit", {}).get(book["id"])
    if selected:
        match = [unit for unit in units if unit["id"] == selected]
        if match:
            return match
    return next(([unit] for unit in units
                 if _progress(unit["cards"], state)["unseen"]), units[-1:])


def shelf() -> dict:
    books = _books()
    with oral_review._LOCK:
        state = oral_review._load()
    result = []
    for book in books.values():
        units = [{**{k: v for k, v in unit.items() if k != "cards"},
                  "progress": _progress(unit["cards"], state)} for unit in book["units"]]
        active = _active_units(book, state)
        result.append({**book, "units": units,
                       "enabled": book["id"] in state.get("enabled_decks", []),
                       "active_unit": active[0]["id"] if active else None,
                       "progress": {key: sum(unit["progress"][key] for unit in units)
                                    for key in ("unseen", "learning", "mastered")}})
    return {"categories": CATEGORIES.copy(), "decks": result,
            "daily_new_deck_cards": state.get("daily_new_deck_cards", DAILY_NEW_DEFAULT)}


def toggle(deck_id: str, enabled: bool, unit_id: str | None = None) -> dict:
    book = _books(deck_id)[deck_id]
    if unit_id and unit_id not in {unit["id"] for unit in book["units"]}:
        raise ValueError("单元不存在")
    with oral_review._LOCK:
        state = oral_review._load()
        active = state.setdefault("enabled_decks", [])
        if enabled and deck_id not in active:
            active.append(deck_id)
        if not enabled and deck_id in active:
            active.remove(deck_id)
        units = state.setdefault("active_unit", {})
        if unit_id is not None:
            units[deck_id] = unit_id
        elif enabled:
            units.pop(deck_id, None)
        state.setdefault("daily_new_deck_cards", DAILY_NEW_DEFAULT)
        oral_review._write(state)
    return {"id": deck_id, "enabled": enabled, "active_unit": units.get(deck_id)}


def _quota(state: dict, today: str) -> int:
    used = sum(row.get("deck_first_review") == today for row in state["cards"].values())
    return max(0, state.get("daily_new_deck_cards", DAILY_NEW_DEFAULT) - used)


def _practice(row: dict, schedule: dict, today: str) -> dict:
    stage = oral_review.mastery_stage(schedule)
    transfer_ready = oral_review.deck_transfer_ready(schedule, today)
    first_success = schedule.get("first_deck_success")
    base = f"/api/decks/{row['deck_id']}/cards/{row['card_id']}"
    return {**row, "card_kind": "deck", "source_type": "deck", "question": row["deck_title"],
            "source": row["deck_title"], "source_fingerprint": _fingerprint(row),
            "key_chunk": row["chunk_in_sentence"], "mastery_stage": stage,
            "transfer_ready": transfer_ready,
            "scaffolding_level": 3 if transfer_ready else 2
            if first_success and first_success < today else 1,
            "created_at": schedule.get("created_at", today),
            "due_date": schedule.get("due_date", today),
            "stability": schedule.get("stability"), "voice": None,
            "deck_url": base, "audio_url": f"{base}/audio",
            "audio": {"scope": "sentence", "start": 0, "end": None}}


def practice_rows(deck_id: str | None, *, unit_id: str | None = None, warmup: bool = False,
                  include_pending: bool = True, enrolled: set[str] | None = None) -> list[dict]:
    with oral_review._LOCK:
        state = oral_review._load()
    enabled = state.get("enabled_decks", [])
    if not warmup and not deck_id and not enabled:
        return []
    today = oral_review._today().isoformat()
    due, fresh, listened = [], [], []
    for book in _books(deck_id, personal=PERSONAL_ID in enabled).values():
        if not warmup and book["id"] not in enabled:
            continue
        selected = {unit["id"] for unit in _active_units(book, state)}
        if unit_id and not any(unit["id"] == unit_id for unit in book["units"]):
            raise FileNotFoundError("词书单元不存在")
        for unit in book["units"]:
            if unit_id and unit_id != unit["id"]:
                continue
            for row in unit["cards"]:
                if enrolled is not None:
                    enrolled.add(row["id"])
                card = _schedule(state, row)
                if card.get("paused"):
                    continue
                if warmup:
                    listened.append(_practice(row, card, today))
                elif card and card.get("last_adjusted_date") and (
                    card["due_date"] <= today or oral_review.deck_transfer_ready(card, today)
                ):
                    due.append(_practice(row, card, today))
                elif (include_pending and not card.get("last_adjusted_date")
                      and (unit_id or unit["id"] in selected)):
                    fresh.append(_practice(row, card, today))
    if warmup:
        return listened
    return due + fresh[:_quota(state, today)]


def grade(deck_id: str, card_id: str, fingerprint: str, rating: str, submission_id: str,
          transfer: bool) -> dict:
    if rating not in {"good", "again", "easy", "suspend"} or not 0 < len(submission_id) <= 100:
        raise ValueError("请选择有效的复习结果")
    with oral_review._LOCK:
        row = get_card(deck_id, card_id)
        if fingerprint != _fingerprint(row):
            raise ValueError("词书卡已更新，请刷新")
        state = oral_review._load()
        receipt = f"deck:{row['id']}:{submission_id}"
        if receipt in state["receipts"]:
            return state["receipts"][receipt]
        if deck_id not in state.get("enabled_decks", []):
            raise ValueError("请先启用词书")
        day = oral_review._today()
        today = day.isoformat()
        old = _schedule(state, row)
        if old.get("paused"):
            raise ValueError("这张卡已暂停")
        adjusted = not transfer and rating != "suspend" and old.get("last_adjusted_date") != today
        if transfer and (rating not in {"good", "again"}
                         or not oral_review.deck_transfer_ready(old, today)):
            raise ValueError("完成跨天提取后才能提交迁移练习")
        if adjusted and old.get("last_adjusted_date") and old["due_date"] > today:
            raise ValueError("这张卡还未到复习日期")
        if adjusted and not old.get("last_adjusted_date") and not _quota(state, today):
            raise ValueError("今天的新卡额度已用完")
        schedule = {**old, "id": row["id"], "deck_id": deck_id,
                    "card_kind": "ielts" if deck_id == PERSONAL_ID else "deck",
                    "source_type": "deck", "topic_id": row.get("topic_id", ""),
                    "item_id": row.get("item_id", ""),
                    "sentence_index": row.get("sentence_index", 0),
                    "question": old.get("question", row["deck_title"]),
                    "source": old.get("source", row["deck_title"]),
                    "source_fingerprint": fingerprint, "en": row["en"], "zh": row["zh"],
                    "created_at": old.get("created_at", oral_review._now_iso()),
                    "due_date": old.get("due_date", today), "paused": rating == "suspend",
                    "last_adjusted_date": old.get("last_adjusted_date"),
                    "level": old.get("level", 0),
                    "learned_at": old.get("learned_at"), "superseded": False}
        if adjusted:
            if not old.get("last_adjusted_date"):
                schedule["deck_first_review"] = today
            schedule.update(oral_review.fsrs_review(schedule, rating, day), last_fsrs_grade=rating)
            if rating == "again":
                for key in ("first_deck_success", "delayed_recall", "transfer_passed",
                            "transfer_deferred_date"):
                    schedule.pop(key, None)
            elif first := old.get("first_deck_success"):
                if first < today:
                    schedule["delayed_recall"] = today
            else:
                schedule["first_deck_success"] = today
        if transfer:
            key = "transfer_passed" if rating == "good" else "transfer_deferred_date"
            schedule[key] = today
        view = _practice(row, schedule, today)
        state["cards"][row["id"]] = schedule
        result = {"card_id": row["id"], "card_kind": "deck", "deck_id": deck_id,
                  "topic_id": schedule["topic_id"], "item_id": schedule["item_id"],
                  "sentence_index": schedule["sentence_index"],
                  "key_chunk": row["chunk_in_sentence"],
                  "en": row["en"], "zh": row["zh"], "question": row["deck_title"],
                  "rating": "unable" if rating == "again" else "independent", "fsrs_grade": rating,
                  "schedule_adjusted": adjusted, "next_due_date": schedule["due_date"],
                  "mastery_stage": view["mastery_stage"], "transfer_ready": view["transfer_ready"],
                  "scaffolding_level": view["scaffolding_level"],
                  "submitted_at": oral_review._now_iso(), "date": today, "recording_id": None,
                  "spoken_self_report": True, "recorded": False, "hint_used": False,
                  "session_id": "arcade", "submission_id": submission_id}
        if adjusted or transfer:
            state["attempts"].append(result)
        state["receipts"][receipt] = result
        oral_review._write(state)
        return result


def audio_file(row: dict, voice: str | None = None, *, transfer: bool = False) -> Path:
    if row["deck_id"] == PERSONAL_ID and not voice and not transfer:
        source = library.item_path(row["topic_id"], row["item_id"])
        original = library.resolve_audio_file(source, "podcast")
        if original is None:
            raise FileNotFoundError("原回答音频不可用")
        return original
    settings = load_settings()
    explicit = voice
    voice = voice or settings.get("kokoro_answer_voice") or "am_puck"
    text = row["transfer_example_en"] if transfer else row["en"]
    if not text:
        raise FileNotFoundError("示范未就绪")
    profile = None
    if voice == "golden_self" and not is_dry_run(settings):
        result = speech_bridge.request(settings, "profile_revision", timeout=15)
        profile = result.get("profile_hash")
        if not profile and explicit:
            raise ValueError("尚未配置母语分身")
        if not profile:
            voice = "am_puck"
    settings["kokoro_answer_voice"] = voice
    root = study_progress.PRIVATE_DIR / "deck_audio" / row["deck_id"]
    suffix = ("-transfer" if transfer else "") + (f"-{explicit}" if explicit else "")
    name = f"{row['card_id']}{suffix}"
    path = root / f"{name}.mp3"
    key_path = root / f"{name}.key"
    dry_run = is_dry_run(settings)
    audio_source = ["v2", text, voice, profile, settings.get("speech_engine_dir"), dry_run]
    key = hashlib.sha256(json.dumps(audio_source, ensure_ascii=False).encode()).hexdigest()
    with _AUDIO_LOCK:
        if path.is_file() and key_path.is_file() and key_path.read_text(encoding="ascii") == key:
            return path
        root.mkdir(parents=True, exist_ok=True)
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="deck-", dir=TMP_DIR) as directory:
            wav = Path(directory) / "sample.wav"
            staged = Path(directory) / "sample.mp3"
            if dry_run:
                audio.make_tone(tts.estimate_seconds(text), wav)
            else:
                speech_bridge.request(settings, "preview_line", text=text, voice=voice, output=wav,
                                      profile_hash=profile)
            duration = mastering.apply_mastering(wav, staged, is_dialogue=False)
            report = audioqa.run_qa(staged, text, duration_sec=duration, skip_vad=dry_run)
            if report["verdict"] == "retry":
                raise tts.TTSError("词书示范音频未通过质量检查，请重试")
            staged_key = Path(directory) / "sample.key"
            staged_key.write_text(key, encoding="ascii")
            key_path.unlink(missing_ok=True)
            atomic_replace(staged, path)
            atomic_replace(staged_key, key_path)
    return path


def prewarm(rows: list[dict]) -> None:
    global _warm_thread
    if not rows or is_dry_run(load_settings()):
        return
    with _WARM_LOCK:
        _warm_rows[:] = rows[:6]
        if _warm_thread is not None:
            return

        def warm() -> None:
            global _warm_thread
            while True:
                with _WARM_LOCK:
                    if not _warm_rows:
                        _warm_thread = None
                        return
                    row = _warm_rows.pop(0)
                try:
                    audio_file(row)
                except (OSError, ValueError, RuntimeError):
                    continue

        _warm_thread = threading.Thread(target=warm, name="deck-audio", daemon=True)
        _warm_thread.start()
