"""从已校验逐句材料生成本机双人教学电台。"""
import asyncio
import hashlib
import json
import os
import re
import shutil
import threading
import wave
from pathlib import Path
from tempfile import TemporaryDirectory

from . import audio, audioqa, library, mastering, oral_review, speech_bridge, study
from .config import DATA_DIR, TMP_DIR, load_settings
from .speech_worker import matched_chunks

EPISODE_DIR = DATA_DIR / "teaching_podcasts"
_LOCK = threading.Lock()
_CJK = re.compile(r"[\u3400-\u9fff]")
_EDGE_FEMALE = "zh-CN-XiaoxiaoMultilingualNeural"
_EDGE_FEMALE_FALLBACK = "zh-CN-XiaoxiaoNeural"
_EDGE_MALE = "zh-CN-YunxiNeural"
_STAGE_DIRECTION = re.compile(
    r"\[|\]|<|>|[（(][^）)]*(?:pause|silence|wait|静音|停顿|等待)|"
    r"\b(?:pause|wait|silence)\s+(?:for\s+)?(?:\d+|three)\s*s",
    re.I,
)


def validate_script(lines: list[dict], targets: list[str]) -> None:
    previous = None
    tutors = []
    for line in lines:
        role, text = line.get("speaker"), line.get("text")
        if (role not in {"A", "B"} or role == previous or not isinstance(text, str)
                or not text.strip() or _STAGE_DIRECTION.search(text)
                or ("\n" in text or "\r" in text)):
            raise ValueError("台词需由女导师和男搭档轮流自然说出，不含舞台指令")
        previous = role
        if role == "A":
            tutors.append(text)
    if (len(lines) < 2 or lines[0]["speaker"] != "A" or not targets
            or any(not matched_chunks(" ".join(tutors), [target]) for target in targets)):
        raise ValueError("双人教学播客需要两位主持人与每个目标表达")


