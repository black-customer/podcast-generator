"""逐句学习材料：播报文本绑定、原话证据与安全音频定位。"""

import hashlib
import json
import re
import threading
from functools import lru_cache
from pathlib import Path

from . import library, rewrite, timeline
from .config import DATA_DIR, atomic_write_text, load_settings

VERSION = 1
MATERIAL_FILE = "study_material.json"
LEGACY_UPGRADE_FILE = DATA_DIR / "study_private" / "legacy_study_upgrades.json"
_ACTIVE: set[tuple[str, str]] = set()
_ACTIVE_LOCK = threading.Lock()

MATERIAL_GUIDANCE = """The material object contains complete_chinese and sentences.
Each sentence has zh, en, explanation, usage and optionally original_error {quote, issue,
correction}. Copy every supplied English answer sentence exactly and in order into en.
Explain useful grammar and collocations in
Chinese. The complete Chinese meaning and each zh must preserve the learner's original meaning;
do not invent experiences. Keep the reference achievable, not needlessly advanced. Optionally add
outline and groups arrays of {label: Chinese content cue, indices: zero-based sentence indices};
use only supplied sentence meanings. For Part 3 add one related English followup question.
Each sentence may have gap_kind: text_supported_error, explicit_gap, or refinement.
Only report an original_error when an exact English quote from the raw
answer proves a real grammatical or spelling error. Never treat a valid alternative wording as an
error. Chinese input is not evidence of an English error. Do not infer pronunciation or scores."""
MATERIAL_GUIDANCE += """ Include a key_chunk copied verbatim from each English sentence: a useful
contiguous phrase of 2–12 English words the learner can reuse. For a supported error, set
category to one of plural, tense, subject_verb_agreement, article, preposition, word_order,
conjunction, collocation, or other."""
MATERIAL_GUIDANCE += """ When a distinct meaning in the Chinese intent was missing from the
spoken attempt, mark the sentence that expresses it with gap_kind: explicit_gap. Use key_chunk
for the expression that fills that gap. Optionally add transfer_example, one English sentence
using the exact key_chunk in a different situation without inventing a detail about the learner."""
MATERIAL_GUIDANCE += """ Optionally add short Chinese prompts for a reusable phrase:
trigger_context for a situation that calls for it, disambiguator for what makes it different,
feynman_hook for a plain-language explanation, and transfer_prompt_zh for a new situation to try.
Use generic situations; never add claims about the learner."""
MATERIAL_GUIDANCE += """ Include coach_summary with a Chinese headline (20–60 characters),
strengths (1–2 short Chinese strings tied to what the learner actually said), and focus_points
(1–3 short Chinese strings about what to practise next). Do not infer speech quality or scores."""
SYSTEM_PROMPT = (
    "You prepare faithful Chinese-English study materials for an IELTS learner. "
    "Return the material object as JSON with no surrounding text. " + MATERIAL_GUIDANCE
)

CHUNK_CUE_FIELDS = ("trigger_context", "disambiguator", "feynman_hook", "transfer_prompt_zh")
LEGACY_CUE_FIELDS = ("key_chunk", *CHUNK_CUE_FIELDS, "transfer_example")

ERROR_LABELS = {"plural": "单复数", "tense": "时态", "subject_verb_agreement": "主谓一致",
                "article": "冠词", "preposition": "介词", "word_order": "语序",
                "conjunction": "连词", "collocation": "搭配", "other": "其他语法或用词"}


class MaterialError(ValueError):
    """材料不完整或无法与实际回答核对。"""


def _answer_sentences(text: str) -> list[str]:
    from .alignment import split_sentences
    from .tts import parse_dialogue

    dialogue = parse_dialogue(text or "") or []
    answer = []
    for speaker, body in dialogue:
        if speaker.lower() == "b":
            answer.extend(split_sentences(body))
    return [part.strip() for part in answer if part.strip()]


