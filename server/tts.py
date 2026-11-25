"""本地逐句语音合成、时间轴、母带及 dry-run 占位。"""
import logging
import re
import shutil
import threading
import uuid
import wave
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory

from . import alignment, audio, audioqa, library, mastering, speech_bridge, timeline
from .config import TMP_DIR, is_dry_run, load_settings

logger = logging.getLogger(__name__)
Progress = Callable[[int, int, str, str], None]

# 支持的合成轨道
VALID_TRACKS = ("default", "monologue", "podcast", "all")

# 对话行：A: / B: / Person A: / Person B:（或全角冒号）
DIALOGUE_LINE_RE = re.compile(
    r"^(?P<tags>(?:\[[^\[\]\n]+\]\s*)*)"
    r"(?:person\s*)?(?P<role>[ab]|interviewer|examiner|candidate)\s*[:：]",
    re.IGNORECASE,
)


class TTSError(RuntimeError):
    pass


class TTSCancelled(RuntimeError):
    """用户取消：任务应立即停止，不算错误。"""
    pass


def parse_dialogue(text: str):
    """识别 A:/B: 交替对话。返回 [(speaker, line)]；不是规整对话则返回 None。"""
    lines: list[tuple[str, str]] = []
    current = ""
    parts: list[str] = []
    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        raw = raw.strip()
        if not raw:
            continue
        marker = DIALOGUE_LINE_RE.match(raw)
        if marker:
            if current and parts:
                lines.append((current, " ".join(parts).strip('"“”').strip()))
            role = marker["role"].lower()
            current = "b" if role in {"b", "candidate"} else "a"
            body = f"{marker['tags'].strip()} {raw[marker.end():].strip()}".strip()
            parts = [body] if body else []
        elif current:
            parts.append(raw)
        else:
            return None
    if current and parts:
        lines.append((current, " ".join(parts).strip('"“”').strip()))
    lines = [(role, body) for role, body in lines if strip_speaker_body(body)]
    return lines if {role for role, _ in lines} == {"a", "b"} else None


def strip_speaker_body(body: str) -> str:
    return audioqa.strip_all_tags(body)[0].strip()


def _split_long_unit(u: str, max_chars: int) -> tuple[str, str]:
    """把超长单元硬切成两段：优先在空格处断开，且绝不切进 [tag] 标签内部。"""
    cut = max_chars
    space = u.rfind(" ", 0, cut)
    if space > max_chars // 2:
        cut = space + 1
    # 若切点前存在跨越切点的未闭合 '['，把切点挪到对应 ']' 之后
    b = u.rfind("[", 0, cut)
    while b != -1:
        close = u.find("]", b + 1)
        if close == -1:
            break
        if close >= cut:
            cut = close + 1
            break
        b = u.rfind("[", 0, b)
    return u[:cut].strip(), u[cut:].lstrip()


