"""对齐真相层 (M02)：真实测量的句级时间轴，替代字符估算。

三类数据来源（按可信度排序）：
- measured：逐段合成时用 ffprobe 实测每段时长，段内句子按字符比例分配（误差不跨段累积）
- sse：Fish /v1/tts/stream/with-timestamp 逐词时间戳（网络可用时对单次合成轨启用）
- estimated：按字符权重全局估算（最后回退，前端可通过 mode 标记降级提示）

alignment.json 携带文本指纹 + 音频签名，读时校验；文本编辑或音频重生成自动失效。
"""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

VERSION = 1


# ---------------------------------------------------------------- 指纹

def text_fingerprint(text: str) -> str:
    """规范化（统一换行、去首尾空白）后哈希；同义空白差异不改变指纹。"""
    norm = (text or "").replace("\r\n", "\n").strip()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def audio_signature(audio_path: Path) -> str:
    """音频签名 = 文件大小 + 修改时间秒。重生成即变化。"""
    try:
        st = audio_path.stat()
        return f"{st.st_size}:{int(st.st_mtime)}"
    except OSError:
        return "missing"


# ---------------------------------------------------------------- 跨度数学

def spans_from_measured_segments(
    seg_durations: list[float], gaps: list[float]
) -> list[dict]:
    """逐段实测时长 + 段前 gap → 每段的绝对 [start, end]。"""
    spans: list[dict] = []
    cur = 0.0
    for dur, gap in zip(seg_durations, gaps, strict=False):
        cur += gap
        start = round(cur, 2)
        end = round(cur + dur, 2)
        spans.append({"start": start, "end": end})
        cur += dur
    return spans


def rescale_spans(spans: list[dict], total: float) -> list[dict]:
    """把实测跨度线性重标定到最终音频总时长。

    mp3 逐段拼接的帧填充/编码器延迟按段数近似线性累积，线性缩放恰好修正这类误差。
    """
    if not spans or total <= 0:
        return spans
    raw_end = spans[-1]["end"]
    if raw_end <= 0 or abs(raw_end - total) < 0.01:
        return spans
    scale = total / raw_end
    out = []
    for s in spans:
        out.append(
            {
                **s,
                "start": round(s["start"] * scale, 2),
                "end": round(s["end"] * scale, 2),
            }
        )
    return out


_SENT_SPLIT_RE = re.compile(r"(?<=[.!?。！？…])\s+")
_TAG_RE = re.compile(r"\[.*?\]")


def split_sentences(text: str) -> list[str]:
    """把块文本切成句子（保留 [tag] 原文）。"""
    parts = []
    for para in (text or "").replace("\r\n", "\n").split("\n"):
        for s in _SENT_SPLIT_RE.split(para.strip()):
            s = s.strip()
            if s:
                parts.append(s)
    return parts or ([text.strip()] if (text or "").strip() else [])


def _speak_weight(sentence: str) -> float:
    clean = _TAG_RE.sub("", sentence)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", clean))
    ascii_len = len(re.findall(r"[a-zA-Z0-9]", clean))
    return max(1.0, ascii_len + cjk * 3.6)


def distribute_sentences_within_segment(
    sentences: list[str], start: float, end: float
) -> list[dict]:
    """块内多句：按口语权重分配块时长，误差限制在块内。"""
    if not sentences:
        return []
    total_w = sum(_speak_weight(s) for s in sentences)
    dur = max(0.0, end - start)
    out = []
    cur = start
    for i, s in enumerate(sentences):
        if i == len(sentences) - 1:
            s_start, s_end = round(cur, 2), round(end, 2)
        else:
            w = _speak_weight(s)
            s_start = round(cur, 2)
            s_end = round(cur + dur * (w / total_w), 2)
        out.append(
            {"text": s, "start": s_start, "end": s_end, "duration": round(s_end - s_start, 2)}
        )
        cur = s_end
    return out