def source_fingerprint(texts: dict) -> str:
    values = [texts.get(key) or "" for key in (
        "original_answer", "natural_english", "podcast_text", "podcast_script"
    )]
    raw = json.dumps(values, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _spoken_words(text: str) -> list[str]:
    return re.findall(r"[a-z]+(?:['’][a-z]+)?", re.sub(r"\[[^\]]*\]", "", text).lower())


def _effective_original(texts: dict) -> str:
    """原始回答：original_answer → chinese → natural_english（旧语料回退）。"""
    return rewrite.original_answer_of(texts).strip()


def expected_sentences(texts: dict) -> list[str]:
    visible = _answer_sentences(texts.get("podcast_text") or "")
    if not visible:
        raise MaterialError("缺少可核对的 B 回答台词")
    script = texts.get("podcast_script") or ""
    if script and _spoken_words(" ".join(visible)) != _spoken_words(
        " ".join(_answer_sentences(script))
    ):
        raise MaterialError("可见回答与实际播报稿词序不同，需先复核音频文本")
    return visible


def validate_material(material: dict, texts: dict, *, require_chunks: bool = False) -> dict:
    if not isinstance(material, dict):
        raise MaterialError("逐句材料必须是 JSON 对象")
    original = _effective_original(texts)
    if not original:
        raise MaterialError("缺少原始回答，请先补齐再准备学习材料")
    expected = expected_sentences(texts)
    chinese = material.get("complete_chinese")
    rows = material.get("sentences")
    if not isinstance(chinese, str) or not chinese.strip():
        raise MaterialError("缺少完整中文原意")
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise MaterialError(f"逐句材料须按播报顺序提供 {len(expected)} 句")
    cleaned = []
    for index, (row, en) in enumerate(zip(rows, expected, strict=True), 1):
        if not isinstance(row, dict):
            raise MaterialError(f"第 {index} 句格式错误")
        for field in ("zh", "en", "explanation", "usage"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise MaterialError(f"第 {index} 句缺少 {field}")
        if row["en"].strip() != en:
            raise MaterialError(f"第 {index} 句英文与实际 B 回答台词不一致")
        entry = {field: row[field].strip() for field in (
            "zh", "en", "explanation", "usage"
        )}
        for field in CHUNK_CUE_FIELDS:
            value = row.get(field)
            if isinstance(value, str) and 0 < len(value.strip()) <= 240:
                entry[field] = value.strip()
        chunk = row.get("key_chunk")
        if chunk is not None or require_chunks:
            from .speech_worker import matched_chunks, tokens

            if (not isinstance(chunk, str) or re.search(r"[\u3400-\u9fff]", chunk) or
                    not 2 <= len(tokens(chunk)) <= 12 or not matched_chunks(en, [chunk])):
                raise MaterialError(f"第 {index} 句的语块须是原句中连续的 2–12 个英文词")
            entry["key_chunk"] = chunk.strip()
            example = row.get("transfer_example")
            if (isinstance(example, str) and 0 < len(example.strip()) <= 240
                    and not re.search(r"[\[\]\n\r\u3400-\u9fff]", example)
                    and example.strip() != en and matched_chunks(example, [chunk])):
                entry["transfer_example"] = example.strip()
        error = row.get("original_error")
        kind = row.get("gap_kind")
        if kind is not None:
            if kind not in {"text_supported_error", "explicit_gap", "refinement"}:
                raise MaterialError("缺口分类错误")
            if kind == "text_supported_error" and not error:
                raise MaterialError("个人错误缺少原话证据")
            entry["gap_kind"] = kind
        if error is not None:
            if not isinstance(error, dict) or any(
                not isinstance(error.get(key), str) or not error[key].strip()
                for key in ("quote", "issue", "correction")
            ):
                raise MaterialError(f"第 {index} 句个人错误缺少原话、问题或改法")
            quote = error["quote"].strip()
            if re.search(r"发音|口音|重音|语调|评分|pronunciation|intonation|accent|score",
                         error["issue"], re.I):
                raise MaterialError("文字不能证明发音或评分问题")
            if quote not in original or len(_spoken_words(quote)) < 2:
                raise MaterialError(f"第 {index} 句个人错误没有可核对的原始英文证据")
            entry["original_error"] = {
                key: error[key].strip() for key in ("quote", "issue", "correction")
            }
            category = error.get("category")
            if isinstance(category, str) and category in ERROR_LABELS:
                entry["original_error"]["category"] = category
        cleaned.append(entry)
    result = {
        "version": VERSION,
        "source_fingerprint": source_fingerprint(texts),
        "complete_chinese": chinese.strip(),
        "sentences": cleaned,
    }
    if "coach_summary" in material:
        summary = material["coach_summary"]
        if not isinstance(summary, dict) or not isinstance(summary.get("headline"), str):
            raise MaterialError("老师总评缺少标题")
        headline = summary["headline"].strip()
        if not 20 <= len(headline) <= 60:
            raise MaterialError("老师总评标题须为 20–60 字")
        coach = {"headline": headline}
        for field, limit in (("strengths", 2), ("focus_points", 3)):
            entries = summary.get(field)
            if (not isinstance(entries, list) or not 1 <= len(entries) <= limit
                    or any(not isinstance(s, str) or not 1 <= len(s.strip()) <= 240
                           for s in entries)):
                raise MaterialError("老师总评需要有效的亮点与练习要点")
            coach[field] = [s.strip() for s in entries]
        result["coach_summary"] = coach
    gaps = [{"sentence_index": index, "key_chunk": row["key_chunk"]}
            for index, row in enumerate(cleaned)
            if row.get("gap_kind") == "explicit_gap" and row.get("key_chunk")]
    if gaps:
        result["lexical_gaps"] = gaps
    for name in ("outline", "groups"):
        if name in material:
            blocks = material[name]
            if not isinstance(blocks, list) or len(blocks) > len(expected):
                raise MaterialError("内容提纲格式错误")
            for block in blocks:
                if (not isinstance(block, dict) or not isinstance(block.get("label"), str)
                        or not block["label"].strip()):
                    raise MaterialError("内容提纲缺少提示")
                indices = block.get("indices")
                if not isinstance(indices, list) or not indices or any(
                    isinstance(n, bool) or not isinstance(n, int) or not 0 <= n < len(expected)
                    for n in indices
                ) or len(set(indices)) != len(indices):
                    raise MaterialError("内容提纲必须引用实际句子")
            result[name] = blocks
    if "followup" in material:
        followup = material["followup"]
        if (not isinstance(followup, str) or not followup.strip() or len(followup) > 1000
                or re.search(r"[\u4e00-\u9fff]", followup)):
            raise MaterialError("追问需要有效英文问题")
        result["followup"] = followup.strip()
    return result


def save_material(topic_id: str, item_id: str, material: dict, *,
                  require_audio: bool = True) -> dict:
    with library.LIB_LOCK:
        path = library.item_path(topic_id, item_id)
        if not path.exists():
            raise FileNotFoundError("条目不存在")
        if require_audio and library.resolve_audio_file(path, "podcast") is None:
            raise MaterialError("播客音频尚未完成")
        result = validate_material(material, library.read_item_texts(path))
        atomic_write_text(path / MATERIAL_FILE, json.dumps(result, ensure_ascii=False, indent=2))
        meta = library.load_meta(path)
        meta["study_status"] = "ready"
        meta["study_error"] = ""
        meta["study_attempt_fingerprint"] = ""
        library.save_meta(path, meta)
        library.invalidate_item_cache(path)
        return result


def set_status(
    topic_id: str, item_id: str, status: str, error: str = "", fingerprint: str | None = None
) -> None:
    if status not in ("preparing", "failed"):
        raise ValueError("非法材料状态")
    with library.LIB_LOCK:
        path = library.item_path(topic_id, item_id)
        if not path.exists():
            raise FileNotFoundError("条目不存在")
        if fingerprint is None:
            fingerprint = source_fingerprint(library.read_item_texts(path))
        library.update_item_meta(
            topic_id, item_id, study_status=status, study_error=error[:300],
            study_attempt_fingerprint=fingerprint,
        )


def generate_material(topic_id: str, item_id: str, *, cancel: threading.Event | None = None,
                      require_chunks: bool = False) -> dict:
    """独立的一次文本模型调用；调用失败只改变材料状态。"""
    full = library.get_item_full(topic_id, item_id)
    original = _effective_original(full)
    if not original:
        raise MaterialError("缺少原始回答，请先补齐")
    if not full.get("has_audio_podcast"):
        raise MaterialError("播客音频尚未完成")
    sentences = expected_sentences(full)
    fingerprint = source_fingerprint(full)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps({
            "question": full.get("question"),
            "ielts_part": library.load_meta(library.item_path(topic_id, item_id)).get("ielts_part"),
            "original_answer": original,
            "exact_spoken_sentences": sentences,
        }, ensure_ascii=False)},
    ]
    from . import study_progress
    private = study_progress.get_progress(topic_id, item_id)
    inputs = (private.get("training") or {}).get("inputs") or private.get("training_inputs")
    if inputs:
        messages.append({"role": "user", "content": json.dumps({
            "supplemental_intent_not_spoken": inputs.get("intent", ""),
            "external_feedback_unverified": inputs.get("feedback", ""),
            "instruction": "Neither field is evidence of an error in the raw English answer.",
        }, ensure_ascii=False)})
    settings = load_settings()
    if settings.get("dry_run"):
        raise MaterialError("dry-run 不调用文本模型；可用 Agent 材料命令准备")
    content = rewrite._chat(settings, messages, cancel)
    try:
        result = rewrite._extract_json(content)
        validate_material(result, full, require_chunks=require_chunks)
    except (MaterialError, rewrite.RewriteError) as exc:
        # 模型偶发漏字段、结构漂移或直接输出非 JSON：带错误清单重问一次（同 rewrite 修复模式）
        messages.append({"role": "assistant", "content": content[:4000]})
        messages.append({"role": "user", "content": (
            f"上次输出存在以下问题：{exc}。请只返回修正后的完整 JSON 对象，"
            "仍须包含 complete_chinese 与逐句 sentences，不要添加其他文字。")})
        content = rewrite._chat(settings, messages, cancel)
        result = rewrite._extract_json(content)
        validate_material(result, full, require_chunks=require_chunks)
    with library.LIB_LOCK:
        if fingerprint != source_fingerprint(library.get_item_full(topic_id, item_id)):
            raise MaterialError("准备期间回答已变化，请重新准备材料")
        return save_material(topic_id, item_id, result)


