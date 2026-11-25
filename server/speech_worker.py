"""运行在 ChineseAccent 环境的本地语音 JSON Lines 服务。"""

import hashlib
import json
import os
import re
import shutil
import sys
from collections.abc import Callable
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

_ENGLISH_WORD = re.compile(r"[a-z]+(?:'[a-z]+)*|\d+", re.I)
_WRITTEN_WORD = re.compile(r"[a-z]+(?:['’][a-z]+)*|\d+(?:[.,]\d+)*(?:st|nd|rd|th)?", re.I)
_SPOKEN_NUMBERS = frozenset((
    "zero oh one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty "
    "ninety hundred thousand million billion trillion first second third fourth fifth sixth "
    "seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth "
    "seventeenth eighteenth nineteenth twentieth thirtieth fortieth fiftieth sixtieth seventieth "
    "eightieth ninetieth hundredth thousandth millionth billionth trillionth"
).split())
_HAN = re.compile(r"[\u3400-\u9fff]")
_REFERENCE_ONSET_PAD = 0.058
_REFERENCE_END_PAD = 0.026


def tokens(text: str) -> list[str]:
    return _ENGLISH_WORD.findall(text.lower().replace("’", "'"))


def matched_chunks(transcript: str, chunks: list[str]) -> list[str]:
    spans = [tokens(span) for span in _HAN.split(transcript)]
    return [chunk for chunk in dict.fromkeys(chunks) if (target := tokens(chunk)) and any(
        observed[i:i + len(target)] == target
        for observed in spans for i in range(len(observed) - len(target) + 1)
    )]


def analyze_words(words: list[dict]) -> dict:
    timed = [word for word in words if re.search(r"\w", word["word"]) and (
        word["end"] > word["start"]
    )]
    count = sum(len(tokens(word["word"])) for word in timed)
    duration = timed[-1]["end"] - timed[0]["start"] if timed else 0
    gaps = sum(round(float(right["start"] - left["end"]), 3) > 0.8
               for left, right in zip(timed, timed[1:], strict=False))
    # 混合语音的字数不能充当可比的英语语速。
    english_only = not any(_HAN.search(word["word"]) for word in timed)
    return {"word_count": count, "wpm": round(count * 60 / duration) if duration and
            english_only else None, "long_pauses": gaps if timed else None}


def status() -> dict:
    import importlib.util

    from backend import config
    from backend.engine.voice_profile import get_voice_profile

    torch = sys.modules.get("torch")
    profile = get_voice_profile()
    return {
        "gpu": torch.cuda.get_device_name(0) if torch and torch.cuda.is_available() else None,
        "kokoro": config.KOKORO_MODEL_PATH.is_file() and config.KOKORO_VOICES_PATH.is_file(),
        "whisper": importlib.util.find_spec("faster_whisper") is not None,
        "profile": {key: profile.get(key) for key in (
            "median_f0_hz", "recommended_base_voice", "finetuned"
        )} if profile else None,
    }


def profile_revision() -> dict:
    from backend.engine.voice_profile import get_voice_profile

    profile = get_voice_profile()
    return {"profile_hash": profile.get("profile_hash") if profile else None}


def reference_playback_words(alignment: dict) -> list[dict]:
    """将示范词的 CTC 支撑区间扩展到更接近可听边界。"""
    # 在 TIMIT 校准说话人上测得的中位偏差，见桌面 2.0 的走查。
    duration = alignment["duration"]
    spans = []
    for word in alignment["words"]:
        if word["end"] <= word["start"]:
            continue
        start = max(0.0, word["start"] - _REFERENCE_ONSET_PAD)
        end = min(duration, word["end"] + _REFERENCE_END_PAD)
        if spans and spans[-1]["end"] > start:
            start = round((spans[-1]["end"] + start) / 2, 4)
            spans[-1]["end"] = start
        spans.append({"text": word["word"], "start": round(start, 4), "end": round(end, 4)})
    return spans


def align_reference_words(path: Path, text: str, align: Callable[..., dict]) -> list[dict]:
    """将已识别的数字读法对齐后合并回书面数字。"""
    original = align(path, text, reference=True)
    if not any(letter.isdigit() for letter in text):
        return reference_playback_words(original)

    written = _WRITTEN_WORD.findall(text)
    expected = [word.lower().replace("’", "'") for word in written]
    spoken = tokens(original["greedy_transcript"])
    reading_lengths = [1] * len(written)
    for tag, start, end, heard_start, heard_end in SequenceMatcher(
        None, expected, spoken, autojunk=False
    ).get_opcodes():
        if tag == "equal":
            continue
        reading = set(spoken[heard_start:heard_end])
        if (tag != "replace" or end - start != 1 or not written[start][0].isdigit()
                or not reading & _SPOKEN_NUMBERS
                or reading - _SPOKEN_NUMBERS - {"and", "point"}):
            return reference_playback_words(original)
        reading_lengths[start] = heard_end - heard_start

    aligned = reference_playback_words(align(path, " ".join(spoken), reference=True))
    if [word["text"].lower() for word in aligned] != spoken:
        return reference_playback_words(original)
    words = []
    cursor = 0
    for display, count in zip(written, reading_lengths, strict=True):
        start = aligned[cursor]["start"]
        cursor += count
        words.append({"text": display, "start": start, "end": aligned[cursor - 1]["end"]})
    return words


