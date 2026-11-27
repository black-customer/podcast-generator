"""从已校验逐句材料生成本机双人教学电台。"""
import hashlib
import json
import re
import shutil
import threading
import wave
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from . import (
    arcade,
    audio,
    audioqa,
    captures,
    library,
    mastering,
    oral_review,
    rewrite,
    speech_bridge,
    study,
    study_progress,
    tts,
)
from .config import DATA_DIR, TMP_DIR, atomic_replace, load_settings
from .speech_worker import matched_chunks

EPISODE_DIR = DATA_DIR / "teaching_podcasts"
_LOCK = threading.Lock()
_CJK = re.compile(r"[\u3400-\u9fff]")
Progress = Callable[[str, int, int, str], None]
_STAGE_DIRECTION = re.compile(
    r"\[|\]|<|>|[（(][^）)]*(?:pause|silence|wait|静音|停顿|等待|笑声|轻笑|叹气|laugh|sigh|chuckle)|"
    r"\b(?:pause|wait|silence)\s+(?:for\s+)?(?:\d+|three)\s*s",
    re.I,
)


def validate_script(lines: list[dict], targets: list[str]) -> None:
    previous = None
    tutors = []
    for line in lines:
        role, text = line.get("speaker"), line.get("text")
        if (role not in ("A", "B") or role == previous or not isinstance(text, str)
                or not text.strip() or _STAGE_DIRECTION.search(text)
                or ("\n" in text or "\r" in text)):
            raise ValueError("台词需由女导师和男搭档轮流自然说出，不含舞台指令")
        previous = role
        if role == "A":
            tutors.append(text)
    if (len(lines) < 2 or lines[0]["speaker"] != "A" or not targets
            or any(not matched_chunks(" ".join(tutors), [target]) for target in targets)):
        raise ValueError("双人教学播客需要两位主持人与每个目标表达")


def _validate_turns(turns: object, mode: str, targets: list[str]) -> list[dict]:
    if not isinstance(turns, list) or not 2 <= len(turns) <= 32:
        raise ValueError("电台剧本需要 2–32 轮双人台词")
    cleaned, lines = [], []
    for turn in turns:
        if not isinstance(turn, dict):
            raise ValueError("电台台词须是 JSON 对象")
        segments = turn.get("segments")
        if segments is None and isinstance(turn.get("text"), str):
            segments = tts.language_segments(turn["text"])
        if not isinstance(segments, list) or not 1 <= len(segments) <= 12:
            raise ValueError("每轮电台台词需要有效的语音分段")
        normalized = []
        for row in segments:
            if (not isinstance(row, dict) or row.get("lang") not in ("zh", "en")
                    or not isinstance(row.get("text"), str) or not row["text"].strip()
                    or len(row["text"]) > 600 or _STAGE_DIRECTION.search(row["text"])):
                raise ValueError("电台分段需要有效的语言和可直接朗读的台词")
            detected = tts.language_segments(" ".join(row["text"].split()))
            if not detected or (mode == "en" and any(p["lang"] != "en" for p in detected)):
                raise ValueError("全英文电台需要纯英文台词")
            normalized.extend(detected)
        role = turn.get("speaker")
        lines.append({"speaker": role, "text": " ".join(row["text"] for row in normalized)})
        cleaned.append({"speaker": role, "segments": normalized})
    if mode == "bilingual" and not any(
        row["lang"] == "zh" for turn in cleaned for row in turn["segments"]
    ):
        raise ValueError("中英电台剧本缺少中文台词")
    validate_script(lines, targets)
    return cleaned