def split_text(text: str, max_chars: int) -> list[str]:
    """按句子边界切段；尊重 [tag] 标签不切断；超长单句硬切。"""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    units: list[str] = []
    buf: list[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        buf.append(ch)
        if ch == "[":
            j = text.find("]", i)
            if j != -1:
                buf.append(text[i + 1 : j + 1])
                i = j
        elif ch in ".!?。！？…":
            if i + 1 >= n or text[i + 1] in " \n\t":
                units.append("".join(buf))
                buf = []
        elif ch == "\n":
            units.append("".join(buf))
            buf = []
        i += 1
    if buf:
        units.append("".join(buf))

    units = [u.strip() for u in units if u.strip()]
    segments: list[str] = []
    cur = ""
    for u in units:
        while len(u) > max_chars:
            if cur:
                segments.append(cur)
                cur = ""
            head, u = _split_long_unit(u, max_chars)
            segments.append(head)
        if cur and len(cur) + len(u) + 1 > max_chars:
            segments.append(cur)
            cur = u
        else:
            cur = f"{cur} {u}".strip() if cur else u
    if cur:
        segments.append(cur)
    return segments


def estimate_seconds(text: str) -> float:
    """dry-run 时按英文平均语速（约 14 字符/秒）估算时长。"""
    return max(1.0, len(text or "") / 14.0)


def clean_text(text: str) -> str:
    """清理旧表演稿的标签和容易拖长停顿的标点。"""
    cleaned, _ = audioqa.strip_all_tags(text or "")
    cleaned = cleaned.replace("—", ", ").replace("–", ", ")
    cleaned = cleaned.replace("...", ", ").replace("…", ", ")
    cleaned = re.sub(r",\s*,+", ",", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().strip(",").strip()

def language_segments(text: str) -> list[dict]:
    """标点随其前面的语言一起合成。"""
    parts = []
    start, language = 0, None
    for i, char in enumerate(text):
        current = "zh" if "\u3400" <= char <= "\u9fff" else "en" if char.isalpha() else None
        if current and language and language != current:
            parts.append({"lang": language, "text": text[start:i].strip()})
            start = i
        if current:
            language = current
    if language:
        parts.append({"lang": language, "text": text[start:].strip()})
    return parts


def render_dialogue(lines: list[tuple[str, str]], out_path: Path, settings: dict,
                    *, speed: float = 1.0) -> None:
    """为离线练习包渲染双语台词，允许为跟读素材指定语速。"""
    if is_dry_run(settings):
        raise TTSError("本地训练音频需要就绪的 ChineseAccent 语音环境")
    voices = {"a": settings.get("kokoro_question_voice") or "af_bella",
              "b": settings.get("kokoro_answer_voice") or "am_puck"}
    mandarin = {"a": "zf_xiaoxiao", "b": "zm_yunxi"}
    clips = []
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="practice-dialogue-", dir=TMP_DIR) as directory:
        work = Path(directory)
        for speaker, text in lines:
            speaker = speaker.lower()
            for index, row in enumerate(language_segments(clean_text(text))):
                zh = row["lang"] == "zh"
                clip = work / f"{len(clips):03d}.wav"
                speech_bridge.request(
                    settings, "preview_line", text=row["text"], output=clip,
                    voice=(mandarin if zh else voices)[speaker], lang="cmn" if zh else "en-us",
                )
                mp3 = clip.with_suffix(".mp3")
                audio._run(["ffmpeg", "-y", "-i", str(clip), "-af", f"atempo={speed}",
                            "-ar", "44100", "-ac", "1", "-b:a", "128k", str(mp3)])
                clips.append({"path": mp3, "gap_before": 0.06 if index else 0.24 if clips else 0})
        if not clips:
            raise TTSError("没有可合成的练习台词")
        audio.concat_mp3(clips, out_path)


def _synthesize_source(
    src: str, out_path: Path, settings: dict, force_monologue: bool = False,
    cancel: threading.Event | None = None, on_progress: Progress | None = None,
) -> tuple[float, int, bool, str, list[dict], list[dict]]:
    dialogue = parse_dialogue(src) if not force_monologue else None
    dry = is_dry_run(settings)
    segments, words = [], []
    turns = []
    for speaker, text in dialogue or [("b", src)]:
        role = "question" if speaker == "a" else "answer"
        voice = settings.get(f"kokoro_{role}_voice") or (
            "af_bella" if speaker == "a" else "am_puck"
        )
        turns.append((speaker, voice, alignment.split_sentences(clean_text(text))))
    total = sum(len(sentences) for _, _, sentences in turns)
    rate = 44100
    cursor = 0
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="kokoro-", dir=TMP_DIR) as directory:
        work = Path(directory)
        combined = work / "dialogue.wav"
        with wave.open(str(combined), "wb") as merged:
            merged.setparams((1, 2, rate, 0, "NONE", "not compressed"))
            for turn, (speaker, voice, sentences) in enumerate(turns):
                for index, sentence in enumerate(sentences):
                    if on_progress and index == 0:
                        on_progress(len(segments), total, sentence, voice)
                    if cancel and cancel.is_set():
                        raise TTSCancelled("已取消")
                    clip = work / f"line-{turn}-{index}.wav"
                    data: dict = {}
                    if dry:
                        audio.make_tone(estimate_seconds(sentence), clip)
                    else:
                        try:
                            data = speech_bridge.request(settings, "synthesize_line", text=sentence,
                                                         voice=voice, output=clip, cancel=cancel)
                        except speech_bridge.SpeechCancelled as exc:
                            raise TTSCancelled(str(exc)) from exc
                        except speech_bridge.SpeechError as exc:
                            raise TTSError(str(exc)) from exc
                    pcm = work / "standard.wav"
                    audio._run(["ffmpeg", "-y", "-i", str(clip), "-ar", str(rate), "-ac", "1",
                                "-c:a", "pcm_s16le", str(pcm)])
                    with wave.open(str(pcm), "rb") as source:
                        frames = source.getnframes()
                        if frames <= 0:
                            raise TTSError("本地语音引擎生成了空音频")
                        gap = round(rate * (0.12 if index else 0.28 if segments else 0))
                        merged.writeframesraw(bytes(2 * gap))
                        cursor += gap
                        start, end = cursor / rate, (cursor + frames) / rate
                        merged.writeframesraw(source.readframes(frames))
                        cursor += frames
                    segments.append({"text": sentence, "speaker": speaker,
                                     "start": round(start, 3), "end": round(end, 3),
                                     "voice": data.get("voice")})
                    words.extend({"text": word["text"], "start": round(start + word["start"], 3),
                                  "end": round(min(end, start + word["end"]), 3)}
                                 for word in data.get("words", [])
                                 if 0 <= word["start"] < word["end"] and
                                 word["start"] < end - start)
                    if on_progress:
                        on_progress(len(segments), total, sentence, data.get("voice") or voice)
        if not segments:
            raise TTSError("没有可合成的本地语音文本")
        audio.concat_mp3([{"path": combined}], out_path)
        duration = audio.probe_duration(out_path)
        if duration <= 0:
            raise TTSError("本地合成音频时长为 0")
        try:
            duration = mastering.apply_mastering(out_path, out_path, is_dialogue=bool(dialogue))
        except audio.FFmpegError:
            logger.warning("本地语音母带处理失败，保留基础音频", exc_info=True)
    return duration, len(segments), bool(dialogue), "kokoro_local", segments, words


