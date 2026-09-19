"""TTS：Fish Audio 客户端 + dry-run 占位 + 长文分段 + 双人对话 + 重试，产出条目 audio.mp3。"""
import base64
import json
import logging
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

import httpx

from . import alignment, audio, audioqa, library, mastering, timeline
from .config import (
    FISH_TTS_URL,
    TMP_DIR,
    load_settings,
    real_api_key,
)

logger = logging.getLogger(__name__)

# 语速范围（Fish prosody.speed）
SPEED_MIN, SPEED_MAX = 0.8, 2.0

# 支持的合成轨道
VALID_TRACKS = ("default", "monologue", "podcast", "all")

# 对话行：A: / B: / Person A: / Person B:（或全角冒号）
DIALOGUE_LINE_RE = re.compile(r"^\s*(?:person\s*)?([ab])\s*[:：]", re.IGNORECASE)


class TTSError(RuntimeError):
    pass


class TTSCancelled(RuntimeError):
    """用户取消：任务应立即停止，不算错误。"""
    pass


def parse_dialogue(text: str):
    """识别 A:/B: 交替对话。返回 [(speaker, line)]；不是规整对话则返回 None。"""
    lines: list[tuple[str, str]] = []
    speakers: set[str] = set()
    for raw in (text or "").replace("\r\n", "\n").split("\n"):
        raw = raw.strip()
        if not raw:
            continue
        m = DIALOGUE_LINE_RE.match(raw)
        if not m:
            return None  # 出现非对话行 → 整体不按对话处理
        speaker = m.group(1).lower()
        body = raw[m.end():].strip().strip('"“”').strip()
        if body:
            lines.append((speaker, body))
            speakers.add(speaker)
    if len(lines) >= 2 and len(speakers) == 2:
        return lines
    return None


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
        while len(u) > max_chars * 1.5:
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


def _post_tts(
    payload: dict, settings: dict, cancel: threading.Event | None = None
) -> bytes:
    headers = {
        "Authorization": f"Bearer {real_api_key(settings)}",
        "model": settings.get("model") or "s2.1-pro-free",
        "Content-Type": "application/json",
    }
    payload = dict(payload)
    payload.setdefault("format", "mp3")
    payload.setdefault("mp3_bitrate", 128)
    payload.setdefault("latency", "normal")
    payload.setdefault("normalize", True)
    try:
        temperature = settings.get("temperature")
        if temperature is not None and temperature != "":
            payload["temperature"] = max(0.0, min(1.0, float(temperature)))
    except (TypeError, ValueError):
        pass

    last_err = ""
    for attempt in range(4):
        if cancel is not None and cancel.is_set():
            raise TTSCancelled("已取消")
        if attempt:
            for _ in range(int([2, 5, 10][attempt - 1] * 10)):
                if cancel is not None and cancel.is_set():
                    raise TTSCancelled("已取消")
                time.sleep(0.1)
        try:
            r = httpx.post(FISH_TTS_URL, headers=headers, json=payload, timeout=300)
        except httpx.HTTPError as exc:
            last_err = f"网络错误: {exc}"
            continue
        if r.status_code == 200:
            return r.content
        if r.status_code in (429, 500, 502, 503, 504):
            last_err = f"Fish API {r.status_code}: {(r.text or '')[:200]}"
            continue
        raise TTSError(f"Fish API {r.status_code}: {(r.text or '')[:300]}")
    raise TTSError(f"重试 4 次仍失败。{last_err}")


FISH_TTS_SSE_URL = "https://api.fish.audio/v1/tts/stream/with-timestamp"


