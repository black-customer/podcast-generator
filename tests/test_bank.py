"""B01 题库快照与查询测试（数据层回归——data/ 是产品本体）。"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient

from server import bank, library
from server.main import app

client = TestClient(app)

SCHEMA = """
create table books (id text primary key, title_zh text not null, title_en text not null);
create table topics (id text primary key, book_id text not null, name_zh text not null,
  name_en text not null, ielts_part integer, sort integer not null default 0);
create table questions (id text primary key, book_id text not null, topic_id text,
  part integer not null, text text not null, text_zh text not null default '',
  norm_text text not null);
create table question_sets (id text primary key, name_zh text not null, year integer not null,
  start_month integer not null, end_month integer not null, sort integer not null default 0);
create table question_set_links (question_id text not null, question_set_id text not null,
  source_slug text not null, source_file text not null, source_page integer not null,
  primary key (question_id, question_set_id, source_slug, source_page));
"""


def make_duck_db(path: Path) -> None:
    """构造最小 RoastDuck schema + 样例数据（两话题、四题、一题集、一无话题题）。"""
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    con.execute("insert into books values ('book1', '雅思全集', 'IELTS Complete')")
    con.execute("insert into books values ('book2', '个人真题', 'Personal IELTS Answers')")
    con.execute("insert into topics values ('t1', 'book1', '老师', 'Teachers', 1, 0)")
    con.execute("insert into topics values ('t2', 'book1', '家乡', 'Hometown', 1, 1)")
    con.executemany(
        "insert into questions values (?,?,?,?,?,?,?)",
        [
            ("q1", "book1", "t1", 1, "Do you have a favorite teacher?", "你有喜欢的老师吗？", "n1"),
            ("q2", "book1", "t1", 1, "Do you want to be a teacher?", "你想当老师吗？", "n2"),
            ("q3", "book1", "t2", 2, "Describe your hometown.\nYou should say: where it is.",
             "描述你的家乡", "n3"),
            ("q4", "book1", "", 3, "How has your hometown changed?", "", "n4"),
        ],
    )
    con.execute("insert into question_sets values ('s1', '2025 第一季度', 2025, 1, 3, 0)")
    con.execute("insert into question_set_links values ('q1', 's1', 'sl', 'f', 1)")
    con.commit()
    con.close()


@pytest.fixture()
def duck_db(tmp_path: Path) -> Path:
    p = tmp_path / "app.db"
    make_duck_db(p)
    return p


@pytest.fixture()
def snapshot_file(duck_db: Path, tmp_path: Path, monkeypatch) -> Path:
    # 隔离真实 9–12月补充题源：单测样例只反映 app.db 夹具本身
    monkeypatch.setattr(bank, "EXTRA_PATH", tmp_path / "no-extra.json")
    out = tmp_path / "question_bank.json"
    bank.sync_from_db(duck_db, out)
    return out


# ---------- 同步 ----------

def test_sync_creates_snapshot(duck_db: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(bank, "EXTRA_PATH", tmp_path / "no-extra.json")
    out = tmp_path / "bank.json"
    snap = bank.sync_from_db(duck_db, out)
    assert out.exists()
    assert snap["counts"] == {"books": 2, "topics": 2, "questions": 4, "sets": 1}
    on_disk = json.loads(out.read_text(encoding="utf-8"))
    assert on_disk["version"] == bank.SNAPSHOT_VERSION
    assert {q["id"] for q in on_disk["questions"]} == {"q1", "q2", "q3", "q4"}
    # Part2 cue card 全文与中文翻译必须完整保留
    q3 = next(q for q in on_disk["questions"] if q["id"] == "q3")
    assert "You should say" in q3["text"]
    assert q3["text_zh"] == "描述你的家乡"
    assert on_disk["sets"][0]["question_ids"] == ["q1"]


def test_sync_is_readonly_and_idempotent(duck_db: Path, tmp_path: Path, monkeypatch):
    monkeypatch.setattr(bank, "EXTRA_PATH", tmp_path / "no-extra.json")
    before = duck_db.read_bytes()
    out = tmp_path / "bank.json"
    first = bank.sync_from_db(duck_db, out)
    second = bank.sync_from_db(duck_db, out)
    assert duck_db.read_bytes() == before, "同步必须只读，不得写源库"
    for key in ("books", "topics", "questions", "sets", "counts"):
        assert first[key] == second[key], f"重复同步 {key} 应幂等"


def test_sync_missing_db_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        bank.sync_from_db(tmp_path / "nope.db", tmp_path / "out.json")


def test_public_snapshot_strips_private_book(duck_db: Path, tmp_path: Path, monkeypatch):
    """公开包绝不包含个人回答册（Bruce 数据绝不分发）。"""
    con = sqlite3.connect(duck_db)
    con.execute("insert into books values ('book_personal_ielts_answers', '我的答案', 'Personal')")
    con.execute(
        "insert into questions values ('qp1', 'book_personal_ielts_answers', NULL, 1, "
        "'原问句缺失：我的个人回答', '我的个人回答', 'np1')"
    )
    con.commit()
    con.close()
    monkeypatch.setattr(bank, "EXTRA_PATH", tmp_path / "no-extra.json")
    out = tmp_path / "bank.json"
    bank.sync_from_db(duck_db, out)
    pub_path = out.with_name("question_bank_public.json")
    raw = pub_path.read_text(encoding="utf-8")
    assert "book_personal_ielts_answers" not in raw
    assert "我的个人回答" not in raw and "原问句缺失" not in raw
    pub = json.loads(raw)
    assert pub["public"] is True and "source" not in pub
    assert {q["id"] for q in pub["questions"]}.isdisjoint({"qp1"})


def test_load_bank_falls_back_to_public(tmp_path: Path, monkeypatch):
    """完整快照缺失时回落公开子集（路人开箱即有题库）。"""
    pub = {"version": 1, "public": True, "questions": [{"id": "q1", "text": "Hi?"}]}
    pub_file = tmp_path / "question_bank_public.json"
    pub_file.write_text(json.dumps(pub), encoding="utf-8")
    monkeypatch.setattr(bank, "BANK_PATH", tmp_path / "question_bank.json")
    monkeypatch.setattr(bank, "PUBLIC_BANK_PATH", pub_file)
    loaded = bank.load_bank()
    assert loaded["public"] is True and loaded["questions"][0]["id"] == "q1"


def test_load_bank_missing_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(bank, "BANK_PATH", tmp_path / "nope.json")
    monkeypatch.setattr(bank, "PUBLIC_BANK_PATH", tmp_path / "no-public.json")
    with pytest.raises(FileNotFoundError):
        bank.load_bank(tmp_path / "nope.json")


# ---------- 查询 ----------

def test_query_part_and_topic_filters(snapshot_file: Path):
    snap = bank.load_bank(snapshot_file)
    assert bank.query_questions(snap, part=1)["total"] == 2
    assert bank.query_questions(snap, part=2)["total"] == 1
    assert bank.query_questions(snap, part=3)["total"] == 1
    only_t1 = bank.query_questions(snap, topic_id="t1")
    assert only_t1["total"] == 2
    assert all(it["topic_name"] == "老师" for it in only_t1["items"])


def test_query_search_en_zh(snapshot_file: Path):
    snap = bank.load_bank(snapshot_file)
    assert bank.query_questions(snap, q="FAVORITE")["total"] == 1
    assert bank.query_questions(snap, q="家乡")["total"] == 1  # 中文命中 text_zh
    assert bank.query_questions(snap, q="")["total"] == 4


def test_query_pagination_clamps(snapshot_file: Path):
    snap = bank.load_bank(snapshot_file)
    res = bank.query_questions(snap, page_size=2)
    assert res["total"] == 4 and res["pageCount"] == 2 and len(res["items"]) == 2
    res = bank.query_questions(snap, page=99, page_size=2)
    assert res["page"] == 2, "越界页码钳制到最后一页"
    res = bank.query_questions(snap, q="不存在的词")
    assert res["total"] == 0 and res["page"] == 1 and res["pageCount"] == 0


def test_query_answered_badge(snapshot_file: Path):
    snap = bank.load_bank(snapshot_file)
    answered = {
        bank.norm_title("Do you have a favorite teacher?"): {
            "topic_id": "t1", "item_id": "001-x", "status": "generated", "has_audio": True,
        },
        bank.norm_title("Do you want to be a teacher?"): {
            "topic_id": "t1", "item_id": "002-y", "status": "ready", "has_audio": False,
        },
    }
    res = bank.query_questions(snap, answered_map=answered)
    flags = {it["id"]: it for it in res["items"]}
    assert flags["q1"]["has_audio"] is True and flags["q1"]["answered"] is True
    assert flags["q2"]["has_audio"] is False and flags["q2"]["answered"] is True
    assert flags["q3"]["answered"] is False
    assert flags["q1"]["answered_item"]["item_id"] == "001-x"


def test_norm_title_normalizes():
    assert bank.norm_title("Do you have a favorite teacher?") == bank.norm_title(
        "do you   HAVE a favorite teacher"
    )


def test_query_set_filter_and_core(snapshot_file: Path):
    snap = bank.load_bank(snapshot_file)
    # 样例：q1 属于题集 s1；t2 名为 "Hometown"（必考话题）→ q3 是必考题
    res = bank.query_questions(snap, set_filter="s1")
    assert {it["id"] for it in res["items"]} == {"q1"}
    assert res["items"][0]["set_labels"] == ["1–3月"]
    core = bank.query_questions(snap, set_filter="core")
    assert {it["id"] for it in core["items"]} == {"q3"}
    assert all(it["core"] for it in core["items"])
    # Part3 的 Work & Success 类话题不得误伤
    snap["topics"].append({"id": "t_wcs", "name_zh": "工作与成功",
                           "name_en": "Work, Career & Success", "ielts_part": 3, "sort": 0})
    snap["questions"][3]["topic_id"] = "t_wcs"
    core2 = bank.query_questions(snap, set_filter="core")
    assert "q4" not in {it["id"] for it in core2["items"]}
    assert bank.query_questions(snap, set_filter="s2")["total"] == 0


def test_merge_extra_topics_questions_and_set(snapshot_file: Path, tmp_path: Path):
    import copy

    snap = bank.load_bank(snapshot_file)
    baseline = copy.deepcopy({"topics": snap["topics"], "questions": snap["questions"],
                              "sets": snap["sets"]})
    extra = tmp_path / "extra.json"
    extra.write_text(json.dumps({
        "set": {"id": "qs_x", "name_zh": "2026 年 9–12 月", "year": 2026,
                "start_month": 9, "end_month": 12},
        "topics": [{"name_en": "Paper", "name_zh": "纸"}],
        "questions": [
            {"topic_en": "Paper", "text": "Brand new question?", "text_zh": "全新题"},
            {"topic_en": "Paper", "text": "Do you have a favorite teacher?",
             "text_zh": "与 q1 重复的题干"},
        ],
    }), encoding="utf-8")
    m1 = bank.merge_extra({"topics": snap["topics"], "questions": snap["questions"],
                           "sets": snap["sets"]}, extra_path=extra)
    m2 = bank.merge_extra({"topics": m1["topics"], "questions": m1["questions"],
                           "sets": m1["sets"]}, extra_path=extra)
    # 幂等：+1 话题 +1 题（重复题干不重复入库）+1 题集
    assert len(m1["topics"]) == len(baseline["topics"]) + 1
    assert len(m1["questions"]) == len(baseline["questions"]) + 1
    assert len(m1["sets"]) == len(baseline["sets"]) + 1
    assert (len(m2["topics"]), len(m2["questions"]), len(m2["sets"])) == (
        len(m1["topics"]), len(m1["questions"]), len(m1["sets"]))
    added = [q for q in m1["questions"] if q["text"] == "Brand new question?"]
    assert len(added) == 1
    assert added[0]["part"] == 1 and added[0]["id"].startswith("q_x26q3_")
    xset = next(s for s in m1["sets"] if s["id"] == "qs_x")
    # 重复题干也挂考季（同题跨季复用）：2 个 question_ids
    assert len(xset["question_ids"]) == 2


def test_answered_items_prefers_audio(monkeypatch):
    class FakeTopic:
        def __init__(self, items):
            self._items = items

        def get(self, _k, _d=None):
            return self._items

    monkeypatch.setattr(
        library, "list_topics",
        lambda: [{"id": "01-a", "name": "A", "stats": {}, "total_sec": 0}],
    )
    monkeypatch.setattr(
        library, "get_topic",
        lambda tid: FakeTopic([
            {"id": "002-plain", "title": "Same question?", "status": "ready",
             "has_monologue": False, "has_podcast": False},
            {"id": "001-audio", "title": "Same question?", "status": "generated",
             "has_monologue": True, "has_podcast": False},
        ]),
    )
    got = bank.answered_items()
    assert got[bank.norm_title("Same question?")]["item_id"] == "001-audio"
    assert got[bank.norm_title("Same question?")]["has_audio"] is True


def test_bank_topics_counts(snapshot_file: Path):
    snap = bank.load_bank(snapshot_file)
    topics = bank.bank_topics(snap, part=1)
    assert [t["name_zh"] for t in topics] == ["老师"]  # q3 是 Part2、q4 无话题
    assert topics[0]["count"] == 2
    assert bank.bank_topics(snap) and bank.bank_topics(snap, part=3) == []


# ---------- 作答分派 ----------

def test_answer_fields_language_dispatch():
    assert bank.answer_fields("我的家乡在山里") == {"chinese": "我的家乡在山里"}
    assert bank.answer_fields("My hometown is in the mountains.") == {
        "natural_english": "My hometown is in the mountains."
    }
    assert bank.answer_fields("  \n ") == {}


def test_answer_topic_name_fallback(snapshot_file: Path):
    snap = bank.load_bank(snapshot_file)
    q1 = bank.find_question(snap, "q1")
    assert bank.answer_topic_name(snap, q1) == "Teachers"
    q4 = bank.find_question(snap, "q4")  # 无 topic → 回落题册英文名
    assert bank.answer_topic_name(snap, q4) == "IELTS Complete"
    assert bank.find_question(snap, "nope") is None


# ---------- API（快照路径 monkeypatch 到临时文件）----------

def test_api_bank_questions(monkeypatch, snapshot_file: Path):
    monkeypatch.setattr(bank, "BANK_PATH", snapshot_file)
    r = client.get("/api/bank/questions?part=1")
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is True
    assert data["total"] == 2
    assert any(t["name_zh"] == "老师" for t in data["topics"])


def test_api_bank_questions_not_available(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bank, "BANK_PATH", tmp_path / "nope.json")
    monkeypatch.setattr(bank, "PUBLIC_BANK_PATH", tmp_path / "no-public.json")
    r = client.get("/api/bank/questions")
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is False and data["items"] == []


def test_api_bank_answer_creates_item(monkeypatch, snapshot_file: Path):
    monkeypatch.setattr(bank, "BANK_PATH", snapshot_file)
    topic_name = "Teachers"
    existed = any(t["name"].casefold() == topic_name.casefold() for t in library.list_topics())
    r = client.post(
        "/api/bank/answer", json={"question_id": "q1", "answer": "我最喜欢的老师是化学老师"}
    )
    assert r.status_code == 200
    data = r.json()
    try:
        assert data["topic_name"].casefold() == topic_name.casefold()
        full = library.get_item_full(data["topic_id"], data["item_id"])
        assert full["question"] == "Do you have a favorite teacher?"
        assert full["chinese"] == "我最喜欢的老师是化学老师"
        assert not existed, "样例话题名不应与真实库冲突；若冲突说明夹具污染"
    finally:
        if not existed:
            library.delete_topic(data["topic_id"])


def test_api_bank_answer_english_and_errors(monkeypatch, snapshot_file: Path):
    monkeypatch.setattr(bank, "BANK_PATH", snapshot_file)
    r = client.post("/api/bank/answer", json={"question_id": "q1", "answer": " "})
    assert r.status_code == 422
    r = client.post("/api/bank/answer", json={"question_id": "nope", "answer": "hi"})
    assert r.status_code == 404
    topic_existed = any(
        t["name"].casefold() == "ielts complete" for t in library.list_topics()
    )
    r = client.post(
        "/api/bank/answer", json={"question_id": "q4", "answer": "It grew a lot bigger."}
    )
    assert r.status_code == 200
    data = r.json()
    try:
        full = library.get_item_full(data["topic_id"], data["item_id"])
        assert full["natural_english"] == "It grew a lot bigger."
        assert full["chinese"] == ""
    finally:
        if not topic_existed:
            library.delete_topic(data["topic_id"])


def test_api_bank_answer_without_snapshot(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(bank, "BANK_PATH", tmp_path / "nope.json")
    r = client.post("/api/bank/answer", json={"question_id": "q1", "answer": "hi"})
    assert r.status_code == 404