def _synthesize_with_qa(
    src: str,
    out_path: Path,
    settings: dict,
    force_monologue: bool = False,
    cancel: threading.Event | None = None,
    on_progress: Progress | None = None,
) -> tuple[tuple, dict, str, list[dict]]:
    """合成 + QA 门禁：临时文件验收、去违规标签重试、通过后原子替换。
    追加返回 align_words。

    返回 (合成结果元组, QA 报告, 实际使用的源文本)。
    """
    dry = is_dry_run(settings)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    staged = out_path.with_name(f".{out_path.stem}.{uuid.uuid4().hex}.staging.mp3")
    retry_path = out_path.with_name(f".{out_path.stem}.{uuid.uuid4().hex}.retry.mp3")
    chosen = staged
    effective_src = src
    options = {"on_progress": on_progress} if on_progress else {}
    try:
        result = _synthesize_source(
            src, staged, settings, force_monologue, cancel=cancel, **options,
        )
        align_words = result[5] or []
        report = audioqa.run_qa(staged, src, duration_sec=None, skip_vad=dry)
        if report["verdict"] == "retry":
            cleaned, removed = audioqa.strip_all_tags(src)
            if not removed or not cleaned.strip() or cleaned == src:
                raise TTSError("音频 QA 未通过，且没有可剥离的表演标签")
            logger.warning("QA 不通过，去标签安全重试: %s removed=%s", out_path.name, removed)
            result = _synthesize_source(
                cleaned, retry_path, settings, force_monologue, cancel=cancel, **options
            )
            effective_src = cleaned
            align_words = result[5] or []
            report = audioqa.run_qa(
                retry_path, cleaned, duration_sec=None, skip_vad=dry
            )
            if report["verdict"] == "retry":
                raise TTSError("去标签重试后音频 QA 仍未通过")
            chosen = retry_path
        if cancel and cancel.is_set():
            raise TTSCancelled("已取消")
        chosen.replace(out_path)
        return result, report, effective_src, align_words
    finally:
        staged.unlink(missing_ok=True)
        retry_path.unlink(missing_ok=True)