def prepare_async(topic_id: str, item_id: str) -> bool:
    """返回是否新启动；重复点击不产生额外计费调用。"""
    key = (topic_id, item_id)
    with _ACTIVE_LOCK:
        if key in _ACTIVE:
            return False
        _ACTIVE.add(key)
    try:
        attempt_fingerprint = source_fingerprint(library.read_item_texts(
            library.item_path(topic_id, item_id)
        ))
        set_status(topic_id, item_id, "preparing", fingerprint=attempt_fingerprint)
    except Exception:
        with _ACTIVE_LOCK:
            _ACTIVE.discard(key)
        raise

    def run() -> None:
        try:
            generate_material(topic_id, item_id)
        except Exception as exc:
            try:
                set_status(topic_id, item_id, "failed", str(exc), attempt_fingerprint)
            except FileNotFoundError:
                pass
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE.discard(key)

    threading.Thread(target=run, name="study-material", daemon=True).start()
    return True


@lru_cache(maxsize=2)
def _read_upgrades(path: Path, modified: int, size: int) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != 1 or not isinstance(data.get("items"), dict):
        raise MaterialError("历史语块文件格式不受支持")
    return data["items"]


def legacy_upgrades(*, strict: bool = False) -> dict:
    try:
        stat = LEGACY_UPGRADE_FILE.stat()
        return _read_upgrades(LEGACY_UPGRADE_FILE, stat.st_mtime_ns, stat.st_size)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, AttributeError):
        if strict:
            raise MaterialError("历史语块文件无法读取，请先核对本机升级记录") from None
        return {}


