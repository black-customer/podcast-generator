"""R03 Agent/API 双模式闭环回归：original_answer、JSON Mode 改写校验、统一入口、CLI、双模一致性。"""
import json
import sys
import time
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient

from server import bank, library

VALID_TEXTS = {
    "natural_english": (
        "I still remember the first teacher who truly influenced me. She was patient, "
        "and she always pushed us to ask better questions instead of memorizing answers."
    ),
    "podcast_text": (
        "A: Who was your favorite teacher growing up?\n"
        "B: Definitely my high school English teacher. She was patient and she always "
        "pushed us to ask better questions instead of just memorizing answers."
    ),
    "podcast_script": (
        "A: [curious] Who was your favorite teacher growing up?\n"
        "B: [relaxed] Definitely my high school English teacher [break] She was patient, and she "
        "always pushed us to ask better questions instead of just memorizing answers."
    ),
}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    topics = tmp_path / "topics"
    episodes = tmp_path / "episodes"
    for d in (topics, episodes, tmp_path / ".tmp"):
        d.mkdir(parents=True)
    from server import assemble, audio, config
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    monkeypatch.setattr(library, "EPISODES_DIR", episodes)
    monkeypatch.setattr(assemble, "EPISODES_DIR", episodes)
    monkeypatch.setattr(audio, "TMP_DIR", tmp_path / ".tmp")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    config.atomic_write_text(tmp_path / "settings.json", json.dumps({"dry_run": True}))
    from server import jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, "JOBS_FILE", tmp_path / "jobs.json")
    jobs_mod.JOBS.clear()
    jobs_mod._ACTIVE_TOPICS.clear()
    yield {"client": None, "tmp": tmp_path, "topics_dir": topics}
    jobs_mod.JOBS.clear()
    jobs_mod._ACTIVE_TOPICS.clear()


@pytest.fixture()
def client(env):
    from server.main import app
    with TestClient(app) as c:
        env["client"] = c
        yield env