def aggregate_dialogue_lines(line_map: list[int], spans: list[dict]) -> list[dict]:
    """把多段聚合成对话行：行跨度 = 首段 start → 末段 end。"""
    n_lines = (max(line_map) + 1) if line_map else 0
    lines = []
    for li in range(n_lines):
        idxs = [i for i, m in enumerate(line_map) if m == li]
        if not idxs:
            continue
        lines.append({"start": spans[idxs[0]]["start"], "end": spans[idxs[-1]]["end"]})
    return lines


# ---------------------------------------------------------------- 文档模型

def build_alignment_doc(
    mode: str,
    source_text: str,
    audio_path: Path,
    segments: list[dict],
    track: str = "default",
    words: list[dict] | None = None,
) -> dict:
    return {
        "version": VERSION,
        "track": track,
        "mode": mode,  # measured | sse | estimated
        "text_fingerprint": text_fingerprint(source_text),
        "audio_signature": audio_signature(audio_path),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "segments": segments,
        **({"words": words} if words else {}),
    }


def save_alignment(doc: dict, file_path: Path) -> None:
    from .config import atomic_write_text

    atomic_write_text(file_path, json.dumps(doc, ensure_ascii=False, indent=2))


def load_alignment(
    file_path: Path,
    expect_text: str | None = None,
    expect_audio: Path | None = None,
) -> dict | None:
    """读取并校验；指纹/签名不匹配或损坏 → None（视为失效）。"""
    if not file_path.exists():
        return None
    try:
        doc = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(doc, dict) or not doc.get("segments"):
        return None
    if expect_text is not None and doc.get("text_fingerprint") != text_fingerprint(expect_text):
        return None
    if expect_audio is not None and doc.get("audio_signature") != audio_signature(expect_audio):
        return None
    return doc


# ---------------------------------------------------------------- 派生（前端兼容时间轴）

def derive_timeline(
    doc: dict, speaker_a_name: str = "Alex", speaker_b_name: str = "Mia"
) -> list[dict]:
    """alignment 文档 → 旧版 timeline 形状 [{id,speaker,name,text,start,end,duration}]。"""
    tl = []
    for i, seg in enumerate(doc.get("segments", [])):
        speaker = (seg.get("speaker") or "a").lower()
        start, end = seg.get("start", 0.0), seg.get("end", 0.0)
        tl.append(
            {
                "id": i,
                "speaker": speaker.upper(),
                "name": speaker_a_name if speaker == "a" else speaker_b_name,
                "text": seg.get("text", ""),
                "start": start,
                "end": end,
                "duration": round(end - start, 2),
                "mode": doc.get("mode", "estimated"),
            }
        )
    return tl


# ---------------------------------------------------------------- SSE 解析（单次合成轨的逐词层）

def parse_sse_events(events: list[str], chunk_offsets: list[float] | None = None) -> dict | None:
    """解析 Fish with-timestamp SSE 流 → {words, total_duration}。

    容错设计：字段名存在多种文档变体（audio/audio_base64、alignment.segments 等），
    网络恢复后用 scripts/probe_fish_sse.py 实测校准；解析失败返回 None 而非抛错。
    """
    words: list[dict] = []
    total = 0.0
    for line in events:
        if not line.startswith("data:"):
            continue
        try:
            data = json.loads(line[5:].strip())
        except (json.JSONDecodeError, ValueError):
            continue
        total = max(total, float(data.get("audio_duration") or 0.0))
        align = data.get("alignment") or {}
        segs = align.get("segments") or data.get("segments") or []
        base = float(data.get("chunk_audio_offset_sec") or 0.0)
        for w in segs:
            t = (w.get("text") or "").strip()
            if not t:
                continue
            words.append(
                {
                    "text": t,
                    "start": round(base + float(w.get("start") or 0.0), 3),
                    "end": round(base + float(w.get("end") or 0.0), 3),
                }
            )
    if not words:
        return None
    words.sort(key=lambda w: w["start"])
    return {"words": words, "total_duration": total}