def _legacy_key(topic_id: str, item_id: str) -> str:
    return f"{topic_id}/{item_id}"


def _legacy_source(topic_id: str, item_id: str) -> bool:
    path = library.item_path(topic_id, item_id)
    tags = library.load_meta(path).get("tags") or []
    return ("bruce-真实回答" in topic_id or "bruce-真实回答" in tags
            or (path / "original_answer.txt").is_file())


def export_legacy_study_upgrade() -> dict:
    items = []
    with library.LIB_LOCK:
        for path in sorted(library.TOPICS_DIR.glob(f"*/items/*/{MATERIAL_FILE}")):
            topic_id, item_id = path.parents[2].name, path.parent.name
            if not _legacy_source(topic_id, item_id):
                continue
            found = get_material(topic_id, item_id)
            if found["status"] != "ready":
                continue
            material = found["material"]
            rows = [{"sentence_index": index, **row}
                    for index, row in enumerate(material["sentences"]) if not row.get("key_chunk")]
            if rows:
                items.append({"topic_id": topic_id, "item_id": item_id,
                              "source_fingerprint": material["source_fingerprint"],
                              "sentences": rows})
    return {"version": 1, "guidance": (
        "保留条目编号、文本指纹和句子序号。逐句只交回 key_chunk、四项语境提示和 "
        "transfer_example。语块须连续出现在原句和迁移例句里，迁移需要使用另一个具体场景。"
    ), "items": items}


