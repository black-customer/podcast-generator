"""生产线 (M14/M15/M16)：批量导入、脚本 lint、音色真源、自媒体草稿。

Agent 协作接口：Agent 会话把批量改写产物写成 Markdown 任务包（batch format），
`import_batch` 一次落盘为条目；`lint_script` 保证标签白名单与对话格式合法。
"""
import re

from . import audioqa, library
from .config import DATA_DIR

# ---------------------------------------------------------------- 脚本 lint

SCRIPT_LINT_FIELDS = ("natural_english", "fish_script", "monologue_script", "podcast_script")


def lint_script(text: str) -> dict:
    """对英文脚本做静态体检：标签白名单、对话格式、空内容。"""
    warnings = []
    cleaned, removed = audioqa.strip_disallowed_tags(text or "")
    if removed:
        warnings.append({"kind": "disallowed_tags", "detail": removed})
    if not (text or "").strip():
        warnings.append({"kind": "empty", "detail": "脚本为空"})
    # 疑似未译中文残留
    if re.search(r"[\u4e00-\u9fff]", re.sub(r"//[^\n]*", "", text or "")):
        warnings.append({"kind": "cjk_in_script", "detail": "英文脚本中检测到汉字（注释除外）"})
    return {"ok": not warnings, "warnings": warnings, "cleaned": cleaned}


def lint_batch_item(item: dict) -> dict:
    """批量包单个条目的 lint。"""
    warnings = []
    for field in SCRIPT_LINT_FIELDS:
        v = (item.get(field) or "").strip()
        if v:
            r = lint_script(v)
            for w in r["warnings"]:
                warnings.append({"field": field, **w})
    if not (item.get("chinese") or "").strip():
        warnings.append({"kind": "missing_chinese", "detail": "缺少中文回答（建议补全语料）"})
    return {"ok": not warnings, "warnings": warnings}


# ---------------------------------------------------------------- 批量包解析

SECTION_ALIASES = {
    "中文": "chinese",
    "中文回答": "chinese",
    "natural english": "natural_english",
    "英文": "natural_english",
    "英语": "natural_english",
    "fish script": "fish_script",
    "fishScript".lower(): "fish_script",
    "配音稿": "fish_script",
    "剧本": "fish_script",
    "独白": "monologue_text",
    "monologue": "monologue_text",
    "独白文本": "monologue_text",
    "独白剧本": "monologue_script",
    "monologue script": "monologue_script",
    "对话": "podcast_text",
    "podcast": "podcast_text",
    "播客剧本": "podcast_text",
    "播客文本": "podcast_text",
    "播客脚本": "podcast_text",
    "podcast script": "podcast_script",
}


def parse_batch(markdown: str) -> list[dict]:
    """解析批量任务包：

        ## 问题标题
        ### 中文
        ...
        ### Natural English
        ...
        ### 播客剧本   (可选)
        ...

    每个二级标题一个条目；三级标题为字段段。也接受 `### 中文` 等别名。
    """
    items: list[dict] = []
    cur: dict | None = None
    cur_field: str | None = None

    for raw in (markdown or "").replace("\r\n", "\n").split("\n"):
        line = raw.rstrip()
        if line.startswith("## "):
            if cur and (cur.get("question") or "").strip():
                items.append(cur)
            cur = {"question": line[3:].strip(), "_buf": {}}
            cur_field = None
            continue
        if line.startswith("### "):
            if cur is None:
                continue
            name = line[4:].strip()
            key = name.lower().replace(" ", "")
            cur_field = SECTION_ALIASES.get(key, SECTION_ALIASES.get(name.lower(), name.lower()))
            cur["_buf"].setdefault(cur_field, [])
            continue
        if cur is None:
            continue
        if cur_field:
            cur["_buf"][cur_field].append(raw)

    if cur and (cur.get("question") or "").strip():
        items.append(cur)

    out = []
    for it in items:
        buf = it.pop("_buf", {})
        entry = {"question": it["question"]}
        for field, lines in buf.items():
            if field in library.TEXT_FIELDS:
                entry[field] = "\n".join(lines).strip()
        out.append(entry)
    return out