def wait_job(client, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job and job.get("state") != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("job 超时仍在运行")


# ---------------------------------------------------------------- 数据层：original_answer

def test_original_answer_roundtrip(env):
    it = library.create_topic("T")
    created = library.create_item(
        it["id"], {"question": "Q?", "chinese": "我的回答", "original_answer": "我的回答"}
    )
    d = library.item_path(it["id"], created["id"])
    texts = library.read_item_texts(d)
    assert texts["original_answer"] == "我的回答"
    assert (d / "original_answer.txt").exists()


def test_original_answer_fallback_for_legacy_items(env):
    """旧条目没有 original_answer.txt：读取为空，回退语义 chinese → natural_english。"""
    from server import rewrite
    it = library.create_topic("T")
    created = library.create_item(it["id"], {"question": "Q?", "chinese": "中文回答"})
    texts = library.read_item_texts(library.item_path(it["id"], created["id"]))
    assert texts["original_answer"] == ""
    assert rewrite.original_answer_of(texts) == "中文回答"
    texts2 = dict(texts, chinese="", natural_english="English answer")
    assert rewrite.original_answer_of(texts2) == "English answer"
    assert rewrite.original_answer_of(dict(texts2, natural_english="")) == ""


def test_original_answer_change_does_not_stale_audio(env):
    from server import config
    it = library.create_topic("T")
    fields = dict(VALID_TEXTS, question="Q?", chinese="中文", original_answer="旧回答")
    created = library.create_item(it["id"], fields)
    config.atomic_write_text(
        config.SETTINGS_FILE, json.dumps({"dry_run": True, "tts_provider": "stepfun"})
    )
    from server import tts
    tts.generate_item_audio(it["id"], created["id"], track="podcast")
    library.update_item_texts(it["id"], created["id"], {"original_answer": "新回答"})
    meta = library.load_meta(library.item_path(it["id"], created["id"]))
    assert meta.get("stale") in (False, None)


# ---------------------------------------------------------------- rewrite 校验

def test_validate_texts_accepts_valid_payload():
    from server import rewrite
    assert rewrite.validate_texts(dict(VALID_TEXTS)) == []


def test_validate_texts_rejects_missing_or_non_dialogue():
    from server import rewrite
    missing = rewrite.validate_texts({k: v for k, v in VALID_TEXTS.items() if k != "podcast_text"})
    assert any("podcast_text" in e for e in missing)
    flat = dict(VALID_TEXTS, podcast_text="Just a plain monologue without dialogue lines.")
    assert any("A:" in e or "对话" in e for e in rewrite.validate_texts(flat))


def test_validate_texts_rejects_tags_in_visible_and_offlist_tags_in_script():
    from server import rewrite
    tagged_visible = dict(VALID_TEXTS, natural_english="She [chuckle] was patient.")
    assert rewrite.validate_texts(tagged_visible), "可见文本不允许任何表演标签"
    bad_tag = dict(VALID_TEXTS, podcast_script="A: Hi [whisper] there.\nB: Hello.")
    errs = rewrite.validate_texts(bad_tag)
    assert any("whisper" in e for e in errs)


@pytest.mark.parametrize("unsafe_tag", ["chuckle", "laugh", "sigh", "inhale", "pause"])
def test_validate_texts_rejects_legacy_audio_risk_tags(unsafe_tag):
    """旧数据可兼容宽白名单，但新生成稿必须遵守 Q02 的轻量标签政策。"""
    from server import rewrite

    bad = dict(
        VALID_TEXTS,
        podcast_script=f"A: [curious] Hi there.\nB: [relaxed] Hello [{unsafe_tag}].",
    )
    errors = rewrite.validate_texts(bad)
    assert any(unsafe_tag in error for error in errors)


def test_validate_texts_rejects_semantic_mismatch_between_text_and_script():
    from server import rewrite
    mismatch = dict(
        VALID_TEXTS,
        podcast_text=(
            "A: Do you like the mountains near your hometown?\n"
            "B: Yes, the peaks and valleys there are absolutely wonderful in autumn."
        ),
    )
    errs = rewrite.validate_texts(mismatch)
    assert any("一致" in e for e in errs)


# ---------------------------------------------------------------- rewrite 生成流

class _Resp:
    def __init__(self, status_code=200, content=""):
        self.status_code = status_code
        self._content = content
        self.text = content

    def json(self):
        return {"choices": [{"message": {"content": self._content}, "finish_reason": "stop"}]}


def _chat_payload(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False)


def test_generate_texts_repairs_once_then_succeeds(monkeypatch):
    from server import rewrite
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        if len(calls) == 1:
            bad = dict(VALID_TEXTS)
            bad.pop("podcast_text")
            return _Resp(content=_chat_payload(bad))
        return _Resp(content=_chat_payload(VALID_TEXTS))

    monkeypatch.setattr(rewrite.httpx, "post", fake_post)
    texts, repairs = rewrite.generate_texts(
        {"stepfun_api_key": "sk-test"}, "Who was your favorite teacher?", "我的英语老师"
    )
    assert repairs == 1
    assert texts == VALID_TEXTS
    assert len(calls) == 2


def test_generate_texts_no_permission_fails_fast_without_retry(monkeypatch):
    from server import rewrite
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(json)
        return _Resp(status_code=401, content="unauthorized")

    monkeypatch.setattr(rewrite.httpx, "post", fake_post)
    with pytest.raises(rewrite.TextPermissionError) as ei:
        rewrite.generate_texts({"stepfun_api_key": "sk-test"}, "Q?", "A")
    assert "Agent" in str(ei.value)
    assert len(calls) == 1


def test_generate_texts_structural_failure_after_one_repair(monkeypatch):
    from server import rewrite

    def fake_post(url, headers=None, json=None, timeout=None):
        return _Resp(content="not json at all {{{")

    monkeypatch.setattr(rewrite.httpx, "post", fake_post)
    with pytest.raises(rewrite.RewriteError):
        rewrite.generate_texts({"stepfun_api_key": "sk-test"}, "Q?", "A")


# ---------------------------------------------------------------- 统一入口端点

def test_generation_request_agent_mode_creates_item_without_text_api(client, monkeypatch):
    from server import rewrite
    c = client["client"]
    config_key = "sk-step-SECRET"

    def boom(*a, **k):
        raise AssertionError("Agent 模式不得调用文本 API")

    monkeypatch.setattr(rewrite.httpx, "post", boom)
    saved = c.put("/api/settings", json={"stepfun_api_key": config_key}).json()
    assert saved["stepfun_api_key_set"] is True

    r = c.post(
        "/api/generation-requests",
        json={"question": "Who was your favorite teacher?", "topic": "Teachers",
              "answer": "我最喜欢高中英语老师，她很有耐心。", "mode": "agent"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["topic_id"] and data["item_id"]
    assert data["result_url"].startswith("#/done/")
    assert "pipeline.py complete" in data["agent_prompt"]
    assert data["item_id"] in data["agent_prompt"]
    assert config_key not in data["agent_prompt"]
    texts = library.read_item_texts(library.item_path(data["topic_id"], data["item_id"]))
    assert texts["original_answer"].startswith("我最喜欢")
    assert texts["question"] == "Who was your favorite teacher?"


def test_generation_request_bank_question_path(client, monkeypatch):
    c = client["client"]
    snapshot = {
        "questions": [{"id": "q1", "text": "Do you have a favorite teacher?",
                       "topic_id": "t1"}],
        "topics": [{"id": "t1", "name_en": "Teachers", "name_zh": "老师"}],
        "books": [],
    }
    monkeypatch.setattr(bank, "load_bank", lambda: snapshot)
    r = c.post(
        "/api/generation-requests",
        json={"question_id": "q1", "answer": "My favorite teacher is Miss Li.", "mode": "agent"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    texts = library.read_item_texts(library.item_path(data["topic_id"], data["item_id"]))
    assert texts["question"] == "Do you have a favorite teacher?"
    assert data["agent_prompt"].count("pipeline.py complete") == 1


def test_generation_request_api_mode_mock_full_chain(client, monkeypatch):
    """API 模式全链路（mock 文本改写 + dry TTS）：改写→校验→落盘→合成→同构数据。"""
    from server import rewrite
    c = client["client"]
    monkeypatch.setattr(
        rewrite, "generate_texts",
        lambda settings, q, a, cancel=None: (dict(VALID_TEXTS), 0),
    )
    r = c.post(
        "/api/generation-requests",
        json={"question": "Who was your favorite teacher?", "topic": "Teachers",
              "answer": "我最喜欢高中英语老师。", "mode": "api"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["job_id"] and not data.get("agent_prompt")
    job = wait_job(c, data["job_id"])
    assert job["state"] == "done", job
    texts = library.read_item_texts(library.item_path(data["topic_id"], data["item_id"]))
    assert texts["natural_english"] == VALID_TEXTS["natural_english"]
    assert texts["podcast_text"] == VALID_TEXTS["podcast_text"]
    assert texts["podcast_script"] == VALID_TEXTS["podcast_script"]
    assert texts["original_answer"] == "我最喜欢高中英语老师。"
    audio_path = library.item_path(data["topic_id"], data["item_id"]) / "audio_podcast.mp3"
    assert audio_path.exists() and audio_path.stat().st_size > 0
    meta = library.load_meta(library.item_path(data["topic_id"], data["item_id"]))
    assert meta.get("status") == "generated"
    # 与 Agent 模式（CLI 完成路径）产出完全同构
    assert set(texts.keys()) >= {"original_answer", "natural_english", "podcast_text",
                                 "podcast_script"}


def test_generation_request_api_mode_permission_failure_keeps_answer_no_audio(client, monkeypatch):
    from server import rewrite
    c = client["client"]

    def no_permission(settings, q, a, cancel=None):
        raise rewrite.TextPermissionError("当前 Key 无文本模型权限，请改用 Agent 模式")

    monkeypatch.setattr(rewrite, "generate_texts", no_permission)
    r = c.post(
        "/api/generation-requests",
        json={"question": "Q?", "topic": "T", "answer": "原始回答内容", "mode": "api"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    job = wait_job(c, data["job_id"])
    assert job["state"] == "error"
    assert any("Agent" in e["message"] for e in job["errors"])
    texts = library.read_item_texts(library.item_path(data["topic_id"], data["item_id"]))
    assert texts["original_answer"] == "原始回答内容"
    assert not (library.item_path(data["topic_id"], data["item_id"]) / "audio_podcast.mp3").exists()


def test_agent_task_endpoint_returns_refreshable_prompt(client):
    c = client["client"]
    r = c.post(
        "/api/generation-requests",
        json={"question": "Q1?", "topic": "T1", "answer": "回答", "mode": "agent"},
    )
    data = r.json()
    r2 = c.get(f"/api/topics/{data['topic_id']}/items/{data['item_id']}/agent-task")
    assert r2.status_code == 200
    prompt = r2.json()["agent_prompt"]
    assert "pipeline.py complete" in prompt and data["item_id"] in prompt
    texts = library.read_item_texts(library.item_path(data["topic_id"], data["item_id"]))
    assert texts["original_answer"] == "回答"


# ---------------------------------------------------------------- pipeline complete（Agent 执行端）

def test_pipeline_complete_writes_and_generates(env, capsys):
    import pipeline
    it = library.create_topic("Teachers")
    created = library.create_item(
        it["id"], {"question": "Who was your favorite teacher?",
                   "original_answer": "我的英语老师。"}
    )
    result = pipeline.complete_item(it["id"], created["id"], dict(VALID_TEXTS))
    texts = library.read_item_texts(library.item_path(it["id"], created["id"]))
    assert texts["podcast_text"] == VALID_TEXTS["podcast_text"]
    assert texts["original_answer"] == "我的英语老师。"
    assert (library.item_path(it["id"], created["id"]) / "audio_podcast.mp3").exists()
    assert "#/done/" in result["play_url"]
    assert result["mp3_path"].endswith("audio_podcast.mp3")


def test_pipeline_complete_rejects_invalid_result_without_partial_write(env):
    import pipeline
    it = library.create_topic("T")
    created = library.create_item(it["id"], {"question": "Q?", "original_answer": "答"})
    bad = dict(VALID_TEXTS)
    bad.pop("natural_english")
    with pytest.raises(pipeline.CompleteError):
        pipeline.complete_item(it["id"], created["id"], bad)
    texts = library.read_item_texts(library.item_path(it["id"], created["id"]))
    assert texts["natural_english"] == ""
    assert texts["original_answer"] == "答"
    assert not (library.item_path(it["id"], created["id"]) / "audio_podcast.mp3").exists()


def test_both_modes_produce_identical_structures(client, monkeypatch):
    """Agent 模式（CLI 路径）与 API 模式（mock）最终数据结构完全一致。"""
    import pipeline
    from server import rewrite
    c = client["client"]
    monkeypatch.setattr(
        rewrite, "generate_texts",
        lambda settings, q, a, cancel=None: (dict(VALID_TEXTS), 0),
    )
    api_res = c.post(
        "/api/generation-requests",
        json={"question": "Q?", "topic": "Parity", "answer": "同一个回答", "mode": "api"},
    ).json()
    wait_job(c, api_res["job_id"])

    agent_res = c.post(
        "/api/generation-requests",
        json={"question": "Q?", "topic": "Parity", "answer": "同一个回答", "mode": "agent"},
    ).json()
    pipeline.complete_item(agent_res["topic_id"], agent_res["item_id"], dict(VALID_TEXTS))

    def snap(tid, iid):
        d = library.item_path(tid, iid)
        texts = library.read_item_texts(d)
        meta = library.load_meta(d)
        keys = ("original_answer", "natural_english", "podcast_text", "podcast_script")
        return ({k: texts[k] for k in keys}, meta.get("status"),
                (d / "audio_podcast.mp3").exists())

    assert snap(api_res["topic_id"], api_res["item_id"]) == \
        snap(agent_res["topic_id"], agent_res["item_id"])


def test_chat_routes_to_configured_plan_endpoint(monkeypatch):
    """配置 stepfun_text_base_url 时文本调用走该接入点（Coding Plan 额度），默认不变。"""
    from server import rewrite

    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "{}"}}]}

    def fake_post(url, **kwargs):
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr(rewrite.httpx, "post", fake_post)
    settings = {"stepfun_api_key": "sk-test", "stepfun_text_model": "step-5-preview"}
    rewrite._chat(settings, [{"role": "user", "content": "hi"}], None)
    assert captured["url"] == rewrite.TEXT_API_URL

    settings["stepfun_text_base_url"] = "https://api.stepfun.com/step_plan/v1"
    rewrite._chat(settings, [{"role": "user", "content": "hi"}], None)
    assert captured["url"] == "https://api.stepfun.com/step_plan/v1/chat/completions"
