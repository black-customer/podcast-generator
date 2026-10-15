"""雅思单题训练：提示事实、独立口答、跨天复验与无损私有状态。"""

import copy
import hashlib
import json
from datetime import date, timedelta
from functools import lru_cache

from . import library, study, study_progress

RATINGS = {"independent", "needs_hint", "unable"}
INTERVALS = [1, 3, 7, 14, 30]


@lru_cache(maxsize=128)
def _audio_digest(path: str, size: int, modified: int, created: int) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def initial(legacy: dict, fingerprint: str) -> dict:
    completed = legacy.get("stage") == "summary"
    return {
        "version": 2,
        "fingerprint": fingerprint,
        "phase": "summary" if completed else "before",
        "status": "awaiting_review" if completed else "unstarted",
        "legacy_completed": completed,
        "sentences": {},
        "focus": [],
        "index": 0,
        "whole_hint": False,
        "successes": 0,
        "due_date": None,
        "last_success_day": None,
        "attempts": [],
        "receipts": {},
        "paused": False,
        "elapsed_sec": 0,
        "inputs": copy.deepcopy(legacy.get("training_inputs") or
                                {"answer": "", "intent": "", "feedback": ""}),
        "notes": "",
    }


def reduce(state: dict, payload: dict, material: dict, now: str, part: int) -> dict:
    if payload.get("version") != 2 or payload.get("fingerprint") != state["fingerprint"]:
        raise ValueError("训练版本已变化，请重新打开；原记录保留")
    aid, action = payload.get("action_id"), payload.get("action")
    if not isinstance(aid, str) or not 1 <= len(aid) <= 128:
        raise ValueError("缺少有效动作标识")
    if aid in {"__proto__", "constructor", "prototype"}:
        raise ValueError("动作标识无效")
    if aid in state["receipts"]:
        return copy.deepcopy(state)
    s = copy.deepcopy(state)
    if action == "undo":
        if "undo" not in s:
            raise ValueError("没有可撤销的操作")
        previous = s.pop("undo")
        receipts = s["receipts"]
        s = previous
        s["receipts"] = receipts
    else:
        previous = {k: copy.deepcopy(v) for k, v in s.items() if k not in {"undo", "receipts"}}
        rows = material.get("sentences", [])
        day = now[:10]
        phase = s["phase"]
        if action == "start":
            if phase != "before":
                raise ValueError("当前步骤不能重新创建首答")
            s.update(
                phase="inputs",
                status="training",
                baseline_unexposed=bool(payload.get("unexposed", False)),
                baseline_recording_id=payload.get("recording_id"),
            )
        elif action == "inputs":
            if phase != "inputs":
                raise ValueError("请先完成首答")
            for key in ("answer", "intent", "feedback"):
                value = payload.get(key, "")
                if not isinstance(value, str) or len(value) > 30000:
                    raise ValueError("原回答或补充内容过长")
                s["inputs"][key] = value
            s["phase"] = "understand"
        elif action == "understand":
            if phase != "understand" or not rows:
                raise ValueError("请先准备并理解学习材料")
            focus = payload.get("focus")
            if focus is None:
                focus = [n for n, r in enumerate(rows) if r.get("original_error")][:3]
                focus = focus or list(range(min(3, len(rows))))
            _indices(focus, rows)
            s.update(focus=focus, index=0, phase="sentence" if focus else "outline")
            for n in focus:
                s["sentences"].setdefault(str(n), {}).update(hint=False, visible=False)
        elif action in {"reveal", "hide", "dictation", "sentence"}:
            n = payload.get("index")
            _indices([n], rows)
            if phase != "sentence" or s["focus"][s["index"]] != n:
                raise ValueError("当前不在该句练习阶段")
            fact = s["sentences"].setdefault(str(n), {})
            if action == "reveal":
                fact["hint"] = True
                fact["visible"] = True
            elif action == "hide":
                fact["visible"] = False
            elif action == "dictation":
                draft = payload.get("draft", "")
                if not isinstance(draft, str) or len(draft) > 10000:
                    raise ValueError("默写草稿过长")
                fact.update(draft=draft, written_passed=payload.get("passed") is True)
            else:
                rating = payload.get("rating")
                if rating not in RATINGS or (rating == "independent" and fact.get("hint")):
                    raise ValueError("用过答案或提示后不能记为独立说出")
                if fact.get("visible"):
                    raise ValueError("请先隐藏英文，再尝试口答")
                fact.update(oral=rating, alternative=payload.get("alternative") is True)
                s["index"] += 1
                if s["index"] >= len(s["focus"]):
                    s["phase"] = "outline"
        elif action == "outline_done":
            if phase != "outline":
                raise ValueError("请先完成局部练习")
            s.update(phase="whole", whole_hint=False)
        elif action == "review":
            if phase not in {"summary", "whole"}:
                raise ValueError("请先完成当前训练")
            s.update(phase="whole", whole_hint=False)
        elif action == "refocus":
            if phase != "summary":
                raise ValueError("请先结束当前回答")
            s.update(phase="understand", status="training")
        elif action == "whole_hint":
            if phase != "whole":
                raise ValueError("当前不在整题回答阶段")
            s["whole_hint"] = True
        elif action == "whole":
            rating = payload.get("rating")
            if phase != "whole" or rating not in RATINGS:
                raise ValueError("请先独立完成整题回答")
            if rating == "independent" and s["whole_hint"]:
                raise ValueError("用过提示不能记为独立完成")
            if not payload.get("recording_id") and payload.get("no_recording") is not True:
                raise ValueError("请先保存录音，或明确选择无录音自评")
            if part == 3 and rating == "independent" and not payload.get("followup_completed"):
                raise ValueError("请先完成相关追问")
            weak = payload.get("weak_indices", [])
            _indices(weak, rows)
            delayed = s["due_date"] and day >= s["due_date"]
            if rating == "independent":
                if day != s["last_success_day"] and (delayed or not s["due_date"]):
                    if delayed:
                        s["successes"] += 1
                    s["last_success_day"] = day
                    interval = INTERVALS[min(s["successes"], len(INTERVALS) - 1)]
                    s["due_date"] = (date.fromisoformat(day) + timedelta(days=interval)).isoformat()
                s.update(
                    phase="summary", status="mastered" if s["successes"] >= 2 else "awaiting_review"
                )
            else:
                s.update(
                    successes=0,
                    due_date=None,
                    last_success_day=None,
                    status="training",
                    phase="sentence" if rows else "understand",
                    index=0,
                    focus=weak or list(range(min(3, len(rows)))),
                )
                for n in s["focus"]:
                    s["sentences"].setdefault(str(n), {}).update(hint=False, visible=False)
            s["attempts"].append(
                {
                    "id": aid,
                    "created_at": now,
                    "rating": rating,
                    "hint_used": state["whole_hint"],
                    "recording_id": payload.get("recording_id"),
                    "no_recording": payload.get("no_recording") is True,
                    "followup_completed": payload.get("followup_completed") is True,
                    "next_due_date": s["due_date"],
                    "weak_indices": weak,
                }
            )
        elif action == "pause":
            if not isinstance(payload.get("paused"), bool):
                raise ValueError("暂停状态错误")
            s["paused"] = payload["paused"]
        elif action == "activity":
            seconds = payload.get("seconds")
            if (
                isinstance(seconds, bool)
                or not isinstance(seconds, (float, int))
                or not 0 <= seconds <= 120
            ):
                raise ValueError("练习用时错误")
            s["elapsed_sec"] += seconds
            notes = payload.get("notes", s["notes"])
            if not isinstance(notes, str) or len(notes) > 10000:
                raise ValueError("准备笔记过长")
            s["notes"] = notes
        else:
            raise ValueError("未知训练动作")
        if action not in {"activity", "dictation", "reveal", "hide", "whole_hint"}:
            s["undo"] = previous
    s["receipts"][aid] = True
    s["updated_at"] = now
    return s


