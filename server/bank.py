"""雅思题库快照与查询（B01）。

数据源为 RoastDuck 的 app.db：只读直读一次生成快照 data/question_bank.json，
运行时不依赖 RoastDuck 存在；题库更新后重跑 `python -m server.bank --sync` 重同步。
快照属可再生数据（同音频策略），不入 git。
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import sys
from pathlib import Path

from .config import atomic_write_text
from .library import now_iso

BANK_PATH = Path(__file__).resolve().parent.parent / "data" / "question_bank.json"
DEFAULT_DB_PATH = Path(r"D:\project\RoastDuck\data\app.db")
SNAPSHOT_VERSION = 1
PAGE_SIZE = 20


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
    return snapshot


def load_bank(path: Path | str | None = None) -> dict:
    """读题库快照；未导入时抛 FileNotFoundError。"""
    p = Path(path) if path else BANK_PATH
    if not p.exists():
        raise FileNotFoundError("题库快照不存在：先运行 python -m server.bank --sync")
    return json.loads(p.read_text(encoding="utf-8"))


def norm_title(text: str) -> str:
    """题干规整键：NFKC 小写、非词字符转空格、压空白——用于与库内条目 title 匹配。"""
    t = re.sub(r"[^\w]+", " ", (text or "").lower())
    return " ".join(t.split())


def answered_norms() -> set[str]:
    """库内全部条目 title 的规整键集合（题库页"已作答/已有音频"徽标依据）。"""
    from . import library

    norms: set[str] = set()
    for t in library.list_topics():
        for it in library.get_topic(t["id"]).get("items", []):
            title = it.get("title") or ""
            if title:
                norms.add(norm_title(title))
    return norms


def _topic_label(snapshot: dict, question: dict) -> tuple[str, str]:
    """题目的话题中文名/英文名；无 topic_id 时回落到所属题册名。"""
    for t in snapshot.get("topics", []):
        if t["id"] == question.get("topic_id"):
            return t["name_zh"], t.get("name_en") or ""
    for b in snapshot.get("books", []):
        if b["id"] == question.get("book_id"):
            return b["title_zh"], b.get("title_en") or ""
    return "未分类", ""


def query_questions(
    snapshot: dict,
    part: int | None = None,
    topic_id: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    answered: set[str] | None = None,
) -> dict:
    """题库查询：part/topic 精确过滤，q 中英不区分大小写子串，页参数钳制。"""
    needle = (q or "").strip().casefold()
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
        name_zh, name_en = _topic_label(snapshot, row)
        rows.append(
            {
                **row,
                "topic_name": name_zh,
                "topic_name_en": name_en,
                "answered": bool(answered) and norm_title(row["text"]) in answered,
            }
        )
    total = len(rows)
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
