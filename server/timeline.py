"""时间戳生成与对齐引擎 (server/timeline.py)。

生成毫秒级精度的句子/话轮起止时间戳 (Live Transcript Timeline)，支撑前端卡拉OK式高亮滚动与点击跳转。
"""
import json
import re
from pathlib import Path

from .audio import probe_duration
from .config import atomic_write_text


def generate_timeline_for_dialogue(
    script_text: str,
    total_audio_path: Path,
    speaker_a_name: str = "Alex",
    speaker_b_name: str = "Mia",
) -> list[dict]:
    """为双人对话生成精确时间轴序列。"""
    from .tts import parse_dialogue  # 延迟导入避免 tts ↔ timeline 循环依赖

    dialogue = parse_dialogue(script_text)
    if not dialogue or not total_audio_path.exists():
        return []

    total_duration = probe_duration(total_audio_path)
    if total_duration <= 0:
        return []

    # 预处理每一行的纯文本与停顿权重
    items = []
    total_weight = 0.0

    for idx, (spk, body) in enumerate(dialogue):
        # 移除标签计算发音长度
        clean_text = re.sub(r"\[.*?\]", "", body).strip()
        # 汉字权重加权 (1个汉字约等于3.5个英文字符的时长)
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", clean_text))
        ascii_count = len(re.findall(r"[a-zA-Z0-9]", clean_text))

        weight = max(1.0, ascii_count + (cjk_count * 3.6))

        # 标签额外停顿
        if "[slight pause]" in body or "..." in body or "—" in body:
            weight += 4.5
        if "[chuckle]" in body or "[sigh]" in body:
            weight += 6.0

        items.append({
            "id": idx,
            "speaker": spk.upper(),
            "name": speaker_a_name if spk.lower() == "a" else speaker_b_name,
            "raw_text": body,
            "clean_text": clean_text,
            "weight": weight,
        })
        total_weight += weight

    # 根据总时长按权重分配起止时间
    cur_time = 0.0
    timeline = []
    n = len(items)

    for i, it in enumerate(items):
        seg_dur = (it["weight"] / total_weight) * total_duration
        start = round(cur_time, 2)
        end = round(cur_time + seg_dur, 2)
        if i == n - 1:
            end = round(total_duration, 2)

        timeline.append({
            "id": it["id"],
            "speaker": it["speaker"],
            "name": it["name"],
            "text": it["raw_text"],
            "start": start,
            "end": end,
            "duration": round(end - start, 2),
        })
        cur_time = end

    return timeline


def generate_timeline_for_monologue(
    script_text: str,
    total_audio_path: Path,
    speaker_name: str = "Alex",
) -> list[dict]:
    """为单人独白段落生成时间轴序列。"""
    if not script_text or not total_audio_path.exists():
        return []

    total_duration = probe_duration(total_audio_path)
    if total_duration <= 0:
        return []

    # 按句子和段落切分
    paragraphs = [p.strip() for p in script_text.replace("\r\n", "\n").split("\n") if p.strip()]
    raw_sentences = []
    for p in paragraphs:
        # 按标点切分单句
        sents = re.split(r"(?<=[.!?。！？])\s+", p)
        for s in sents:
            s = s.strip()
            if s:
                raw_sentences.append(s)

    if not raw_sentences:
        raw_sentences = [script_text.strip()]

    items = []
    total_weight = 0.0
    for idx, s in enumerate(raw_sentences):
        clean_text = re.sub(r"\[.*?\]", "", s).strip()
        weight = max(1.0, float(len(clean_text)))
        if "[slight pause]" in s or "..." in s or "—" in s:
            weight += 4.5
        items.append({"id": idx, "text": s, "weight": weight})
        total_weight += weight

    cur_time = 0.0
    timeline = []
    n = len(items)
    for i, it in enumerate(items):
        seg_dur = (it["weight"] / total_weight) * total_duration
        start = round(cur_time, 2)
        end = round(cur_time + seg_dur, 2)
        if i == n - 1:
            end = round(total_duration, 2)

        timeline.append({
            "id": it["id"],
            "speaker": "A",
            "name": speaker_name,
            "text": it["text"],
            "start": start,
            "end": end,
            "duration": round(end - start, 2),
        })
        cur_time = end

    return timeline


def save_timeline(timeline: list[dict], file_path: Path) -> None:
    atomic_write_text(file_path, json.dumps(timeline, ensure_ascii=False, indent=2))


def load_timeline(file_path: Path) -> list[dict]:
    if file_path.exists():
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def get_or_create_timeline(topic_id: str, item_id: str, track: str = "podcast") -> dict:
    """时间轴端点主入口。返回 {"lines", "words", "mode"}。

    优先级：alignment_{track}.json（带文本/音频指纹校验，M02 实测数据 + SSE 逐词）
    → 旧版 timeline 缓存 → 按权重估算生成并缓存。
    """
    from . import alignment, library

    ipath = library.item_path(topic_id, item_id)
    full = library.get_item_full(topic_id, item_id)

    cache = (
        ipath / f"timeline_{track}.json"
        if track in ("monologue", "podcast")
        else ipath / "timeline_podcast.json"
    )

    audio_path = library.resolve_audio_file(ipath, track)
    src, _ = library.get_track_source_text(full, track)
    if not src:
        src, _ = library.get_track_source_text(full, "default")

    # 1) 实测 alignment（指纹不匹配 = 文本或音频已变 → 自动失效）
    if src and audio_path:
        align_file = (
            ipath / f"alignment_{track}.json"
            if track in ("monologue", "podcast")
            else ipath / "alignment_podcast.json"
        )
        doc = alignment.load_alignment(align_file, expect_text=src, expect_audio=audio_path)
        if doc:
            return {
                "lines": alignment.derive_timeline(doc),
                "words": doc.get("words") or [],
                "mode": doc.get("mode") or "measured",
            }

    # 2) 旧版缓存
    cached = load_timeline(cache)
    if cached:
        return {"lines": cached, "words": [], "mode": "estimated"}

    if not audio_path or not src:
        return {"lines": [], "words": [], "mode": "estimated"}

    # 3) 估算回退
    if track == "monologue":
        tl = generate_timeline_for_monologue(src, audio_path)
    else:
        tl = generate_timeline_for_dialogue(src, audio_path)
        tl = tl or generate_timeline_for_monologue(src, audio_path)
    if tl:
        save_timeline(tl, cache)
    return {"lines": tl, "words": [], "mode": "estimated"}