def build_script(question: str, points: list[dict], mode: str,
                 *, daily: bool = False) -> list[dict]:
    bilingual = mode == "bilingual"
    lines: list[dict] = []
    question = question.translate(str.maketrans("", "", "[]<>"))
    if _CJK.search(question):
        question = "Which phrase would you reach for here?"

    def turn(speaker: str, text: str) -> None:
        text = " ".join(text.split())
        if _CJK.search(text) and re.search(r"[A-Za-z]", text):
            raise ValueError("中英文分别交给独立台词")
        lines.append({"speaker": speaker, "text": text})

    turn("A", "今天聊几处开口时容易卡住的表达。先听意思，说出一个词也可以。"
         if bilingual else "Picture this: we're halfway through an answer, the idea is there, "
         "and one expression just won't come. Let's see what makes it easier to find next time.")
    turn("B", "That happens to me all the time. I have the idea in my head, and then I reach "
         "for the most ordinary word I know.")
    for i, row in enumerate(points):
        target = row["key_chunk"]
        example = row.get("transfer_example") or row["en"]
        error = row.get("original_error")
        cue = row["zh"].translate(str.maketrans("", "", "[]<>"))
        if bilingual:
            # 中文意群有时保留术语；英文目标在随后一轮另说。
            cue = re.sub(r"[\x00-\x7f]+", " ", cue).strip()
            open_line = f"想说的是这层意思。{cue} 你会怎么开口？"
            if error:
                issue = re.sub(r"[\x00-\x7f]+", " ", error["issue"]).strip()
                open_line = f"这句意思是这样。{cue} {issue}。试着先说一遍。"
        elif error:
            quote = error["quote"].translate(str.maketrans("", "", "[]<>"))
            open_line = f'You said, "{quote}." What small change would keep the meaning?'
        elif i == 0:
            open_line = f"Let's take this one. {question} "
            open_line += "One short phrase can do a lot of work here."
        else:
            open_line = "Here's another moment that feels familiar. Can you reach for a phrase "
            open_line += "that says the same thing a little more precisely?"
        turn("A", open_line)
        # 犹豫写成有意义的搭档台词，留出抢答空间又保持连续声音。
        clue = target.split(maxsplit=1)[0]
        turn("B", f"Hmm, starts with {clue}. What comes next?" if not daily and len(points) > 1 else
             f"Hmm, I think it starts with {clue}. I can picture what I mean. "
             "Give me the rest of that phrase.")
        if error:
            explanation = f'Try this wording: "{row["en"]}" The bit to keep together is {target}.'
        else:
            explanation = f'Yes, {target}. Put it back into the answer and you get: "{row["en"]}"'
        turn("A", explanation)
        turn("B", "That sounds like something I'd actually say. Where else could I use it?")
        scenario = (f'In a different conversation, you could say, "{example}"'
                    if row.get("transfer_example")
                    else f'Imagine a friend wants a quick example. You could reply, "{example}"')
        turn("A", scenario)
        turn("B", f"Okay, {target}. I can carry that into another answer without learning "
             "the whole thing by heart." if len(points) == 1 and not daily else
             f"Okay, {target}. I can carry that into another answer.")
        if daily:
            turn("A", "Try saying the line again with one detail from your own life. "
                 "Leave the phrase together and change a detail around it.")
            turn("B", "I can swap in a different time or place. That gives me something "
                 "to say when the question comes up again, without memorizing a script.")
    if daily:
        turn("A", "On the next question, listen for the idea first. If it fits, try the expression "
             "once. You'll remember more when the words are tied to something you actually mean.")
        turn("B", "I like that. I'll think of a real example, say it out loud, and see which "
             "expressions I can retrieve. I'll leave anything that doesn't fit for another answer.")
        if len(points) == 1:
            turn("A", "Let's do one more pass. Imagine a friend hears your answer and asks for "
                 "a little more detail. Say why that idea matters or how it came about.")
            turn("B", "Hmm, I'd start with one thing I can picture, then add why it stands out. "
                 "Keeping the answer simple gives me time to find the words I want.")
            turn("A", f"Exactly. Bring back {points[0]['key_chunk']} when it fits. You can give "
                 "the answer your own ending and still get some practice with the same expression.")
            turn("B", "That's a plan. I'll say my own version on the way out. Next time I hear "
                 "the question, I'll see what I can bring back without looking at the sentence.")
    elif len(points) == 1:
        turn("A", "Try slipping that phrase into one new sentence later on. A small change of "
             "scene is enough to make it your own.")
        turn("B", "Deal. I'll keep the useful bit handy and let the next answer be different.")
    validate_script(lines, [row["key_chunk"] for row in points])
    return lines


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


def for_item(topic_id: str, item_id: str, mode: str, partner: str) -> dict:
    full = library.get_item_full(topic_id, item_id)
    rows = _item_points(topic_id, item_id)
    gaps = [row for row in rows
            if row.get("original_error") or row.get("gap_kind") == "explicit_gap"]
    points = _targets(gaps or rows, 2 if gaps else 1)
    return generate(full["question"], points, mode, partner)


def for_today(mode: str, partner: str) -> dict:
    today = oral_review._today().isoformat()
    with oral_review._LOCK:
        review = oral_review._load()
    attempts = [row for row in reversed(review["attempts"]) if row["date"] == today]
    rows, sources = [], {}

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

    for key in dict.fromkeys((row["topic_id"], row["item_id"]) for row in attempts):
        try:
            sources[key] = _item_points(*key)
        except FileNotFoundError:
            sources[key] = []
        rows.extend(sources[key])
    current = _targets(rows, 2)
    rows.clear()
    old = sorted((card for card in review["cards"].values()
                  if not card["paused"] and not card.get("superseded")
                  and (card.get("last_reviewed") or card.get("learned_at") or "")[:10] != today),
                 key=lambda card: card["due_date"])
    seen_today = {attempt.get("card_id") for attempt in attempts}
    for card in old:
        if card["id"] not in seen_today:
            source_row(card)
    used = {row["key_chunk"].casefold() for row in current}
    previous = _targets([row for row in rows if row.get("key_chunk", "").casefold() not in used],
                        2, prioritize_gaps=False)
    question = attempts[0].get("question", "") if attempts else ""
    return generate(question or "Which expression comes back to you first?", current + previous,
                    mode, partner, daily=today)