def fish_tts_sse(
    text: str,
    settings: dict,
    reference_id: str = "",
    cancel: threading.Event | None = None,
    is_dialogue: bool = False,
) -> tuple[bytes, list[dict]]:
    """流式合成并取逐词时间戳。返回 (audio_bytes, words)。

    words 来自最后一个 SSE 事件的 alignment（实测为全局时间戳、累积词表）。
    任何解析失败都返回 words=[]（上层回退到估算），音频本身照常可用。
    """
    headers = {
        "Authorization": f"Bearer {real_api_key(settings)}",
        "model": settings.get("model") or "s2.1-pro-free",
        "Content-Type": "application/json",
    }
    payload: dict = {"text": text, "format": "mp3", "mp3_bitrate": 128,
                     "latency": "normal", "normalize": True, "chunk_length": 200}
    ref = (reference_id or "").strip()
    if ref:
        payload["reference_id"] = ref
    elif is_dialogue:
        va = (settings.get("reference_id") or "").strip()
        vb = (settings.get("reference_id_b") or "").strip()
        # Bruce 规则：回答必须男声方便模仿 → 男声放数组第 0 位（对应 <|speaker:0|>）。
        # 脚本约定仍是 A:提问 / B:回答，发送时把回答行标记为 speaker:0、提问行为 speaker:1。
        if va and vb:
            if settings.get("answer_voice_male", True):
                payload["reference_id"] = [va, vb]
            else:
                payload["reference_id"] = [vb, va]
    try:
        temperature = settings.get("temperature")
        if temperature is not None and temperature != "":
            payload["temperature"] = max(0.0, min(1.0, float(temperature)))
    except (TypeError, ValueError):
        pass

    last_err = ""
    for attempt in range(3):
        if cancel is not None and cancel.is_set():
            raise TTSCancelled("已取消")
        if attempt:
            time.sleep([2, 5][attempt - 1])
        audio = bytearray()
        words: list[dict] = []
        try:
            with httpx.stream("POST", FISH_TTS_SSE_URL, headers=headers, json=payload,
                              timeout=httpx.Timeout(300, connect=30)) as resp:
                if resp.status_code in (429, 500, 502, 503, 504):
                    last_err = f"Fish SSE {resp.status_code}"
                    resp.read()
                    continue
                if resp.status_code != 200:
                    body = resp.read().decode("utf-8", "ignore")[:300]
                    raise TTSError(f"Fish SSE {resp.status_code}: {body}")
                chunk_align: dict[int, dict] = {}  # seq -> {offset, words}（块内本地时间）
                chunk_order: list[int] = []
                for line in resp.iter_lines():
                    if cancel is not None and cancel.is_set():
                        raise TTSCancelled("已取消")
                    if not line.startswith("data:"):
                        continue
                    try:
                        data = json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
                    audio += base64.b64decode(data.get("audio_base64") or "")
                    align = (data.get("alignment") or {}).get("segments") or []
                    if align:
                        seq = int(data.get("chunk_seq") or 0)
                        if seq not in chunk_align:
                            chunk_order.append(seq)
                        chunk_align[seq] = {
                            "offset": float(data.get("chunk_audio_offset_sec") or 0.0),
                            "words": align,
                        }
                # 全局词表 = 每块最后事件的对齐 + 块偏移（实测：块内时间为本地时间）
                for seq in chunk_order:
                    off = chunk_align[seq]["offset"]
                    for w in chunk_align[seq]["words"]:
                        t = w.get("text", "")
                        if not t:
                            continue
                        try:
                            ws, we = float(w.get("start") or 0.0), float(w.get("end") or 0.0)
                        except (TypeError, ValueError):
                            continue
                        words.append(
                            {"text": t, "start": round(off + ws, 3), "end": round(off + we, 3)}
                        )
        except httpx.HTTPError as exc:
            last_err = f"网络错误: {exc}"
            continue
        if audio:
            return bytes(audio), words
        last_err = last_err or "空音频"
    raise TTSError(f"SSE 流式合成失败。{last_err}")


def fish_tts_segment(
    text: str,
    settings: dict,
    reference_id: str = "",
    cancel: threading.Event | None = None,
) -> bytes:
    payload: dict = {
        "text": text,
        "chunk_length": 200,
    }
    ref = (reference_id or "").strip() or (settings.get("reference_id") or "").strip()
    if ref:
        payload["reference_id"] = ref
    try:
        speed = float(settings.get("speed") or 1.0)
    except (TypeError, ValueError):
        speed = 1.0
    if speed != 1.0:
        payload["prosody"] = {"speed": max(SPEED_MIN, min(SPEED_MAX, speed))}
    return _post_tts(payload, settings, cancel=cancel)


def fish_tts_dialogue(
    lines: list[tuple[str, str]],
    settings: dict,
    cancel: threading.Event | None = None,
) -> bytes:
    """多说话人单次生成：A/B 行转成 <|speaker:i|> 标记，reference_id 传声音数组。

    模型看到整段对话上下文，接话节奏、反应、停顿由模型自己演绎（NotebookLM 式）。
    """
    voice_a = (settings.get("reference_id") or "").strip()
    voice_b = (settings.get("reference_id_b") or "").strip()
    if not voice_a or not voice_b:
        raise TTSError("多说话人模式需要同时配置音色 A 与音色 B")

    parts = []
    for speaker, line in lines:
        idx = 0 if speaker == "a" else 1
        parts.append(f"<|speaker:{idx}|>{line}")
    payload: dict = {
        "text": "\n".join(parts),
        "reference_id": [voice_a, voice_b],
    }
    return _post_tts(payload, settings, cancel=cancel)


