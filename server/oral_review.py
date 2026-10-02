"""本机困难句口答日程：按材料版本绑定、跨天复习与可恢复轮次。"""

import hashlib
import json
import threading
import uuid
from datetime import date, datetime, timedelta

from . import library, study, study_progress
from .config import atomic_write_text

REVIEW_FILE = study_progress.PRIVATE_DIR / "oral_review.json"
INTERVAL_DAYS = (1, 3, 7, 14, 30)
_LOCK = threading.RLock()


def _today() -> date:
    return date.today()


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _load() -> dict:
    if not REVIEW_FILE.exists():
        return {"version": 1, "cards": {}, "sessions": {}, "attempts": [], "receipts": {}}
    data = json.loads(REVIEW_FILE.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("口答记录版本或格式不受支持，请先备份本机文件")
    return data


def _write(state: dict) -> None:
    atomic_write_text(REVIEW_FILE, json.dumps(state, ensure_ascii=False, indent=2))


def _card_id(topic_id: str, item_id: str, index: int, fingerprint: str) -> str:
    source = json.dumps([topic_id, item_id, index, fingerprint], ensure_ascii=False)
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def _material(topic_id: str, item_id: str, cache: dict | None = None) -> dict:
    key = (topic_id, item_id)
    if cache is not None and key in cache:
        value = cache[key]
        if isinstance(value, Exception):
            raise value
        return value
    try:
        found = study.get_material(topic_id, item_id)
    except (FileNotFoundError, ValueError, KeyError) as error:
        if cache is not None:
            cache[key] = error
        raise
    if cache is not None:
        cache[key] = found
    return found


def _source_info(topic_id: str, item_id: str) -> dict:
    with library.LIB_LOCK:
        path = library.item_path(topic_id, item_id)
        if not path.exists():
            raise FileNotFoundError("条目不存在")
        texts = library.read_item_texts(path)
        return {"question": texts["question"], "title": library.item_title(texts, path.name)}


def _valid(card: dict, cache: dict | None = None) -> bool:
    try:
        found = _material(card["topic_id"], card["item_id"], cache)
        rows = found.get("material", {}).get("sentences", [])
        index = card["sentence_index"]
        return (found["status"] == "ready"
                and found["material"]["source_fingerprint"] == card["source_fingerprint"]
                and 0 <= index < len(rows) and rows[index]["en"] == card["en"])
    except (FileNotFoundError, ValueError, KeyError):
        return False


def _make_card(topic_id: str, item_id: str, index: int, found: dict,
               learned_at: str | None, source: str) -> dict:
    material = found["material"]
    row = material["sentences"][index]
    full = _source_info(topic_id, item_id)
    fingerprint = material["source_fingerprint"]
    learned_date = learned_at[:10] if learned_at else _today().isoformat()
    due = (date.fromisoformat(learned_date) + timedelta(days=1)
           if learned_at else _today())
    return {
        "id": _card_id(topic_id, item_id, index, fingerprint),
        "topic_id": topic_id, "item_id": item_id, "sentence_index": index,
        "source_fingerprint": fingerprint, "zh": row["zh"], "en": row["en"],
        "question": full["question"], "source": full["title"],
        "created_at": _now_iso(), "learned_at": learned_at, "legacy": learned_at is None,
        "due_date": due.isoformat(), "level": 0, "last_adjusted_date": None,
        "paused": False, "superseded": False, "enrollment": source,
    }


def _supersede_older(state: dict, current: dict) -> None:
    for card in state["cards"].values():
        if card["id"] != current["id"] and all(card[key] == current[key] for key in (
            "topic_id", "item_id", "sentence_index"
        )):
            card["superseded"] = True
            card["paused"] = True


def _reconcile(state: dict, cache: dict | None = None) -> None:
    root = study_progress.PRIVATE_DIR
    if not root.exists():
        return
    for path in root.glob("*/*/state.json"):
        tid, iid = path.parent.parent.name, path.parent.name
        try:
            progress = study_progress.get_progress(tid, iid)
            found = _material(tid, iid, cache)
            if found["status"] != "ready":
                continue
            fingerprint = found["material"]["source_fingerprint"]
            for key, facts in progress.get("facts", {}).items():
                if not str(key).isdigit() or not isinstance(facts, dict):
                    continue
                index = int(key)
                if index >= len(found["material"]["sentences"]):
                    continue
                if not facts.get("passed") or not (
                    facts.get("wrong_attempts", 0) > 0 or facts.get("hint_used")
                    or facts.get("favorite")
                ):
                    continue
                card_id = _card_id(tid, iid, index, fingerprint)
                if card_id in state["cards"]:
                    continue
                older = any(c["topic_id"] == tid and c["item_id"] == iid
                            and c["sentence_index"] == index for c in state["cards"].values())
                passed_fp = facts.get("passed_source_fingerprint")
                if passed_fp is not None and passed_fp != fingerprint:
                    continue
                if older and passed_fp != fingerprint:
                    continue
                learned_at = facts.get("passed_at") if passed_fp == fingerprint else None
                state["cards"][card_id] = _make_card(
                    tid, iid, index, found, learned_at, "difficulty"
                )
                _supersede_older(state, state["cards"][card_id])
        except (FileNotFoundError, ValueError, OSError, KeyError, TypeError):
            continue


def _due_cards(state: dict, cache: dict | None = None) -> list[dict]:
    today = _today().isoformat()
    cards = [c for c in state["cards"].values()
             if not c["paused"] and not c.get("superseded")
             and c["due_date"] <= today and _valid(c, cache)]
    return sorted(cards, key=lambda c: (c["due_date"], c["created_at"],
                                        c["topic_id"], c["item_id"], c["sentence_index"]))


def _pending_learning() -> list[dict]:
    rows = []
    root = study_progress.PRIVATE_DIR
    if not root.exists():
        return rows
    for path in root.glob("*/*/state.json"):
        tid, iid = path.parent.parent.name, path.parent.name
        try:
            progress = study_progress.get_progress(tid, iid)
            if progress["stage"] == "summary" or (
                progress["stage"] == "before" and not progress.get("before_started")
            ):
                continue
            full = _source_info(tid, iid)
            rows.append({"topic_id": tid, "item_id": iid, "question": full["question"],
                         "stage": progress["stage"], "sentence_index": progress["sentence_index"],
                         "last_activity_at": progress.get("last_activity_at")})
        except (FileNotFoundError, ValueError, KeyError):
            continue
    return sorted(rows, key=lambda row: (row["last_activity_at"] or "", row["topic_id"],
                                         row["item_id"]), reverse=True)


def _preview(card: dict) -> dict:
    return {key: card[key] for key in ("id", "topic_id", "item_id", "sentence_index",
                                      "zh", "question", "source", "due_date", "paused")}


def _recovery(card: dict, cache: dict | None = None) -> dict:
    exists = library.item_path(card["topic_id"], card["item_id"]).exists()
    material_ready = False
    if exists:
        found = _material(card["topic_id"], card["item_id"], cache)
        material_ready = found["status"] == "ready" and card["sentence_index"] < len(
            found.get("material", {}).get("sentences", [])
        )
    return {**_preview(card), "source_exists": exists, "material_ready": material_ready}


def today_overview() -> dict:
    with _LOCK:
        state = _load()
        cache: dict = {}
        _reconcile(state, cache)
        due = _due_cards(state, cache)
        invalid = [c for c in state["cards"].values()
                   if not c.get("superseded") and not _valid(c, cache)]
        active = next((s for s in state["sessions"].values() if s["state"] == "active"), None)
        return {
            "today": _today().isoformat(), "due_count": len(due),
            "due_preview": [_preview(c) for c in due[:10]],
            "continue_learning": _pending_learning(),
            "active_session_id": active["id"] if active else None,
            "needs_material_count": len(invalid),
            "needs_material": [_recovery(c, cache) for c in invalid[:5]],
            "has_learning_records": study_progress.PRIVATE_DIR.exists() and any(
                study_progress.PRIVATE_DIR.glob("*/*/state.json")
            ),
            "history": {"undated_legacy_count": sum(c["legacy"] for c in state["cards"].values())},
        }


def _current_card(state: dict, session: dict) -> dict | None:
    if session["current_index"] >= len(session["card_ids"]):
        return None
    return state["cards"].get(session["card_ids"][session["current_index"]])


def _public_session(state: dict, session: dict) -> dict:
    out = {k: session[k] for k in ("id", "card_ids", "current_index", "state", "phase",
                                    "hint_used", "responded", "recording_id", "no_recording")}
    out["results"] = list(session["results"])
    card = _current_card(state, session)
    if card:
        usable = _valid(card)
        availability = "paused" if card["paused"] else "ready" if usable else "missing"
        out["current_card"] = {**_preview(card), "availability": availability}
        if session["phase"] == "compare" and usable:
            found = study.get_material(card["topic_id"], card["item_id"])
            row = found["material"]["sentences"][card["sentence_index"]]
            out["current_card"].update({"en": row["en"], "explanation": row["explanation"],
                                         "usage": row["usage"]})
    else:
        out["current_card"] = None
    return out


def start_session(topic_id: str | None = None, item_id: str | None = None,
                  sentence_index: int | None = None) -> dict:
    with _LOCK, study_progress._LOCK, library.LIB_LOCK:
        state = _load()
        _reconcile(state)
        active = next((s for s in state["sessions"].values() if s["state"] == "active"), None)
        if active:
            return _public_session(state, active)
        if topic_id is not None:
            cards = [c for c in state["cards"].values()
                     if c["topic_id"] == topic_id and c["item_id"] == item_id
                     and c["sentence_index"] == sentence_index and not c["paused"] and _valid(c)]
            if not cards:
                raise ValueError("这句尚未加入可用的口答日程")
            cards = cards[:1]
        else:
            cards = _due_cards(state)[:10]
        if not cards:
            raise ValueError("今天没有待口答的困难句")
        sid = uuid.uuid4().hex
        session = {"id": sid, "created_at": _now_iso(), "card_ids": [c["id"] for c in cards],
                   "current_index": 0, "state": "active", "phase": "prompt",
                   "hint_used": False, "responded": False, "recording_id": None,
                   "no_recording": False, "results": []}
        state["sessions"][sid] = session
        _write(state)
        return _public_session(state, session)


def get_session(session_id: str) -> dict:
    with _LOCK:
        state = _load()
        if session_id not in state["sessions"]:
            raise FileNotFoundError("复习轮次不存在")
        return _public_session(state, state["sessions"][session_id])


def _advance(session: dict) -> None:
    session["current_index"] += 1
    session.update({"phase": "prompt", "hint_used": False, "responded": False,
                    "recording_id": None, "no_recording": False})
    if session["current_index"] >= len(session["card_ids"]):
        session["state"] = "completed"


def session_action(session_id: str, action: str, action_id: str) -> dict:
    if action not in {"hint", "answered_without_recording", "show_answer", "skip"}:
        raise ValueError("未知口答操作")
    if not action_id or len(action_id) > 100:
        raise ValueError("缺少操作 ID")
    with _LOCK, study_progress._LOCK, library.LIB_LOCK:
        state = _load()
        receipt_key = f"{session_id}:action:{action_id}"
        if receipt_key in state["receipts"]:
            return state["receipts"][receipt_key]
        session = state["sessions"].get(session_id)
        if not session:
            raise FileNotFoundError("复习轮次不存在")
        if session["state"] != "active":
            raise ValueError("本轮已结束")
        card = _current_card(state, session)
        if not card:
            raise ValueError("本轮没有当前句")
        if action != "skip" and (card["paused"] or not _valid(card)):
            raise ValueError("句子已暂停或材料已变化，请跳过后处理")
        if action == "hint":
            session["hint_used"] = True
        elif action == "answered_without_recording":
            session.update({"responded": True, "no_recording": True, "phase": "compare",
                            "recording_id": None})
        elif action == "show_answer":
            if not session["responded"]:
                session["hint_used"] = True
                session["no_recording"] = True
            session["phase"] = "compare"
        else:
            session["results"].append({"card_id": card["id"], "zh": card["zh"],
                                       "outcome": "skipped"})
            _advance(session)
        response = _public_session(state, session)
        if action == "hint":
            response["hint_text"] = card["en"]
        state["receipts"][receipt_key] = response
        _write(state)
        return response


def attach_recording(session_id: str, recording_id: str) -> dict:
    with _LOCK, study_progress._LOCK, library.LIB_LOCK:
        state = _load()
        session = state["sessions"].get(session_id)
        if not session or session["state"] != "active":
            raise ValueError("复习轮次不可录音")
        card = _current_card(state, session)
        if not card or card["paused"] or not _valid(card):
            raise ValueError("当前句子不可用")
        progress = study_progress.get_progress(card["topic_id"], card["item_id"])
        entry = next((r for r in progress["recordings"]
                      if r["id"] == recording_id and r["stage"] == "oral_review"
                      and r["session_id"] == session_id
                      and r["sentence_index"] == card["sentence_index"]), None)
        if not entry:
            raise ValueError("录音与当前句子不匹配")
        session.update({"recording_id": recording_id, "responded": True,
                        "no_recording": False, "phase": "compare"})
        _write(state)
        return _public_session(state, session)


def save_session_recording(session_id: str, data: bytes, duration_sec: float,
                           media_type: str) -> dict:
    with _LOCK, study_progress._LOCK, library.LIB_LOCK:
        state = _load()
        session = state["sessions"].get(session_id)
        if not session or session["state"] != "active" or session["phase"] != "prompt":
            raise ValueError("当前轮次无法录音")
        card = _current_card(state, session)
        if not card or card["paused"] or not _valid(card):
            raise ValueError("当前句子无法录音")
        entry = study_progress.save_recording(
            card["topic_id"], card["item_id"], "oral_review", data, duration_sec,
            media_type, card["sentence_index"], session_id,
        )
        return {"recording": entry, "session": attach_recording(session_id, entry["id"])}


def _recording_exists(card: dict, session_id: str, recording_id: str) -> bool:
    try:
        progress = study_progress.get_progress(card["topic_id"], card["item_id"])
        entry = next((r for r in progress["recordings"] if r["id"] == recording_id
                      and r["stage"] == "oral_review" and r["session_id"] == session_id
                      and r["sentence_index"] == card["sentence_index"]), None)
        if not entry:
            return False
        file = study_progress.PRIVATE_DIR / card["topic_id"] / card["item_id"] / entry["filename"]
        return file.name == entry["filename"] and file.is_file() and file.stat().st_size > 0
    except (FileNotFoundError, ValueError, KeyError, OSError):
        return False


def submit_attempt(session_id: str, submission_id: str, rating: str) -> dict:
    if rating not in {"independent", "needs_hint", "unable"}:
        raise ValueError("请选择有效的自评结果")
    if not submission_id or len(submission_id) > 100:
        raise ValueError("缺少提交 ID")
    with _LOCK, study_progress._LOCK, library.LIB_LOCK:
        state = _load()
        receipt_key = f"{session_id}:attempt:{submission_id}"
        if receipt_key in state["receipts"]:
            return state["receipts"][receipt_key]
        session = state["sessions"].get(session_id)
        if not session:
            raise FileNotFoundError("复习轮次不存在")
        if session["state"] != "active" or session["phase"] != "compare":
            raise ValueError("请先口答并查看示范")
        card = _current_card(state, session)
        if not card or card["paused"] or not _valid(card):
            raise ValueError("材料已变化，请跳过这句并补齐材料")
        if session["recording_id"] and not _recording_exists(
            card, session_id, session["recording_id"]
        ):
            raise ValueError("本次录音已删除或不可用，请重新录音或改为无录音自评")
        if rating == "independent" and (session["hint_used"] or not session["responded"]):
            raise ValueError("看过提示或未口答，不能标为独立说出")
        if rating == "needs_hint" and not session["responded"]:
            raise ValueError("尚未口答，请选择暂时说不出")
        today = _today().isoformat()
        adjusted = card["last_adjusted_date"] != today
        if adjusted:
            card["level"] = min(card["level"] + 1, 4) if rating == "independent" else 0
            card["due_date"] = (
                _today() + timedelta(days=INTERVAL_DAYS[card["level"]])
            ).isoformat()
            card["last_adjusted_date"] = today
        attempt = {
            "submission_id": submission_id, "session_id": session_id, "card_id": card["id"],
            "topic_id": card["topic_id"], "item_id": card["item_id"],
            "sentence_index": card["sentence_index"], "question": card["question"],
            "zh": card["zh"], "en": card["en"], "submitted_at": _now_iso(),
            "date": today, "rating": rating, "hint_used": session["hint_used"],
            "recording_id": session["recording_id"], "recorded": bool(session["recording_id"]),
            "spoken_self_report": session["responded"], "schedule_adjusted": adjusted,
            "next_due_date": card["due_date"],
        }
        state["attempts"].append(attempt)
        session["results"].append({"card_id": card["id"], "zh": card["zh"],
                                   "outcome": rating, "recorded": attempt["recorded"],
                                   "next_due_date": card["due_date"]})
        _advance(session)
        state["receipts"][receipt_key] = attempt
        _write(state)
        return attempt


def set_card_paused(card_id: str, paused: bool) -> dict:
    with _LOCK, study_progress._LOCK, library.LIB_LOCK:
        state = _load()
        _reconcile(state)
        card = state["cards"].get(card_id)
        if not card:
            raise FileNotFoundError("复习句子不存在")
        card["paused"] = bool(paused)
        _write(state)
        return _preview(card)


def enroll_card(topic_id: str, item_id: str, index: int) -> dict:
    with _LOCK, study_progress._LOCK, library.LIB_LOCK:
        found = study.get_material(topic_id, item_id)
        if found["status"] != "ready" or index < 0 or index >= len(found["material"]["sentences"]):
            raise ValueError("逐句材料未就绪或句子序号错误")
        state = _load()
        _reconcile(state)
        fp = found["material"]["source_fingerprint"]
        card_id = _card_id(topic_id, item_id, index, fp)
        card = state["cards"].get(card_id)
        if not card:
            card = _make_card(topic_id, item_id, index, found, _now_iso(), "manual")
            state["cards"][card_id] = card
        else:
            card["paused"] = False
        card["superseded"] = False
        _supersede_older(state, card)
        _write(state)
        return _preview(card)


def get_card_for_sentence(topic_id: str, item_id: str, index: int) -> dict:
    with _LOCK:
        state = _load()
        _reconcile(state)
        found = study.get_material(topic_id, item_id)
        if found["status"] != "ready" or index < 0 or index >= len(found["material"]["sentences"]):
            return {"status": "material_unavailable"}
        card_id = _card_id(topic_id, item_id, index, found["material"]["source_fingerprint"])
        card = state["cards"].get(card_id)
        return {"status": "enrolled", "card": _preview(card)} if card and not card.get(
            "superseded"
        ) else {
            "status": "not_enrolled",
        }


def get_history(day: str | None = None, topic_id: str | None = None,
                item_id: str | None = None) -> dict:
    if day is not None:
        date.fromisoformat(day)
    with _LOCK:
        state = _load()
        _reconcile(state)
        attempts = [a for a in state["attempts"]
                    if (day is None or a["date"] == day)
                    and (topic_id is None or a["topic_id"] == topic_id)
                    and (item_id is None or a["item_id"] == item_id)]
        dates: dict[str, dict] = {}
        sources = {(c["topic_id"], c["item_id"]): {"topic_id": c["topic_id"],
            "item_id": c["item_id"], "question": c["question"]} for c in state["cards"].values()}
        passed_total = 0
        undated_dictation = 0

        def bucket_for(value: str) -> dict:
            return dates.setdefault(value, {"date": value, "attempt_count": 0,
                "distinct_cards": set(), "dictation_passed_count": 0,
                "ratings": {"independent": 0, "needs_hint": 0, "unable": 0},
                "attempts": []})

        root = study_progress.PRIVATE_DIR
        if root.exists():
            for path in root.glob("*/*/state.json"):
                tid, iid = path.parent.parent.name, path.parent.name
                if (topic_id is not None and tid != topic_id) or (
                    item_id is not None and iid != item_id
                ):
                    continue
                try:
                    progress = study_progress.get_progress(tid, iid)
                except (FileNotFoundError, ValueError, OSError):
                    continue
                for fact in progress.get("facts", {}).values():
                    if not isinstance(fact, dict) or not fact.get("passed"):
                        continue
                    passed_at = fact.get("passed_at")
                    if not passed_at:
                        undated_dictation += 1
                    elif day is None or passed_at[:10] == day:
                        passed_total += 1
                        bucket_for(passed_at[:10])["dictation_passed_count"] += 1

        for attempt in attempts:
            card = state["cards"].get(attempt["card_id"])
            attempt["recording_available"] = bool(attempt["recording_id"] and card
                and _recording_exists(card, attempt["session_id"], attempt["recording_id"]))
            bucket = bucket_for(attempt["date"])
            bucket["attempt_count"] += 1
            bucket["distinct_cards"].add(attempt["card_id"])
            bucket["ratings"][attempt["rating"]] += 1
            bucket["attempts"].append(attempt)
        result = []
        for bucket in sorted(dates.values(), key=lambda b: b["date"], reverse=True):
            bucket["distinct_sentence_count"] = len(bucket.pop("distinct_cards"))
            result.append(bucket)
        return {"days": result, "sources": list(sources.values()),
                "dictation_passed_total": passed_total,
                "dictation_undated_count": undated_dictation,
                "undated_legacy_count": sum(
            c.get("legacy", False) for c in state["cards"].values()
        )}