def import_batch(topic_name: str, markdown: str, lint: bool = True) -> dict:
    """批量导入任务包 → 建条目（或更新已有同名条目）。返回导入报告。"""
    entries = parse_batch(markdown)
    if not entries:
        raise RuntimeError("任务包为空：需要至少一个 `## 标题` 段落")

    t_info = library.create_topic(topic_name) if not any(
        t["name"] == topic_name for t in library.list_topics()
    ) else next(t for t in library.list_topics() if t["name"] == topic_name)
    tid = t_info["id"]

    created, updated, rejected = [], [], []
    reject_kinds = {"empty", "disallowed_tags"}
    for entry in entries:
        report = {"question": entry["question"], "lint": {"ok": True, "warnings": []}}
        if lint:
            lr = lint_batch_item(entry)
            report["lint"] = lr
            blocking = [w for w in lr["warnings"] if w.get("kind") in reject_kinds]
            if blocking:
                report["blocking"] = blocking
                rejected.append(report)
                continue
        existing = None
        for it in library.get_topic(tid)["items"]:
            if it["title"].strip().lower() == entry["question"].strip().lower():
                existing = it["id"]
                break
        if existing:
            library.update_item_texts(tid, existing, entry)
            report["item_id"] = existing
            report["action"] = "updated"
            updated.append(report)
        else:
            r = library.create_item(tid, entry)
            report["item_id"] = r["id"]
            report["action"] = "created"
            created.append(report)

    return {
        "topic_id": tid,
        "created": len(created),
        "updated": len(updated),
        "rejected": len(rejected),
        "reports": created + updated + rejected,
    }


# ---------------------------------------------------------------- 音色真源 (M15)

VOICES_FILE = DATA_DIR / "voices.json"


def get_voice_catalog() -> list[dict]:
    voices = library.read_voices()
    for v in voices:
        v.setdefault("speed", 1.0)
        v.setdefault("temperature", None)
    return voices


def find_voice(reference_id: str) -> dict | None:
    for v in get_voice_catalog():
        if v.get("reference_id") == reference_id:
            return v
    return None


# ---------------------------------------------------------------- 自媒体草稿 (M16)

def content_drafts(topic_id: str) -> dict:
    """从话题语料生成三种自媒体内容草稿（模板驱动，零 API）。"""
    topic = library.get_topic(topic_id)
    items = []
    for it in topic["items"]:
        full = library.get_item_full(topic_id, it["id"])
        if (full.get("natural_english") or "").strip():
            items.append(full)

    quotes = []
    for it in items:
        en = (it.get("natural_english") or "").strip()
        zh = (it.get("chinese") or "").strip()
        en_first = _first_sentences(en, 2)
        zh_first = _first_sentences(zh, 1) if zh else ""
        quotes.append({"title": it["title"], "en": en_first, "zh": zh_first})

    card_lines = ["📚 我的英语语料库今日更新", ""]
    for it in items:
        card_lines.append(f"❓ {it['title']}")
        first_en = _first_sentences(it.get("natural_english") or "", 1)
        if first_en:
            card_lines.append(f"💬 {first_en}")
        card_lines.append("")
    xiaohongshu = "\n".join(card_lines).strip()

    thread = [f"🧵 {topic['name']} — 本期我用自己的真实回答练了这些表达："]
    for i, it in enumerate(items, start=1):
        en = _first_sentences(it.get("natural_english") or "", 1)
        if en:
            thread.append(f"{i}. {it['title']}\n   {en}")
    thread.append("#EnglishLearning #IELTS #英语口语")

    video_script_lines = []
    for it in items:
        video_script_lines.append(f"【{it['title']}】")
        for seg in _sentences(it.get("natural_english") or ""):
            video_script_lines.append(f"  · {seg}")
    video_script = "\n".join(video_script_lines)

    return {
        "topic": topic["name"],
        "xiaohongshu": xiaohongshu,
        "thread": "\n".join(thread),
        "video_script": video_script,
        "quotes": quotes,
    }


def _first_sentences(text: str, n: int) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?。！？])\s+", text.strip())
    return " ".join(parts[:n])


def _sentences(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"(?<=[.!?。！？])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()][:6]