def apply_legacy_study_upgrade(payload: dict) -> dict:
    if (not isinstance(payload, dict) or payload.get("version") != 1
            or not isinstance(payload.get("items"), list) or not payload["items"]):
        raise MaterialError("历史语块提交需要版本 1 和非空条目列表")
    with library.LIB_LOCK:
        upgrades = legacy_upgrades(strict=True).copy()
        seen = set()
        count = 0
        for item in payload["items"]:
            if not isinstance(item, dict):
                raise MaterialError("历史条目格式错误")
            tid, iid = item.get("topic_id"), item.get("item_id")
            patches = item.get("sentences")
            if (not all(isinstance(key, str) and library._safe_id(key) for key in (tid, iid))
                    or not isinstance(patches, list) or not patches
                    or not _legacy_source(tid, iid)):
                raise MaterialError("历史条目标识或句子列表无效")
            key = _legacy_key(tid, iid)
            if key in seen:
                raise MaterialError("同一历史条目不可重复提交")
            seen.add(key)
            found = get_material(tid, iid, _apply_upgrades=False)
            material = found.get("material", {})
            fp = item.get("source_fingerprint")
            if found["status"] != "ready" or not fp or fp != material["source_fingerprint"]:
                raise MaterialError("历史材料已变化，请重新导出")
            rows = material["sentences"]
            previous = upgrades.get(key, {})
            merged = (previous.get("sentences", {}).copy()
                      if previous.get("fingerprint") == fp else {})
            indices = set()
            for patch in patches:
                if not isinstance(patch, dict):
                    raise MaterialError("历史句子格式错误")
                index = patch.get("sentence_index")
                if (type(index) is not int or not 0 <= index < len(rows) or index in indices
                        or rows[index].get("key_chunk")):
                    raise MaterialError("历史句子序号无效、重复或已包含语块")
                indices.add(index)
                if set(patch) != {"sentence_index", *LEGACY_CUE_FIELDS} or any(
                    not isinstance(patch[field], str) or not 0 < len(patch[field].strip()) <= 240
                    for field in LEGACY_CUE_FIELDS
                ):
                    raise MaterialError("历史句子只能补齐语块、四项情境提示和迁移示范")
                merged[str(index)] = {field: patch[field].strip() for field in LEGACY_CUE_FIELDS}
            candidate = {**material, "sentences": [
                {**row, **merged.get(str(index), {})} for index, row in enumerate(rows)]}
            texts = library.read_item_texts(library.item_path(tid, iid))
            checked = validate_material(candidate, texts)
            from .captures import make_cloze

            for index in indices:
                row = checked["sentences"][index]
                if not all(row.get(field) for field in LEGACY_CUE_FIELDS):
                    raise MaterialError("迁移示范必须在新情境使用同一语块")
                make_cloze(row["en"], row["key_chunk"])
            upgrades[key] = {"fingerprint": fp, "sentences": merged}
            count += len(indices)
        # 单文件事务，旧材料、音频、时间轴与已有句子进度保留原字节。
        atomic_write_text(LEGACY_UPGRADE_FILE, json.dumps({"version": 1, "items": upgrades},
                                                        ensure_ascii=False, indent=2))
        return {"items": len(seen), "sentences": count}