def _indices(indices: list, rows: list) -> None:
    if (
        not isinstance(indices, list)
        or len(indices) > len(rows)
        or any(
            isinstance(n, bool) or not isinstance(n, int) or not 0 <= n < len(rows) for n in indices
        )
        or len(set(indices)) != len(indices)
    ):
        raise ValueError("练习句子序号错误")


def context(tid: str, iid: str) -> dict:
    item = library.get_item_full(tid, iid)
    found = study.get_material(tid, iid)
    material = found.get("material") or {}
    path = library.item_path(tid, iid)
    audio = path / "audio_podcast.mp3"
    stamp = ""
    if audio.exists():
        stat = audio.stat()
        stamp = _audio_digest(str(audio), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                material,
                study.source_fingerprint(library.read_item_texts(path)),
                stamp,
            ]
        ).encode()
    ).hexdigest()
    legacy = study_progress.get_progress(tid, iid)
    stored = legacy.get("training")
    if stored is not None and (not isinstance(stored, dict) or stored.get("version") != 2):
        raise ValueError("训练记录版本不受支持，请保留原件")
    state = (
        copy.deepcopy(stored)
        if stored and stored.get("fingerprint") == fingerprint
        else initial(legacy, fingerprint)
    )
    if stored and stored.get("awaiting_material") and stored.get("fingerprint") != fingerprint:
        state = copy.deepcopy(stored)
        state.update(fingerprint=fingerprint, awaiting_material=not bool(material))
        state.pop("undo", None)
    part = (
        item.get("ielts_part") or item.get("part") or library.load_meta(path).get("ielts_part", 1)
    )
    # 旧条目通过题库题干匹配推断 Part，未匹配时不伪造题型。
    from . import bank

    for question in bank.load_bank().get("questions", []):
        if question.get("text", "").strip() == item.get("question", "").strip():
            part = question.get("part", part)
            break
    return {
        "state": state,
        "material": material,
        "material_status": found["status"],
        "reason": found.get("reason", ""),
        "part": int(part or 1),
        "item": item,
        "recordings": legacy.get("recordings", []),
        "changed": bool(stored and stored.get("fingerprint") != fingerprint),
        "history": copy.deepcopy(legacy.get("training_history", [])),
    }