def draft_episode_with_llm(context: dict, mode: str, cancel: threading.Event | None) -> dict:
    language = "ENGLISH MODE. Write every spoken segment in English. "
    example = '{"speaker":"A","segments":[{"lang":"en","text":"How do you unwind?"}]}'
    if mode == "bilingual":
        language = (
            "中英双语电台。两位主播用普通话交流、分析和点拨，用英文引用原话、带读和举例。"
            "女导师 A 的第一段必须是普通话，男搭档 B 也必须至少说一段普通话。"
            "不要把中文讲解翻译成英文。每个分段只包含一种语言，普通话标 zh，英文标 en。"
        )
        example = ('{"speaker":"A","segments":[{"lang":"zh","text":"你是怎么放松的？"},'
                   '{"lang":"en","text":"How do you unwind?"}]},'
                   '{"speaker":"B","segments":[{"lang":"zh","text":"我会先想到散步。"}]}')
    messages = [
        {"role": "system", "content": (
            language + " Write a short, natural English-learning podcast with a female coach A "
            "and a male "
            "partner B. Start with A and alternate turns. Use the learner's exact English attempt, "
            "their Chinese intent and the supplied evidence when available. For scenes or "
            "excerpts, use the supplied context and bridge from it to new examples rather than "
            "attributing the dialogue to the learner. Discuss why the literal wording can "
            "be tempting, then let the hosts model the reusable phrases and show how they work "
            "in everyday situations. Use a relaxed conversation with room for natural follow-ups. "
            "Never invent personal facts or mistakes. A should speak every key_chunk in points. "
            "Aim for about two to three minutes and 8–14 short turns. "
            "No labels, stage directions, scores, or scripted silences. "
            ' Return JSON only: {"title":"short title","highlights":["key_chunk"],'
            '"turns":[' + example + ']}. The sample shows the structure only; use the given topic.'
        )},
        {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
    ]
    result = rewrite._extract_json(rewrite._chat(load_settings(), messages, cancel))
    title = result.get("title")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 100:
        raise ValueError("电台剧本缺少有效标题")
    targets = [row["key_chunk"] for row in context["points"]]
    turns = _validate_turns(result.get("turns"), mode, targets)
    highlights = result.get("highlights")
    selected = list(dict.fromkeys(phrase for phrase in highlights
                                  if isinstance(phrase, str) and phrase in targets)
                    ) if isinstance(highlights, list) else []
    return {"title": title.strip(), "highlights": (selected + [
        phrase for phrase in targets if phrase not in selected
    ])[:4], "turns": turns}


def _dry_script(question: str, points: list[dict], mode: str, daily: str | None) -> dict:
    lead = [{"lang": "zh", "text": "来听几个可以直接用到口答里的表达。"}]
    reply = [{"lang": "zh", "text": "我再说一遍。"}]
    if mode == "en":
        lead = reply = []
    targets = [row["key_chunk"] for row in points]
    return {"title": f"{daily} 今日电台" if daily else question, "highlights": targets,
            "turns": [
                {"speaker": "A", "segments": lead + [
                    {"lang": "en", "text": row["en"]} for row in points
                ]},
                {"speaker": "B", "segments": reply + [
                    {"lang": "en", "text": "Let me try that again."}
                ]},
            ]}


def _targets(rows: list[dict], limit: int, *, prioritize_gaps: bool = True) -> list[dict]:
    ranked = sorted(rows, key=lambda row: (
        not row.get("original_error"), row.get("gap_kind") != "explicit_gap",
    )) if prioritize_gaps else rows
    seen, result = set(), []
    for row in ranked:
        target = row.get("key_chunk", "")
        if target and target.casefold() not in seen:
            result.append(row)
            seen.add(target.casefold())
            if len(result) >= limit:
                break
    return result


def _item_points(topic_id: str, item_id: str) -> list[dict]:
    found = study.get_material(topic_id, item_id)
    return found.get("material", {}).get("sentences", []) if found["status"] == "ready" else []


def _context(topic_id: str, item_id: str, full: dict) -> dict:
    progress = study_progress.get_progress(topic_id, item_id)
    inputs = progress.get("training_inputs") or (progress.get("training") or {}).get("inputs") or {}
    return {"question": full["question"], "original_answer": rewrite.original_answer_of(full),
            "chinese_intent": inputs.get("intent", "")}


def for_item(topic_id: str, item_id: str, mode: str, partner: str, **options) -> dict:
    full = library.get_item_full(topic_id, item_id)
    rows = _item_points(topic_id, item_id)
    points = _targets(rows, 4)
    return generate(full["question"], points, mode, partner,
                    context=_context(topic_id, item_id, full), **options)


def _capture_point(row: dict) -> dict:
    source = row["capture"]["source"]
    fields = ("en", "zh", "chunk_zh", "trigger_context", "usage_boundary",
              "disambiguator", "feynman_hook", "transfer_example_en")
    return {**{key: row[key] for key in fields if row.get(key)},
            "key_chunk": row["chunk_in_sentence"], "target_chunk": row["target_chunk"],
            "source_type": row["capture"]["source_type"],
            "series_title": source.get("series_title", ""),
            "episode_title": source.get("episode_title", "")}


def _blend(groups: list[list[dict]], limit: int) -> list[dict]:
    ordered = []
    for index in range(max(map(len, groups), default=0)):
        ordered.extend(group[index] for group in groups if index < len(group))
    return _targets(ordered, limit, prioritize_gaps=False)


def for_capture(capture_id: str, mode: str, partner: str, **options) -> dict:
    capture = captures.get_capture(capture_id)
    source = capture["source"]
    series = source.get("series_id")
    if capture["source_type"] == "scene" and series:
        rows = [row for row in captures.list_cards(status="active", source_type="scene")
                if row["capture"]["source"].get("series_id") == series]
    else:
        rows = captures.list_cards(status="active", capture_id=capture_id)
    points = _targets([_capture_point(row) for row in rows], 4, prioritize_gaps=False)
    if not points:
        raise ValueError("请先确认入库至少一条看剧表达")
    title = source.get("series_title") or capture["title"]
    return generate(f"{title} · 表达复盘", points, mode, partner, capture_id=capture_id,
                    context={"series_title": title, "focus": "scene recap"}, **options)


def for_today(mode: str, partner: str, **options) -> dict:
    day = oral_review._today()
    today = day.isoformat()
    with oral_review._LOCK:
        review = oral_review._load()
    attempts = [row for row in reversed(review["attempts"])
                if row["date"] == today and row.get("fsrs_grade") != "suspend"]
    speaking_attempts = [row for row in attempts if oral_review._is_ielts(row)]
    rows, sources, practiced = [], {}, []

    def source_row(entry: dict) -> None:
        key = entry["topic_id"], entry["item_id"]
        if key not in sources:
            try:
                sources[key] = _item_points(*key)
            except FileNotFoundError:
                sources[key] = []
        index = entry["sentence_index"]
        if 0 <= index < len(sources[key]) and sources[key][index]["en"] == entry["en"]:
            rows.append(sources[key][index])

    for key in dict.fromkeys((row["topic_id"], row["item_id"]) for row in speaking_attempts):
        try:
            sources[key] = _item_points(*key)
            full = library.get_item_full(*key)
            if sources[key] and len(practiced) < 6:
                practiced.append({**_context(*key, full), "points": _targets(sources[key], 2)})
        except FileNotFoundError:
            sources[key] = []
        rows.extend(sources[key])
    current = _targets(rows, 2)
    rows.clear()
    old = sorted((card for card in review["cards"].values()
                  if oral_review._is_ielts(card) and not card.get("deck_id") and not card["paused"]
                  and not card.get("superseded")
                  and card["due_date"] <= today
                  and (card.get("last_reviewed") or card.get("learned_at") or "")[:10] != today),
                 key=lambda card: card["due_date"])
    seen_today = {attempt.get("card_id") for attempt in attempts}
    for card in old:
        if card["id"] not in seen_today:
            source_row(card)
    used = {row["key_chunk"].casefold() for row in current}
    previous = _targets([row for row in rows if row.get("key_chunk", "").casefold() not in used],
                        2, prioritize_gaps=False)
    ielts = current + previous
    if len(ielts) < 4:
        ielts.extend(arcade._fresh_ielts(set(review["cards"]), 4 - len(ielts), False))
    recent = (day - timedelta(days=2)).isoformat()
    groups = {"scene": [], "snippet": []}
    for row in captures.list_cards(status="active"):
        kind = row["capture"]["source_type"]
        if kind not in groups:
            continue
        schedule = review["cards"].get(row["id"], {})
        due = not schedule or schedule["due_date"] <= today
        fresh = (schedule.get("created_at") or row["capture"]["created_at"])[:10] >= recent
        if not schedule.get("paused") and (due or fresh or row["id"] in seen_today):
            groups[kind].append(_capture_point(row))
    from . import decks

    deck_points = []
    deck_records = [review["cards"].get(row["card_id"], {}) for row in attempts
                    if row.get("card_kind") == "deck"]
    deck_records.extend(row for row in review["cards"].values()
                        if row.get("deck_id") and row.get("last_adjusted_date")
                        and row["due_date"] <= today)
    for scheduled in deck_records:
        deck_id = scheduled.get("deck_id")
        if deck_id not in review.get("enabled_decks", []) or scheduled.get("paused"):
            continue
        try:
            row = decks.get_card(deck_id, scheduled["id"].rsplit(":", 1)[-1])
        except (OSError, ValueError):
            continue
        if decks._fingerprint(row) == scheduled["source_fingerprint"]:
            deck_points.append({**row, "key_chunk": row["target_chunk"], "source_type": "deck"})
    points = _blend([ielts, groups["scene"], groups["snippet"], _targets(deck_points, 4)], 4)
    question = speaking_attempts[0].get("question", "") if speaking_attempts else ""
    return generate(question or "Which expression comes back to you first?", points,
                    mode, partner, daily=today, context={"practiced": practiced,
                                                       "due_expressions": previous}, **options)



def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel and cancel.is_set():
        raise tts.TTSCancelled("已取消")


def _join_audio(paths: list[tuple[Path, str]], target: Path
                ) -> tuple[float, list[tuple[float, float]]]:
    combined = target.parent / "joined.wav"
    pcm = target.parent / "turn.wav"
    spans, position, rate = [], 0, 24000
    with wave.open(str(combined), "wb") as merged:
        merged.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        previous = None
        for path, speaker in paths:
            if previous is not None:
                gap = round(rate * (0.06 if speaker == previous else 0.24))
                merged.writeframesraw(bytes(gap * 2))
                position += gap
            previous = speaker
            audio._run(["ffmpeg", "-y", "-i", str(path), "-ac", "1", "-ar", str(rate),
                        "-c:a", "pcm_s16le", str(pcm)], timeout=40)
            with wave.open(str(pcm), "rb") as part:
                samples = part.getnframes()
                if not samples:
                    raise ValueError("有一句主持台词的音频为空")
                merged.writeframesraw(part.readframes(samples))
            spans.append((round(position / rate, 4), round((position + samples) / rate, 4)))
            position += samples
    duration = mastering.apply_mastering(combined, target)
    if not audioqa.check_silence_islands(target, min_island=3.0)["ok"]:
        raise ValueError("电台音频含连续三秒静音，请重试")
    return duration, spans


def generate(question: str, points: list[dict], mode: str, partner: str,
             *, daily: str | None = None, context: dict | None = None,
             capture_id: str | None = None,
             cancel: threading.Event | None = None, on_progress: Progress | None = None) -> dict:
    if not points:
        raise ValueError("先确认一张语块卡或完成带语块的逐句材料，再生成教学电台")
    if mode not in {"en", "bilingual"} or partner not in {"am_puck", "golden_self"}:
        raise ValueError("未知的电台语言或搭档音色")
    settings = load_settings()
    dry = bool(settings.get("dry_run"))
    _check_cancel(cancel)
    voices = {"A": "af_bella", "B": partner}
    mandarin = {"A": "zf_xiaoxiao", "B": "zm_yunxi"}
    profile_hash = None
    if partner == "golden_self" and not dry:
        profile_hash = speech_bridge.request(
            settings, "profile_revision", timeout=15, cancel=cancel,
        ).get("profile_hash")
        if not profile_hash:
            raise ValueError("尚未配置母语分身")
    if on_progress:
        on_progress("script", 0, 0, "正在根据这些表达编排双人播客")
    script = (_dry_script(question, points, mode, daily) if dry else
              draft_episode_with_llm({"question": question, **(context or {}), "points": points},
                                     mode, cancel))
    _check_cancel(cancel)
    episode_key = [daily, mode, voices, profile_hash, dry, script]
    if capture_id:
        episode_key.append(capture_id)
    digest = json.dumps(episode_key, ensure_ascii=False)
    episode_id = hashlib.sha256(digest.encode()).hexdigest()[:24]
    segments = [{**row, "speaker": turn["speaker"]} for turn in script["turns"]
                for row in turn["segments"]]
    total = len(segments)
    _check_cancel(cancel)
    try:
        return get_episode(episode_id)
    except FileNotFoundError:
        pass
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="teaching-radio-", dir=TMP_DIR) as directory:
        work = Path(directory)
        paths = []
        if on_progress:
            on_progress("tts", 0, total, "正在启动本地语音")
        for index, line in enumerate(segments):
            _check_cancel(cancel)
            speaker, lang = line["speaker"], line["lang"]
            voice = mandarin[speaker] if lang == "zh" else voices[speaker]
            path = work / f"line-{index}.wav"
            if dry:
                audio.make_tone(tts.estimate_seconds(line["text"]), path)
            else:
                speech_bridge.request(
                    settings, "preview_line", text=line["text"], voice=voice, output=path,
                    lang="cmn" if lang == "zh" else "en-us", cancel=cancel,
                    profile_hash=profile_hash if voice == "golden_self" else None,
                )
            paths.append((path, speaker))
            if on_progress:
                on_progress("tts", index + 1, total, "女导师" if speaker == "A" else "男搭档")
        _check_cancel(cancel)
        if on_progress:
            on_progress("master", total, total, "正在统一响度并检查静音")
        target = work / "episode.mp3"
        duration, timings = _join_audio(paths, target)
        episode = {"id": episode_id, "title": script["title"], "created_at": library.now_iso(),
                   "kind": "daily" if daily else "item", "language_mode": mode,
                   "voices": voices, "duration": duration, "highlights": script["highlights"],
                   "mandarin_voices": mandarin if mode == "bilingual" else {},
                   "dry_run": dry, "audio_url": f"/api/teaching-podcasts/{episode_id}/audio",
                   "lines": [{**line, "start": start, "end": end}
                             for line, (start, end) in zip(segments, timings, strict=True)]}
        if capture_id:
            episode.update(kind="capture", capture_id=capture_id)
        with _LOCK:
            _check_cancel(cancel)
            if (EPISODE_DIR / episode_id).exists():
                return get_episode(episode_id)
            EPISODE_DIR.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=".episode-", dir=EPISODE_DIR) as staging:
                partial = Path(staging)
                shutil.copyfile(target, partial / "episode.mp3")
                (partial / "episode.json").write_text(
                    json.dumps(episode, ensure_ascii=False, indent=2), encoding="utf-8",
                )
                _check_cancel(cancel)
                atomic_replace(partial, EPISODE_DIR / episode_id)
    return episode


def public_episode(episode: dict) -> dict:
    return {key: value for key, value in episode.items() if key != "lines"}


def audio_file(episode_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{24}", episode_id):
        raise FileNotFoundError("教学播客不存在")
    folder = EPISODE_DIR / episode_id
    path = folder / "episode.mp3"
    if not path.is_file() or not (folder / "episode.json").is_file():
        raise FileNotFoundError("教学播客不存在")
    return path


def get_episode(episode_id: str) -> dict:
    return json.loads(audio_file(episode_id).with_suffix(".json").read_text(encoding="utf-8"))


def list_episodes() -> list[dict]:
    result = []
    for path in EPISODE_DIR.glob("*/episode.json"):
        try:
            result.append(get_episode(path.parent.name))
        except (OSError, ValueError):
            continue
    return sorted(result, key=lambda episode: episode["created_at"], reverse=True)