def get_material(topic_id: str, item_id: str, *, allow_pending_audio: bool = False,
                 _apply_upgrades: bool = True) -> dict:
    path = library.item_path(topic_id, item_id)
    if not path.exists():
        raise FileNotFoundError("条目不存在")
    texts = library.read_item_texts(path)
    meta = library.load_meta(path)
    result: dict = {"status": "needs_input", "reason": "请补齐逐句学习材料"}
    if not _effective_original(texts):
        result["reason"] = "缺少原始回答；请补齐后准备材料，旧音频仍可播放"
        return result
    has_audio = library.resolve_audio_file(path, "podcast") is not None
    if allow_pending_audio and meta.get("stale"):
        has_audio = False
    if not has_audio:
        result["reason"] = "播客音频尚未完成"
        if not allow_pending_audio:
            return result
    attempt_matches = meta.get("study_attempt_fingerprint") == source_fingerprint(texts)
    if attempt_matches and meta.get("study_status") == "preparing":
        with _ACTIVE_LOCK:
            if (topic_id, item_id) not in _ACTIVE:
                return {"status": "failed", "reason": "准备任务中断，请重试"}
        return {"status": "preparing", "reason": "逐句材料正在准备"}
    if attempt_matches and meta.get("study_status") == "failed":
        return {"status": "failed", "reason": meta.get("study_error") or "材料准备失败"}
    file = path / MATERIAL_FILE
    if file.exists():
        try:
            stored = json.loads(file.read_text(encoding="utf-8"))
            if not isinstance(stored, dict):
                raise MaterialError("逐句材料文件必须是 JSON 对象")
            if stored.get("version") != VERSION:
                raise MaterialError("逐句材料版本不受支持，请重新准备")
            if stored.get("source_fingerprint") != source_fingerprint(texts):
                return {"status": "changed", "reason": "回答正文或原始回答已变化，请复核材料"}
            validated = validate_material(stored, texts)
            if _apply_upgrades:
                upgrade = legacy_upgrades().get(_legacy_key(topic_id, item_id), {})
                if upgrade.get("fingerprint") == validated["source_fingerprint"]:
                    for index, row in enumerate(validated["sentences"]):
                        if not row.get("key_chunk"):
                            row.update(upgrade["sentences"].get(str(index), {}))
            return {"status": "ready" if has_audio else "coaching_ready", "material": validated}
        except (OSError, ValueError, TypeError) as exc:
            return {"status": "failed", "reason": f"材料需修复：{str(exc)[:160]}"}
    return result


def sentence_audio(topic_id: str, item_id: str, index: int) -> dict:
    found = get_material(topic_id, item_id)
    if found["status"] != "ready":
        raise MaterialError("逐句材料尚未就绪")
    rows = found["material"]["sentences"]
    if index < 0 or index >= len(rows):
        raise MaterialError("句子序号越界")
    path = library.item_path(topic_id, item_id)
    audio = library.resolve_audio_file(path, "podcast")
    if not audio:
        raise MaterialError("音频不可用")
    response = {"scope": "full_answer", "start": 0, "end": None,
                "reason": "这句没有可靠的独立时间位置，将播放完整音频"}
    located = timeline.get_or_create_timeline(topic_id, item_id, "podcast")
    if located.get("mode") not in ("sse",):
        return response
    target = rows[index]["en"]
    matches = [line for line in located.get("lines", [])
               if line.get("speaker", "").upper() == "B"
               and target == re.sub(r"\[[^\]]*\]", "", line.get("text") or "").strip()]
    if len(matches) == 1 and (matches[0].get("end") or 0) > (matches[0].get("start") or 0):
        return {"scope": "sentence", "start": matches[0]["start"],
                "end": matches[0]["end"], "reason": "经文本和音频指纹核对的时间轴"}
    return response