def preview_line(text: str, voice: str, output: str,
                 profile_hash: str | None = None, require_profile: bool = True) -> dict:
    from backend.engine.audio_io import _synthesize_kokoro_sync
    from backend.engine.voice_profile import get_voice_profile

    final = Path(output)
    profile = get_voice_profile() if voice == "golden_self" else None
    if voice == "golden_self" and require_profile and not profile:
        raise ValueError("尚未配置母语分身，请先在 ChineseAccent 建立声纹")
    if profile_hash and (not profile or profile["profile_hash"] != profile_hash):
        raise ValueError("声纹配置已更新，请重新试听")
    if profile:
        base = profile.get("recommended_base_voice") or "am_liam"
        source = final.with_suffix(".base.wav")
        _synthesize_kokoro_sync(text, base, source)

        import torch
        from backend.engine import voice_clone

        cache_key = hashlib.sha256(f"podcast\n{base}\n{text}".encode()).hexdigest()
        # 读取声纹与权重，派生语音留在调用方的工作目录。
        voice_clone.GOLDEN_AUDIO_DIR = final.parent
        release = voice_clone.release_other_voice_models
        # 已加载的分身与对齐器可以共存；冷启动和显存紧张时用原有释放策略。
        if (voice_clone.get_device_info()["vc_loaded"] and torch.cuda.is_available() and
                torch.cuda.mem_get_info()[0] >= 1024 ** 3):
            voice_clone.release_other_voice_models = lambda: None
        try:
            converted = voice_clone.convert_to_golden_self(
                source, cache_key, version="natural", use_finetuned=True,
                expected_profile_hash=profile["profile_hash"],
            )
        finally:
            voice_clone.release_other_voice_models = release
        shutil.copyfile(converted["audio_path"], final)
    else:
        voice = "am_liam" if voice == "golden_self" else voice
        _synthesize_kokoro_sync(text, voice, final)
    return {"voice": voice}


def synthesize_line(text: str, voice: str, output: str) -> dict:
    from backend.engine.aligner import forced_align_words

    result = preview_line(text, voice, output, require_profile=False)
    return {**result, "words": align_reference_words(Path(output), text, forced_align_words)}


@lru_cache(maxsize=2)
def _whisper(language: str | None):
    from faster_whisper import WhisperModel

    return WhisperModel("base.en" if language == "en" else "base", device="cpu",
                        compute_type="int8")


def transcribe_and_analyze(path: str, language: str | None = None,
                           chunks: list[str] | None = None) -> dict:
    source = path
    options = {"language": language, "beam_size": 3, "word_timestamps": True, "vad_filter": True}
    if language is None:
        from faster_whisper.audio import decode_audio
        from faster_whisper.vad import VadOptions, get_speech_timestamps

        rate = 16000
        source = decode_audio(path, sampling_rate=rate)
        speech = get_speech_timestamps(source, VadOptions(min_silence_duration_ms=300,
                                                          speech_pad_ms=100))
        if not speech:
            return {"transcript": "", "words": [], **analyze_words([]), "matched_chunks": []}
        # 逐个语音区间识别语言，保留原文件的偏移以统计真实停顿。
        timestamps = [span[edge] / rate for span in speech for edge in ("start", "end")]
        options.update(multilingual=True, clip_timestamps=timestamps, vad_filter=False,
                       condition_on_previous_text=False)
    segments, _info = _whisper(language).transcribe(source, **options)
    words, lines = [], []
    for segment in segments:
        lines.append(segment.text.strip())
        words.extend({"word": w.word.strip(), "start": float(w.start), "end": float(w.end)}
                     for w in segment.words or [])
    transcript = " ".join(lines)
    return {"transcript": transcript, "words": words, **analyze_words(words),
            "matched_chunks": matched_chunks(transcript, chunks or [])}


def transcribe_intent(path: str) -> dict:
    segments, _info = _whisper("zh").transcribe(
        path, language="zh", beam_size=3, vad_filter=True,
        initial_prompt="请使用简体中文，保留日常口语和原意。", condition_on_previous_text=False,
    )
    return {"transcript": " ".join(segment.text.strip() for segment in segments).strip()}


def check_utterance(path: str, text: str, chunks: list[str]) -> dict:
    from backend.engine.aligner import forced_align_words
    from backend.engine.audio_io import decode_to_wav16k

    source = Path(path)
    wav = source.with_suffix(".ctc.wav")
    try:
        decode_to_wav16k(source, wav)
        aligned = forced_align_words(wav, text)
        heard = aligned.get("greedy_transcript", "")
        hits = [] if aligned.get("off_script") else matched_chunks(heard, chunks)
        return {"transcript": heard, "matched_chunks": hits}
    finally:
        wav.unlink(missing_ok=True)


def main() -> None:
    sys.path.insert(0, str(Path.cwd()))
    # 模型及 C 扩展的诊断输出不能写入协议流。
    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), sys.stdout.fileno())
    methods = {function.__name__: function for function in (
        status, profile_revision, synthesize_line, preview_line, transcribe_and_analyze,
        transcribe_intent, check_utterance
    )}
    for line in sys.stdin:
        request_id = None
        try:
            message = json.loads(line)
            request_id = message["id"]
            result = methods[message["method"]](**message.get("params", {}))
            response = json.dumps({"id": request_id, "result": result}, allow_nan=False)
        except Exception as exc:
            detail = str(exc)
            memory_failure = (isinstance(exc, MemoryError) or getattr(exc, "winerror", 0) == 1455
                              or any(term in detail.lower()
                                     for term in ("out of memory", "bad allocation")))
            error = ("本机内存或页面文件不足，当前语音未能生成"
                     if memory_failure else f"本地语音引擎：{type(exc).__name__} {detail[:240]}")
            response = json.dumps({"id": request_id, "error": error, "reset": memory_failure})
        print(response, file=protocol, flush=True)


if __name__ == "__main__":
    main()
