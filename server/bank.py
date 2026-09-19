"""雅思题库快照与查询（B01）。

数据源为 RoastDuck 的 app.db：只读直读一次生成快照 data/question_bank.json，
运行时不依赖 RoastDuck 存在；题库更新后重跑 `python -m server.bank --sync` 重同步。
快照属可再生数据（同音频策略），不入 git。
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import sys
from pathlib import Path

from .config import atomic_write_text
from .library import now_iso

BANK_PATH = Path(__file__).resolve().parent.parent / "data" / "question_bank.json"
PUBLIC_BANK_PATH = Path(__file__).resolve().parent.parent / "data" / "question_bank_public.json"
EXTRA_PATH = Path(__file__).resolve().parent.parent / "data" / "question_bank_extra.json"
DEFAULT_DB_PATH = Path(r"D:\project\RoastDuck\data\app.db")
SNAPSHOT_VERSION = 1
PAGE_SIZE = 20

# 公开包剔除的个人数据：Bruce 的个人回答题册（题干含其个人作答描述，绝不分发）
PRIVATE_BOOK_IDS = {"book_personal_ielts_answers"}

# 必考话题：雅思每季固定的开场五件套（Bruce 2026-09-20 定稿）。
# 全等匹配话题英文名的规整形式，避免 Part3 的 "Work, Career & Success" 等误伤。
CORE_TOPIC_NORMS = {
    "work or studies", "work or study", "work studies", "work study", "work",
    "home accommodation", "home or accommodation", "home", "accommodation",
    "hometown",
    "the area you live in", "area you live in",
    "the city you live in", "city you live in",
}


def sync_from_db(db_path: Path | str | None = None, out_path: Path | str | None = None) -> dict:
    """只读连接 RoastDuck app.db，导出题库快照（原子写）。"""
    db = Path(db_path) if db_path else DEFAULT_DB_PATH
    if not db.exists():
        raise FileNotFoundError(f"题库源库不存在：{db}")
    out = Path(out_path) if out_path else BANK_PATH
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        cur = con.cursor()
        books = [
            {"id": r[0], "title_zh": r[1], "title_en": r[2]}
            for r in cur.execute("select id, title_zh, title_en from books order by id")
        ]
        topics = [
            {
                "id": r[0],
                "name_zh": r[1],
                "name_en": r[2],
                "ielts_part": r[3],
                "sort": r[4],
            }
            for r in cur.execute(
                "select id, name_zh, name_en, ielts_part, sort from topics order by sort, id"
            )
        ]
        questions = [
            {
                "id": r[0],
                "book_id": r[1],
                "part": r[2],
                "topic_id": r[3] or "",
                "text": r[4],
                "text_zh": r[5] or "",
            }
            for r in cur.execute(
                "select id, book_id, part, topic_id, text, text_zh from questions "
                "order by part, text"
            )
        ]
        # personal 题册部分题目 text 为空（原问句缺失）——用 text_zh 回退作题干，
        # 否则列表出现空行、作答会建出空题干条目
        for row in questions:
            if not row["text"].strip():
                row["text"] = row["text_zh"].strip()
                row["text_zh"] = ""
        questions = [r for r in questions if r["text"]]
        links: dict[str, list[str]] = {}
        for qid, sid in cur.execute(
            "select question_id, question_set_id from question_set_links "
            "order by question_set_id, question_id"
        ):
            links.setdefault(sid, []).append(qid)
        sets = [
            {
                "id": r[0],
                "name_zh": r[1],
                "year": r[2],
                "start_month": r[3],
                "end_month": r[4],
                "question_ids": links.get(r[0], []),
            }
            for r in cur.execute(
                "select id, name_zh, year, start_month, end_month "
                "from question_sets order by sort, id"
            )
        ]
    finally:
        con.close()
    merged = merge_extra(
        {"topics": topics, "questions": questions, "sets": sets}
    )
    topics, questions, sets = merged["topics"], merged["questions"], merged["sets"]
    snapshot = {
        "version": SNAPSHOT_VERSION,
        "exported_at": now_iso(),
        "source": str(db),
        "counts": {
            "books": len(books),
            "topics": len(topics),
            "questions": len(questions),
            "sets": len(sets),
        },
        "books": books,
        "topics": topics,
        "questions": questions,
        "sets": sets,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out, json.dumps(snapshot, ensure_ascii=False, indent=1))
    # 公开子集：剔除 Bruce 个人回答题册及其题目后入库（git 跟踪，路人开箱即有题库）
    pub = _strip_private(snapshot)
    atomic_write_text(out.with_name("question_bank_public.json"),
                      json.dumps(pub, ensure_ascii=False, indent=1))
    return snapshot


def _strip_private(snapshot: dict) -> dict:
    """公开分发子集：去掉私人题册与其题目，去掉本机路径。只含公开题库内容。"""
    books = [b for b in snapshot.get("books", []) if b["id"] not in PRIVATE_BOOK_IDS]
    questions = [q for q in snapshot.get("questions", []) if q["book_id"] not in PRIVATE_BOOK_IDS]
    used_topics = {q["topic_id"] for q in questions}
    topics = [t for t in snapshot.get("topics", []) if t["id"] in used_topics]
    qids = {q["id"] for q in questions}
    sets = []
    for s in snapshot.get("sets", []):
        sets.append({**s, "question_ids": [i for i in s.get("question_ids", []) if i in qids]})
    return {
        "version": snapshot.get("version"),
        "public": True,
        "counts": {
            "books": len(books),
            "topics": len(topics),
            "questions": len(questions),
            "sets": len(sets),
        },
        "books": books,
        "topics": topics,
        "questions": questions,
        "sets": sets,
    }


def merge_extra(data: dict, extra_path: Path | None = None) -> dict:
    """把补充题源（如 9–12月新题 PDF 整理件）合并进快照数据。

    话题按英文名规全等去重（复用已有 id）；题目按题干规整去重（已有题跳过）；
    新题生成稳定 id（q_x26q3_<hash>）并全部挂到 extra 的题集下。幂等：重跑不重复。
    """
    path = extra_path if extra_path is not None else EXTRA_PATH
    if not path.exists():
        return data
    extra = json.loads(Path(path).read_text(encoding="utf-8"))

    topics = data["topics"]
    questions = data["questions"]
    sets = data["sets"]

    topic_id_by_norm: dict[str, str] = {}
    for t in topics:
        topic_id_by_norm[norm_title(t.get("name_en") or t["name_zh"])] = t["id"]

    set_id = extra["set"]["id"]
    if not any(s["id"] == set_id for s in sets):
        sets.append({**extra["set"], "question_ids": []})
    target_set = next(s for s in sets if s["id"] == set_id)

    existing_norms: dict[str, str] = {norm_title(q["text"]): q["id"] for q in questions}
    linked = set(target_set.get("question_ids", []))

    for q in extra.get("questions", []):
        tnorm = norm_title(q["topic_en"])
        tid = topic_id_by_norm.get(tnorm)
        if tid is None:
            tmeta = next(
                (t for t in extra["topics"] if norm_title(t["name_en"]) == tnorm), None
            )
            new_id = f"t_x26q3_{hashlib.sha1(tnorm.encode()).hexdigest()[:10]}"
            topics.append(
                {
                    "id": new_id,
                    "name_zh": tmeta["name_zh"] if tmeta else q["topic_en"],
                    "name_en": tmeta["name_en"] if tmeta else q["topic_en"],
                    "ielts_part": 1,
                    "sort": 0,
                }
            )
            topic_id_by_norm[tnorm] = new_id
            tid = new_id
        qnorm = norm_title(q["text"])
        if qnorm in existing_norms:
            # 题干与库内已有题重复：不入重复行，但挂上本考季（同题可跨季复用）
            if existing_norms[qnorm] not in linked:
                target_set["question_ids"].append(existing_norms[qnorm])
                linked.add(existing_norms[qnorm])
            continue
        qid = f"q_x26q3_{hashlib.sha1(qnorm.encode()).hexdigest()[:10]}"
        questions.append(
            {
                "id": qid,
                "book_id": "book_extra_maimen",
                "part": 1,
                "topic_id": tid,
                "text": q["text"],
                "text_zh": q.get("text_zh") or "",
            }
        )
        existing_norms[qnorm] = qid
        if qid not in linked:
            target_set["question_ids"].append(qid)
            linked.add(qid)
    return {"topics": topics, "questions": questions, "sets": sets}


def load_bank(path: Path | str | None = None) -> dict:
    """读题库快照；完整快照缺失时回落到仓库自带的公开子集（路人开箱即用）。"""
    p = Path(path) if path else BANK_PATH
    if not p.exists():
        p = PUBLIC_BANK_PATH
    if not p.exists():
        raise FileNotFoundError("题库快照不存在：先运行 python -m server.bank --sync")
    return json.loads(p.read_text(encoding="utf-8"))


def norm_title(text: str) -> str:
    """题干规整键：NFKC 小写、非词字符转空格、压空白——用于与库内条目 title 匹配。"""
    t = re.sub(r"[^\w]+", " ", (text or "").lower())
    return " ".join(t.split())


def answered_items() -> dict[str, dict]:
    """库内条目按题干规整键索引：norm -> {topic_id, item_id, status, has_audio}。

    同题多条目时优先已有音频的（点进去能听）。题库页徽标与跳转依据。
    """
    from . import library

    result: dict[str, dict] = {}
    for t in library.list_topics():
        for it in library.get_topic(t["id"]).get("items", []):
            title = it.get("title") or ""
            if not title:
                continue
            entry = {
                "topic_id": t["id"],
                "item_id": it["id"],
                "status": it.get("status") or "",
                "has_audio": bool(it.get("has_monologue") or it.get("has_podcast")),
            }
            key = norm_title(title)
            prev = result.get(key)
            if prev is None or (entry["has_audio"] and not prev["has_audio"]):
                result[key] = entry
    return result


def set_index(snapshot: dict) -> dict[str, list[dict]]:
    """qid -> 所属题集列表（含 short 短标签），并给题集补 count。"""
    sets = snapshot.get("sets", [])
    idx: dict[str, list[dict]] = {}
    for s in sets:
        s["short"] = f"{s['start_month']}–{s['end_month']}月"
        for qid in s.get("question_ids", []):
            idx.setdefault(qid, []).append(s)
    return idx


def _topic_label(snapshot: dict, question: dict) -> tuple[str, str]:
    """题目的话题中文名/英文名；无 topic_id 时回落到所属题册名。"""
    for t in snapshot.get("topics", []):
        if t["id"] == question.get("topic_id"):
            return t["name_zh"], t.get("name_en") or ""
    for b in snapshot.get("books", []):
        if b["id"] == question.get("book_id"):
            return b["title_zh"], b.get("title_en") or ""
    return "未分类", ""


def _core_topic_ids(snapshot: dict) -> set[str]:
    """必考话题 id 集合：话题英文名规整后落在 CORE_TOPIC_NORMS 全等集合内。"""
    return {
        t["id"]
        for t in snapshot.get("topics", [])
        if norm_title(t.get("name_en") or "") in CORE_TOPIC_NORMS
    }


def query_questions(
    snapshot: dict,
    part: int | None = None,
    topic_id: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    answered_map: dict[str, dict] | None = None,
    random_pick: bool = False,
    set_filter: str | None = None,
) -> dict:
    """题库查询：part/topic 精确过滤，q 中英不区分大小写子串，页参数钳制。

    set_filter：题集 id（考季筛选）或 "core"（必考题——固定五话题：
    Work or studies / Home-accommodation / Hometown / The area you live in /
    The city you live in，Bruce 2026-09-20 定稿）。
    random_pick=True 时从过滤结果随机取一题（items 单条，total 保持过滤总数）。
    """
    needle = (q or "").strip().casefold()
    qsets = set_index(snapshot)
    core_tids = _core_topic_ids(snapshot)
    rows: list[dict] = []
    for row in snapshot.get("questions", []):
        if part is not None and row["part"] != part:
            continue
        if topic_id and row["topic_id"] != topic_id:
            continue
        if needle:
            in_en = needle in row["text"].casefold()
            in_zh = needle in (row["text_zh"] or "").casefold()
            if not in_en and not in_zh:
                continue
        my_sets = qsets.get(row["id"], [])
        is_core = row["topic_id"] in core_tids
        if set_filter == "core" and not is_core:
            continue
        if set_filter and set_filter != "core" and set_filter not in {s["id"] for s in my_sets}:
            continue
        name_zh, name_en = _topic_label(snapshot, row)
        answered_item = (answered_map or {}).get(norm_title(row["text"]))
        rows.append(
            {
                **row,
                "topic_name": name_zh,
                "topic_name_en": name_en,
                "answered": answered_item is not None,
                "has_audio": bool(answered_item and answered_item["has_audio"]),
                "answered_item": answered_item,
                "set_labels": [s["short"] for s in my_sets],
                "core": is_core,
            }
        )
    total = len(rows)
    if random_pick and rows:
        import random as _random

        rows = [_random.choice(rows)]
        return {"items": rows, "total": total, "page": 1, "pageCount": 1, "page_size": 1}
    size = min(max(1, page_size), 100)
    page_count = max(1, math.ceil(total / size)) if total else 0
    page = min(max(1, page), page_count) if total else 1
    start = (page - 1) * size
    return {
        "items": rows[start : start + size],
        "total": total,
        "page": page,
        "pageCount": page_count,
        "page_size": size,
    }


def bank_topics(snapshot: dict, part: int | None = None) -> list[dict]:
    """话题筛选器数据：每话题在当前 part 过滤下的题数。"""
    counts: dict[str, int] = {}
    for row in snapshot.get("questions", []):
        if part is not None and row["part"] != part:
            continue
        if row["topic_id"]:
            counts[row["topic_id"]] = counts.get(row["topic_id"], 0) + 1
    result = []
    for t in snapshot.get("topics", []):
        n = counts.get(t["id"], 0)
        if n:
            result.append(
                {
                    "id": t["id"],
                    "name_zh": t["name_zh"],
                    "name_en": t.get("name_en") or "",
                    "ielts_part": t.get("ielts_part"),
                    "count": n,
                }
            )
    result.sort(key=lambda t: (t.get("ielts_part") or 9, -(t["count"]), t["name_zh"]))
    return result


def find_question(snapshot: dict, question_id: str) -> dict | None:
    for row in snapshot.get("questions", []):
        if row["id"] == question_id:
            return row
    return None


def answer_fields(answer: str) -> dict:
    """原始作答按语言分派：含中文 → chinese 字段；纯英文 → natural_english（待 Agent 改写）。"""
    text = (answer or "").strip()
    if not text:
        return {}
    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in text)
    return {"chinese": text} if has_cjk else {"natural_english": text}


def answer_topic_name(snapshot: dict, question: dict) -> str:
    """作答入库的目标话题名：题库话题英文名（缺省回落题册英文名）。"""
    for t in snapshot.get("topics", []):
        if t["id"] == question.get("topic_id"):
            return t.get("name_en") or t["name_zh"]
    for b in snapshot.get("books", []):
        if b["id"] == question.get("book_id"):
            return b.get("title_en") or b["title_zh"]
    return "Bank imports"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="RoastDuck 题库快照同步工具")
    parser.add_argument("--sync", action="store_true", help="只读直读 app.db 生成题库快照")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="app.db 路径")
    args = parser.parse_args()
    if not args.sync:
        parser.print_help()
        return
    snap = sync_from_db(args.db)
    print(
        f"题库同步完成：{snap['counts']['questions']} 题 / "
        f"{snap['counts']['topics']} 话题 / {snap['counts']['sets']} 题集 → {BANK_PATH}"
    )


if __name__ == "__main__":
    sys.exit(main())