def test_connection(settings: dict) -> dict:
    """用最小请求验证 key（生成 1 秒音频）。"""
    if not real_api_key(settings):
        return {"ok": True, "mode": "dry_run", "message": "未配置 API key，当前为 dry-run 模式"}
    headers = {
        "Authorization": f"Bearer {real_api_key(settings)}",
        "model": settings.get("model") or "s2.1-pro-free",
        "Content-Type": "application/json",
    }
    try:
        r = httpx.post(
            FISH_TTS_URL,
            headers=headers,
            json={"text": "Hi.", "format": "mp3", "latency": "normal"},
            timeout=120,
        )
    except httpx.HTTPError as exc:
        return {"ok": False, "message": f"网络错误: {exc}"}
    if r.status_code == 200 and len(r.content) > 500:
        return {"ok": True, "mode": "live", "message": f"连接成功，模型 {headers['model']}"}
    if r.status_code in (401, 403):
        return {"ok": False, "message": f"鉴权失败({r.status_code})，请检查 API key"}
    return {"ok": False, "message": f"Fish API {r.status_code}: {(r.text or '')[:200]}"}


def _speaker_ref(settings: dict, speaker: str) -> str:
    """逐行回退路径的音色映射。Bruce 规则：回答（B 行）用男声 reference_id。"""
    answer_is_male = bool(settings.get("answer_voice_male", True))
    if speaker == "a":
        # 提问行：answer_voice_male 开 → 提问用女声 B
        return (
            (settings.get("reference_id_b") or "").strip()
            if answer_is_male
            else (settings.get("reference_id") or "").strip()
        )
    # 回答行
    return (
        (settings.get("reference_id") or "").strip()
        if answer_is_male
        else (settings.get("reference_id_b") or "").strip()
    )