def _save_track_outputs(
    ipath: Path,
    track: str,
    src: str,
    out_audio: Path,
    dur: float,
    align_segments: list[dict] | None,
    words: list[dict] | None = None,
    speaker_a: str = "Mia",
    speaker_b: str = "Ethan",
    mode: str = "measured",
) -> list[dict]:
    """写 alignment_{track}.json（真实/估算标记 + 可选逐词）+ timeline_{track}.json。"""
    audio_for_align = out_audio
    if align_segments:
        doc = alignment.build_alignment_doc(
            mode=mode, source_text=src, audio_path=audio_for_align,
            segments=align_segments, track=track, words=words,
        )
    else:
        # 单次合成轨：暂无逐词数据，用旧估算器生成并明确标记 estimated
        if parse_dialogue(src):
            est = timeline.generate_timeline_for_dialogue(src, out_audio, speaker_a, speaker_b)
            est = est or timeline.generate_timeline_for_monologue(src, out_audio, speaker_a)
        else:
            est = timeline.generate_timeline_for_monologue(src, out_audio, speaker_a)
        doc = alignment.build_alignment_doc(
            mode="estimated", source_text=src, audio_path=audio_for_align,
            segments=est, track=track,
        )
    alignment.save_alignment(doc, ipath / f"alignment_{track}.json")
    tl = alignment.derive_timeline(doc, speaker_a, speaker_b)
    timeline.save_timeline(tl, ipath / f"timeline_{track}.json")
    return tl