def get(tid: str, iid: str) -> dict:
    return context(tid, iid)


def action(tid: str, iid: str, payload: dict) -> dict:
    with study_progress._LOCK, library.LIB_LOCK:
        ctx = context(tid, iid)
        legacy = study_progress.get_progress(tid, iid)
        rec_id = payload.get("recording_id")
        if rec_id and not any(r["id"] == rec_id for r in legacy["recordings"]):
            raise ValueError("录音不属于当前题目")
        if rec_id:
            record = next(r for r in legacy["recordings"] if r["id"] == rec_id)
            if not (study_progress._folder(tid, iid) / record["filename"]).is_file():
                raise ValueError("录音文件不可用，请重录或明确选择无录音自评")
            if payload.get("action") == "whole" and record.get("stage") != "recall":
                raise ValueError("整题复验需要本次独立回答录音")
        updated = reduce(ctx["state"], payload, ctx["material"], library.now_iso(), ctx["part"])
        updated["awaiting_material"] = not bool(ctx["material"])
        previous = legacy.get("training")
        if previous and previous.get("fingerprint") != updated["fingerprint"]:
            legacy.setdefault("training_history", []).append(previous)
        legacy["training"] = updated
        study_progress._write(tid, iid, legacy)
        ctx["state"] = updated
        return ctx


def overview() -> dict:
    rows = []
    if study_progress.PRIVATE_DIR.exists():
        for file in study_progress.PRIVATE_DIR.glob("*/*/state.json"):
            tid, iid = file.parent.parent.name, file.parent.name
            try:
                ctx = context(tid, iid)
            except (ValueError, FileNotFoundError):
                continue
            s = ctx["state"]
            if s["status"] == "unstarted":
                continue
            rows.append(
                {
                    "topic_id": tid,
                    "item_id": iid,
                    "question": ctx["item"]["question"],
                    "part": ctx["part"],
                    "state": s,
                }
            )
    rows.sort(key=lambda r: r["state"].get("updated_at", ""), reverse=True)
    return {"version": 2, "items": rows, "today": library.now_iso()[:10]}


def covered_today(tid: str, iid: str) -> bool:
    legacy = study_progress.get_progress(tid, iid)
    s = legacy.get("training") or {}
    attempts = s.get("attempts", [])
    return bool(attempts and attempts[-1]["created_at"][:10] == library.now_iso()[:10]
                and attempts[-1]["rating"] == "independent"
                and context(tid, iid)["state"]["fingerprint"] == s.get("fingerprint"))