def _edge_speak(text: str, voice: str, output: Path) -> str:
    try:
        from edge_tts import Communicate
        from edge_tts.exceptions import NoAudioReceived
    except ImportError as exc:
        raise ValueError(
            "中英电台需要安装 edge-tts：.venv/Scripts/python -m pip install edge-tts"
        ) from exc
    try:
        try:
            asyncio.run(Communicate(text, voice, receive_timeout=25).save(str(output)))
        except NoAudioReceived:
            voice = _EDGE_FEMALE_FALLBACK if voice == _EDGE_FEMALE else voice
            asyncio.run(Communicate(text, voice, receive_timeout=25).save(str(output)))
        return voice
    except Exception as exc:
        raise ValueError("中英电台连接语音服务失败，请检查网络后重试") from exc


def _join_audio(paths: list[Path], target: Path) -> tuple[float, list[tuple[float, float]]]:
    combined = target.parent / "joined.wav"
    pcm = target.parent / "turn.wav"
    spans, position, rate = [], 0, 24000
    with wave.open(str(combined), "wb") as merged:
        merged.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        for path in paths:
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
             *, daily: str | None = None) -> dict:
    if not points:
        raise ValueError("先完成有重点语块的逐句材料，再生成教学电台")
    if mode not in {"en", "bilingual"} or partner not in {"am_puck", "golden_self"}:
        raise ValueError("未知的电台语言或搭档音色")
    if mode == "bilingual" and partner != "am_puck":
        raise ValueError("中英电台使用晓晓和云希，请切回默认搭档")
    settings = load_settings()
    profile_hash = None
    if partner == "golden_self":
        profile_hash = speech_bridge.request(
            settings, "profile_revision", timeout=15,
        ).get("profile_hash")
        if not profile_hash:
            raise ValueError("尚未配置母语分身")
    voices = ({"A": "af_bella", "B": partner} if mode == "en" else
              {"A": _EDGE_FEMALE, "B": _EDGE_MALE})
    script = build_script(question, points, mode, daily=bool(daily))
    title = f"{daily} 今日电台" if daily else question
    digest = json.dumps([title, voices, profile_hash, script], ensure_ascii=False)
    episode_id = hashlib.sha256(digest.encode()).hexdigest()[:24]
    with _LOCK:
        try:
            return get_episode(episode_id)
        except FileNotFoundError:
            pass
        TMP_DIR.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="teaching-radio-", dir=TMP_DIR) as directory:
            work = Path(directory)
            paths = []
            for index, line in enumerate(script):
                voice = voices[line["speaker"]]
                path = work / f"line-{index}.{'wav' if mode == 'en' else 'mp3'}"
                if mode == "en":
                    speech_bridge.request(
                        settings, "preview_line", text=line["text"], voice=voice, output=path,
                        profile_hash=profile_hash if voice == "golden_self" else None,
                    )
                else:
                    voices[line["speaker"]] = _edge_speak(line["text"], voice, path)
                paths.append(path)
            target = work / "episode.mp3"
            duration, timings = _join_audio(paths, target)
            episode = {"id": episode_id, "title": title, "created_at": library.now_iso(),
                       "kind": "daily" if daily else "item", "language_mode": mode,
                       "voices": voices, "duration": duration,
                       "audio_url": f"/api/teaching-podcasts/{episode_id}/audio",
                       "lines": [{**line, "start": start, "end": end}
                                 for line, (start, end) in zip(script, timings, strict=True)]}
            EPISODE_DIR.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=".episode-", dir=EPISODE_DIR) as staging:
                partial = Path(staging)
                shutil.copyfile(target, partial / "episode.mp3")
                (partial / "episode.json").write_text(
                    json.dumps(episode, ensure_ascii=False, indent=2), encoding="utf-8",
                )
                os.replace(partial, EPISODE_DIR / episode_id)
    return episode


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