def generate_item_audio(
    topic_id: str,
    item_id: str,
    track: str = "default",
    cancel: threading.Event | None = None,
    on_progress: Progress | None = None,
) -> dict:
    """为单个条目生成音频。
    track: 'monologue' | 'podcast' | 'all' | 'default'
    """
    if track not in VALID_TRACKS:
        raise TTSError(f"未知轨道: {track}（可选 {VALID_TRACKS}）")
    settings = load_settings()
    dry = is_dry_run(settings)
    full = library.get_item_full(topic_id, item_id)
    ipath = library.item_path(topic_id, item_id)

    meta_updates = {
        "status": "generated",
        "error": "",
        "stale": False,
        "generated_at": library.now_iso(),
        "dry_run": dry,
    }

    results = {}
    options = {"on_progress": on_progress} if on_progress else {}

    if track in ("all", "monologue"):
        src_mono, field_mono = library.get_track_source_text(full, "monologue")
        if src_mono:
            out_mono = ipath / "audio_monologue.mp3"
            res = _synthesize_with_qa(
                src_mono, out_mono, settings, force_monologue=True, cancel=cancel, **options
            )
            (dur, segs, is_diag, mode, seg_spans, seg_words), qa_report, eff_src, align_words = res
            meta_updates["duration_sec_monologue"] = round(dur, 2)
            meta_updates["qa_monologue"] = qa_report["verdict"]
            audioqa.save_qa_report(qa_report, ipath / "qa_monologue.json")
            results["monologue"] = {
                "duration_sec": round(dur, 2), "segments": segs, "mode": mode,
                "qa": qa_report["verdict"],
            }
            align_mode = "sse" if mode == "kokoro_local" and seg_words else "measured"
            _save_track_outputs(ipath, "monologue", eff_src, out_mono, dur, seg_spans, seg_words,
                                mode=align_mode)
            # 如果没有主 audio.mp3，拷贝一份（连 alignment 一起）
            if not (ipath / "audio.mp3").exists():
                shutil.copy2(out_mono, ipath / "audio.mp3")
                meta_updates["duration_sec"] = round(dur, 2)
                shutil.copy2(ipath / "alignment_monologue.json", ipath / "alignment_podcast.json")
                shutil.copy2(ipath / "timeline_monologue.json", ipath / "timeline_podcast.json")
        elif track == "monologue":
            raise TTSError("没有可合成的独白文本（需 monologue_script 或 monologue_text）")

    if track in ("all", "podcast"):
        src_pod, field_pod = library.get_track_source_text(full, "podcast")
        if src_pod:
            out_pod = ipath / "audio_podcast.mp3"
            res = _synthesize_with_qa(
                src_pod, out_pod, settings, force_monologue=False, cancel=cancel, **options
            )
            (dur, segs, is_diag, mode, seg_spans, seg_words), qa_report, eff_src, align_words = res
            meta_updates["duration_sec_podcast"] = round(dur, 2)
            meta_updates["qa_podcast"] = qa_report["verdict"]
            audioqa.save_qa_report(qa_report, ipath / "qa_podcast.json")
            results["podcast"] = {
                "duration_sec": round(dur, 2), "segments": segs, "mode": mode,
                "qa": qa_report["verdict"],
            }
            word_timed = mode == "kokoro_local" and seg_words
            pod_mode = "sse" if word_timed else "measured"
            _save_track_outputs(
                ipath, "podcast", eff_src, out_pod, dur, seg_spans, seg_words, mode=pod_mode
            )
            if not (ipath / "audio.mp3").exists() and "monologue" not in results:
                shutil.copy2(out_pod, ipath / "audio.mp3")
                meta_updates["duration_sec"] = round(dur, 2)
        elif track == "podcast":
            raise TTSError("没有可合成的播客文本（需 podcast_script 或 podcast_text）")

    if track == "default" or (not results and track == "all"):
        src_def, field_def = library.get_track_source_text(full, "default")
        if not src_def:
            library.update_item_meta(topic_id, item_id, error="没有可合成的文本")
            raise TTSError("没有可合成的文本")
        out_def = ipath / "audio.mp3"
        res = _synthesize_with_qa(src_def, out_def, settings, cancel=cancel, **options)
        (dur, segs, is_diag, mode, seg_spans, seg_words), qa_report, eff_src, align_words = res
        meta_updates["duration_sec"] = round(dur, 2)
        meta_updates["tts_source"] = field_def
        meta_updates["dialogue"] = is_diag
        meta_updates["tts_mode"] = mode
        meta_updates["qa_default"] = qa_report["verdict"]
        audioqa.save_qa_report(qa_report, ipath / "qa_default.json")
        results["default"] = {
            "duration_sec": round(dur, 2), "segments": segs, "mode": mode,
            "qa": qa_report["verdict"],
        }
        track_key = "podcast" if is_diag else "monologue"
        def_mode = "sse" if mode in {"dialogue_single_pass", "kokoro_local"} and align_words else (
            "measured"
        )
        _save_track_outputs(
            ipath, track_key, eff_src, out_def, dur, seg_spans, align_words, mode=def_mode
        )

    # 编辑与生成可并行：在同一数据锁内比对源稿并落元数据，避免旧稿音频清除 stale 标记。
    with library.LIB_LOCK:
        current_texts = library.read_item_texts(ipath)
        if any(current_texts[field] != full[field] for field in library.STALE_TEXT_FIELDS):
            meta_updates["stale"] = True
        meta_updates["generated_at"] = library.now_iso()
        library.update_item_meta(topic_id, item_id, **meta_updates)
    return {
        "ok": True,
        "track": track,
        "results": results,
        "dry_run": dry,
    }