def _synthesize_source(
    src: str,
    out_path: Path,
    settings: dict,
    force_monologue: bool = False,
    cancel: threading.Event | None = None,
) -> tuple[float, int, bool, str, list[dict] | None, list[dict]]:
    """核心合成函数：处理文本分段/多说话人合成并输出到 out_path。
    返回: (duration_sec, seg_count, is_dialogue, tts_mode, align_segments, align_words)

    alignment_segments：逐段实测的句级/行级跨度（单次合成模式为 None，由上层降级估算）。
    """
    dry = not real_api_key(settings) or bool(settings.get("dry_run"))
    try:
        seg_chars = int(settings.get("segment_chars") or 700)
    except (TypeError, ValueError):
        seg_chars = 700
    try:
        gap_ms = float(settings.get("gap_ms") or 350)
    except (TypeError, ValueError):
        gap_ms = 350.0

    voice_b = (settings.get("reference_id_b") or "").strip()
    dialogue = parse_dialogue(src) if (voice_b and not force_monologue) else None

    single_pass_bytes: bytes | None = None
    single_pass_words: list[dict] = []
    plan: list[tuple[str, str, float]] = []
    line_map: list[int] = []  # 每个计划段属于哪个对话行（独白为空）
    if dialogue and not dry:
        try:
            # Bruce 规则（answer_voice_male，默认开）：回答（B 行）必须是男声。
            # 男声=reference_id 放数组位 0 → 回答行发 speaker:0，提问行发 speaker:1。
            answer_is_male = bool(settings.get("answer_voice_male", True))
            q_idx, a_idx = (1, 0) if answer_is_male else (0, 1)
            tagged = "\n".join(
                f"<|speaker:{q_idx if spk == 'a' else a_idx}|>{body}" for spk, body in dialogue
            )
            single_pass_bytes, single_pass_words = fish_tts_sse(
                tagged, settings, is_dialogue=True, cancel=cancel
            )
        except TTSError:
            single_pass_bytes = None

    align_segments: list[dict] | None = None
    align_words: list[dict] = []
    seg_words_map: dict[int, list[dict]] = {}
    if dialogue and single_pass_bytes is None:
        prev_speaker = None
        for li, (speaker, line) in enumerate(dialogue):
            for j, seg in enumerate(split_text(line, seg_chars)):
                gap = 0.0
                if j > 0:
                    gap = gap_ms / 1000.0
                elif prev_speaker is not None:
                    gap = gap_ms / 1000.0 * 1.3  # 换人说话稍微多停一点
                plan.append((seg, _speaker_ref(settings, speaker), gap))
                line_map.append(li)
                prev_speaker = speaker
        seg_count = len(plan)
    elif single_pass_bytes is None:
        segments = split_text(src, seg_chars)
        plan = [(seg, "", gap_ms / 1000.0 if i else 0.0) for i, seg in enumerate(segments)]
        seg_count = len(segments)

    work = TMP_DIR / f"tts-{uuid.uuid4().hex}"
    work.mkdir(parents=True, exist_ok=True)
    try:
        if single_pass_bytes is not None:
            full_path = work / "dialogue-full.mp3"
            full_path.write_bytes(single_pass_bytes)
            entries = [{"path": full_path, "gap_before": 0.0}]
            seg_count = 1
            if single_pass_words and dialogue:
                mapped = alignment.map_words_to_lines(dialogue, single_pass_words)
                if mapped:
                    align_segments = [
                        {"text": body, "speaker": spk, "start": sp[0], "end": sp[1]}
                        for (spk, body), sp in zip(dialogue, mapped, strict=False)
                        if sp is not None
                    ]
                    align_words = single_pass_words
        else:
            entries = []
            seg_durations: list[float] = []
            for idx, (seg, ref, gap) in enumerate(plan):
                seg_path = work / f"seg-{idx:03d}.mp3"
                if cancel is not None and cancel.is_set():
                    raise TTSCancelled("已取消")
                if dry:
                    audio.make_tone(estimate_seconds(seg), seg_path)
                else:
                    seg_bytes, seg_words = fish_tts_sse(seg, settings, ref, cancel=cancel)
                    seg_path.write_bytes(seg_bytes)
                    if seg_words:
                        seg_words_map[idx] = seg_words
                seg_durations.append(audio.probe_duration(seg_path))
                entries.append({"path": seg_path, "gap_before": gap})
            seg_count = len(entries)

            # 实测跨度：段边界精确，段内句子按口语权重分配（误差不跨段累积）
            gaps = [e["gap_before"] for e in entries]
            spans = alignment.spans_from_measured_segments(seg_durations, gaps)
            if dialogue:
                line_spans = alignment.aggregate_dialogue_lines(line_map, spans)
                align_segments = [
                    {"text": body, "speaker": spk, **sp}
                    for (spk, body), sp in zip(dialogue, line_spans, strict=False)
                ]
            else:
                align_segments = []
                for idx, ((seg_text, _, _), sp) in enumerate(zip(plan, spans, strict=False)):
                    align_segments.extend(
                        alignment.distribute_sentences_within_segment(
                            alignment.split_sentences(seg_text), sp["start"], sp["end"]
                        )
                    )
                    for w in seg_words_map.get(idx, []):
                        align_words.append(
                            {"text": w["text"],
                             "start": round(sp["start"] + w["start"], 3),
                             "end": round(sp["start"] + w["end"], 3)}
                        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        audio.concat_mp3(entries, out_path)
        duration = audio.probe_duration(out_path)
        if duration <= 0:
            raise TTSError("生成的音频时长为 0，可能合成失败")

        # mp3 拼接帧填充近似线性累积 → 线性重标定到最终总时长
        if align_segments:
            align_segments = alignment.rescale_spans(align_segments, duration)

        # 广播级母带处理：Room Tone 注入 + 录音棚温暖 EQ + 动态压缩 + 立体声场展宽
        try:
            duration = mastering.apply_mastering(out_path, out_path, is_dialogue=bool(dialogue))
        except Exception:
            # 母带若因偶发原因失败，依然保留可用基础音频
            logger.warning("母带处理失败，保留基础音频: %s", out_path, exc_info=True)
    finally:
        for p in work.glob("*"):
            p.unlink(missing_ok=True)
        try:
            work.rmdir()
        except OSError:
            pass

    tts_mode = (
        "monologue"
        if not dialogue
        else ("dialogue_single_pass" if single_pass_bytes is not None else "dialogue_per_line")
    )
    return duration, seg_count, bool(dialogue), tts_mode, align_segments, align_words


def _synthesize_with_qa(
    src: str,
    out_path: Path,
    settings: dict,
    force_monologue: bool = False,
    cancel: threading.Event | None = None,
) -> tuple[tuple, dict, str, list[dict]]:
    """合成 + QA 门禁：异常音频隔离（.rejected.mp3）、去违规标签重试一次。
    追加返回 align_words。

    返回 (合成结果元组, QA 报告, 实际使用的源文本)。
    """
    dry = not real_api_key(settings) or bool(settings.get("dry_run"))
    result = _synthesize_source(src, out_path, settings, force_monologue, cancel=cancel)
    effective_src = src
    align_words = result[5] or []
    # 时长必须探测最终产物（母带/外部因素可能改变它），不能用合成时的返回值
    report = audioqa.run_qa(out_path, src, duration_sec=None, skip_vad=dry)
    if report["verdict"] == "retry":
        # 恢复路径：剥离全部标签（含白名单内的 [chuckle]——失控笑声最常见来源）
        cleaned, removed = audioqa.strip_all_tags(src)
        if removed and cleaned.strip() and cleaned != src:
            logger.warning("QA 不通过，隔离并去标签重试: %s removed=%s", out_path.name, removed)
            quarantine = out_path.with_suffix(".rejected.mp3")
            out_path.replace(quarantine)
            try:
                result = _synthesize_source(
                    cleaned, out_path, settings, force_monologue, cancel=cancel
                )
                effective_src = cleaned
                align_words = result[5] or []
                report = audioqa.run_qa(out_path, cleaned, duration_sec=None, skip_vad=dry)
            except Exception:
                # 重试失败：恢复被隔离的原始音频，记录但不再阻断
                quarantine.replace(out_path)
                report["retry_error"] = "重试合成失败，已恢复原始音频"
    return result, report, effective_src, align_words


def _save_track_outputs(
    ipath: Path,
    track: str,
    src: str,
    out_audio: Path,
    dur: float,
    align_segments: list[dict] | None,
    words: list[dict] | None = None,
    speaker_a: str = "Alex",
    speaker_b: str = "Mia",
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
) -> dict:
    """为单个条目生成音频。
    track: 'monologue' | 'podcast' | 'all' | 'default'
    """
    if track not in VALID_TRACKS:
        raise TTSError(f"未知轨道: {track}（可选 {VALID_TRACKS}）")
    settings = load_settings()
    dry = not real_api_key(settings) or bool(settings.get("dry_run"))
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

    if track in ("all", "monologue"):
        src_mono, field_mono = library.get_track_source_text(full, "monologue")
        if src_mono:
            out_mono = ipath / "audio_monologue.mp3"
            res = _synthesize_with_qa(
                src_mono, out_mono, settings, force_monologue=True, cancel=cancel
            )
            (dur, segs, is_diag, mode, seg_spans, seg_words), qa_report, eff_src, align_words = res
            meta_updates["duration_sec_monologue"] = round(dur, 2)
            meta_updates["qa_monologue"] = qa_report["verdict"]
            audioqa.save_qa_report(qa_report, ipath / "qa_monologue.json")
            results["monologue"] = {
                "duration_sec": round(dur, 2), "segments": segs, "mode": mode,
                "qa": qa_report["verdict"],
            }
            _save_track_outputs(ipath, "monologue", eff_src, out_mono, dur, seg_spans, seg_words)
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
                src_pod, out_pod, settings, force_monologue=False, cancel=cancel
            )
            (dur, segs, is_diag, mode, seg_spans, seg_words), qa_report, eff_src, align_words = res
            meta_updates["duration_sec_podcast"] = round(dur, 2)
            meta_updates["qa_podcast"] = qa_report["verdict"]
            audioqa.save_qa_report(qa_report, ipath / "qa_podcast.json")
            results["podcast"] = {
                "duration_sec": round(dur, 2), "segments": segs, "mode": mode,
                "qa": qa_report["verdict"],
            }
            pod_mode = "sse" if (mode == "dialogue_single_pass" and seg_words) else "measured"
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
        res = _synthesize_with_qa(src_def, out_def, settings, cancel=cancel)
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
        def_mode = "sse" if (mode == "dialogue_single_pass" and align_words) else "measured"
        _save_track_outputs(
            ipath, track_key, eff_src, out_def, dur, seg_spans, align_words, mode=def_mode
        )

    library.update_item_meta(topic_id, item_id, **meta_updates)
    return {
        "ok": True,
        "track": track,
        "results": results,
        "dry_run": dry,
    }
