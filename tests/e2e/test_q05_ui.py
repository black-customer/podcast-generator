"""Q05 合成浏览器交互与截图；请求全部模拟，不触碰个人内容。"""
import io
import json
import os
import re
import wave
import zipfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import expect, sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8765")
OUT = Path("data/.tmp/q05-ui")


def mock(page, state=None):
    state = state or {"drafts": {}, "progress": {}, "fail_draft": False, "fail_progress": False}
    item = {"id": "i1", "title": "Your home?", "question": "Your home?",
            "original_answer": "我的家在河边。", "chinese": "我的家在河边。",
            "natural_english": "My home is by the river.",
            "podcast_text": "B: My home is by the river.",
            "status": "generated", "has_audio": True, "has_audio_podcast": True,
            "has_audio_monologue": True, "has_monologue": True, "has_podcast": True,
            "study_status": "ready", "duration_sec": 30}
    topic = {"id": "t1", "name": "Synthetic Q05", "items": [item], "category": "ielts",
             "stats": {"total": 1, "generated": 1}, "total_sec": 30}
    ref = {"topic_id": "t1", "item_id": "i1", "has_audio": True,
           "created_at": "2026-10-01T12:00:00Z"}
    rows = [{"id": "q1", "text": "Your home?", "text_zh": "你的家在哪里？", "part": 1,
             "topic_name": "家乡", "topic_name_en": "Home", "answered": True,
             "has_audio": True, "answered_item": ref},
            {"id": "q2", "text": "Your work?", "text_zh": "你做什么工作？", "part": 1,
             "topic_name": "工作", "topic_name_en": "Work", "answered": False}]
    audio_buffer = io.BytesIO()
    with wave.open(audio_buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * 30)

    def handler(route):
        req = route.request
        url = urlparse(req.url)
        path = url.path
        qs = parse_qs(url.query)
        body = req.post_data_json if req.method == "PUT" else {}
        if "/audio/" in path or path.endswith("/episode/audio"):
            payload = audio_buffer.getvalue()
            match = re.match(r"bytes=(\d+)-(\d*)", req.headers.get("range", ""))
            if match:
                start = int(match[1])
                end = min(int(match[2]) if match[2] else len(payload) - 1, len(payload) - 1)
                route.fulfill(status=206, body=payload[start:end + 1], content_type="audio/wav",
                              headers={"Accept-Ranges": "bytes",
                                       "Content-Range": f"bytes {start}-{end}/{len(payload)}"})
            else:
                route.fulfill(body=payload, content_type="audio/wav",
                              headers={"Accept-Ranges": "bytes"})
            return
        if path.endswith("/settings"):
            data = {"stepfun_api_key_set": True, "fish_api_key_set": False}
        elif path.endswith("/bank/questions"):
            status = qs.get("answer_status", ["all"])[0]
            selected = [r for r in rows if status == "all"
                        or r["answered"] == (status == "answered")]
            needle = qs.get("q", [""])[0].lower()
            selected = [r for r in selected if needle in r["text"].lower()]
            if qs.get("random"):
                selected = selected[:1]
            data = {"available": True, "items": selected, "total": len(selected),
                    "page": 1, "pageCount": 1, "topics": [], "sets": []}
        elif path.endswith("/answers"):
            data = {"answers": [ref, {**ref, "item_id": "i2", "has_audio": False,
                                      "created_at": "2026-09-01T12:00:00Z"}]}
        elif path == "/api/answer-drafts":
            data = {"drafts": list(state["drafts"].values())}
        elif "/answer-drafts/" in path:
            if req.method == "GET" and state.get("fail_draft_read"):
                route.fulfill(status=503, json={"detail": "Synthetic draft read failure"})
                return
            qid = path.rsplit("/", 1)[1]
            current = state["drafts"].get(qid, {"answer": "", "revision": 0, "mode": "agent"})
            if req.method == "PUT":
                if state["fail_draft"]:
                    route.fulfill(status=503, json={"detail": "Synthetic save failure"})
                    return
                if body["revision"] != current["revision"]:
                    route.fulfill(status=409, json={"detail": "另一页面已更新草稿"})
                    return
                current = {**body, "question_id": qid, "revision": current["revision"] + 1}
                state["drafts"][qid] = current
            elif req.method == "DELETE":
                if int(qs["revision"][0]) != current["revision"]:
                    route.fulfill(status=409, json={"detail": "草稿已更新"})
                    return
                current = {"answer": "", "revision": current["revision"] + 1}
                state["drafts"][qid] = current
            data = current
        elif path.endswith("/listening-progress/latest"):
            data = next(iter(state["progress"].values()), {"latest": None})
        elif path.endswith("/listening-progress"):
            track = body.get("track") or qs.get("track", ["podcast"])[0]
            data = {"kind": "item", "topic_id": "t1", "item_id": "i1", "track": track,
                    "position": 8, "duration": 30, "title": "Your home?",
                    "audio_fingerprint": "synthetic-audio", "state": "ready",
                    **state["progress"].get(track, {})}
            if req.method == "PUT":
                if state["fail_progress"]:
                    route.fulfill(status=503, json={"detail": "Synthetic progress failure"})
                    return
                state.setdefault("progress_writes", []).append(body)
                data.update(body)
                state["progress"][track] = data
        elif path.endswith("/topics"):
            data = [topic]
        elif path.endswith("/topics/t1"):
            data = topic
        elif "/items/" in path and "/timeline/" not in path:
            data = item if path.endswith("i1") else {**item, "id": "i2", "has_audio": False,
                                                    "original_answer": "历史原话"}
        elif "/timeline/" in path:
            data = {"lines": [{"text": "My home is by the river.", "start": 0, "end": 30}],
                    "words": [], "mode": "estimated"}
        elif path.endswith("/search"):
            data = {"results": [{"topic_id": "t1", "item_id": "i1", "title": "Your home?",
                                 "topic_name": "Synthetic Q05", "snippet": "我的家在河边。",
                                 "has_audio": True, "study_status": "ready"}],
                    "total": 1, "page": 1, "pageCount": 1}
        elif path.endswith("/generation-requests"):
            state["submits"] = state.get("submits", 0) + 1
            if state.get("fail_submit"):
                route.fulfill(status=500, json={"detail": "Synthetic submit failure"})
                return
            data = {"topic_id": "t1", "item_id": "i1", "agent_prompt": "Synthetic command"}
        elif path.endswith("/episode"):
            data = {"items": [{"title": "Your home?", "offset_sec": 0}],
                    "topic_name": "Synthetic Q05", "item_count": 1, "total_sec": 30}
        else:
            data = {}
        route.fulfill(json=data)

    page.route("**/api/**", handler)
    return state


@pytest.mark.parametrize("width,height", [(1536, 1024), (1280, 800), (1024, 768)])
def test_q05_screens_and_flow(width, height):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        state = mock(page)
        OUT.mkdir(parents=True, exist_ok=True)
        before = bool(os.environ.get("Q05_BASELINE"))
        for name, url in [("bank", "#/bank?sel=q1"), ("corpus", "#/topics"),
                          ("player", "#/play/t1/i1")]:
            page.goto(BASE_URL + "/" + url)
            page.wait_for_timeout(450)
            page.screenshot(path=str(OUT / f"{'before' if before else 'after'}-{width}-{name}.png"),
                            full_page=True)
        if before:
            browser.close()
            return
        page.goto(BASE_URL + "/#/bank?sel=q1")
        expect(page.locator("#saved-answer")).to_contain_text("我的家在河边")
        expect(page.locator("#bank-answer-input")).to_have_count(0)
        page.locator("#answer-version").select_option("1")
        expect(page.locator("#saved-answer")).to_contain_text("历史原话")
        page.locator("#bank-status").select_option("unanswered")
        expect(page.locator(".bank-row")).to_have_count(1)
        page.locator(".bank-row").click()
        page.locator("#bank-answer-input").fill("这是一份未提交草稿")
        page.locator("[name='bank-gen-mode'][value='api']").check()
        expect(page.locator("#draft-status")).to_contain_text("已保存")
        page.reload()
        expect(page.locator("#bank-answer-input")).to_have_value("这是一份未提交草稿")
        expect(page.locator("[name='bank-gen-mode'][value='api']")).to_be_checked()
        state["fail_draft"] = True
        page.locator("#bank-answer-input").fill("保存失败仍保留的文字")
        expect(page.locator("#draft-status")).to_contain_text("保存失败")
        expect(page.locator("#bank-answer-input")).to_have_value("保存失败仍保留的文字")
        page.screenshot(path=str(OUT / f"after-{width}-draft-failure.png"), full_page=True)
        state["fail_draft"] = False
        page.goto(BASE_URL + "/#/topics?q=河边")
        expect(page.locator(".corpus-search-result")).to_contain_text("河边")
        page.screenshot(path=str(OUT / f"after-{width}-search.png"), full_page=True)
        page.goto(BASE_URL + "/#/play/t1/i1")
        page.wait_for_function("document.getElementById('core-audio').currentTime >= 8",
                               timeout=3000)
        page.locator("#gp-restart").click()
        assert page.locator("#core-audio").evaluate("a => a.currentTime") < 2
        assert not errors, errors
        browser.close()


@pytest.mark.parametrize("width", [390, 430])
def test_offline_search_answer_filter_and_resume(width, tmp_path):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * 30)
    path = tmp_path / "synthetic.pack.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("pack.json", json.dumps({"pack_version": 1, "content_hash": "synthetic",
            "topics": [{"id": "中文话题", "name": "Synthetic Q05", "items": [{"id": "i1"}]}],
            "counts": {"topics": 1, "items": 1}}))
        archive.writestr("bank.json", json.dumps({"questions": [
            {"id": "q1", "text": "Your home?", "part": 1, "topic_id": "", "text_zh": "家"},
            {"id": "q2", "text": "Your work?", "part": 1, "topic_id": "", "text_zh": "工作"}],
            "topics": [], "sets": []}))
        archive.writestr("topics/中文话题/items/i1/item.json", json.dumps({
            "id": "i1", "title": "Your home?", "texts": {"question": "Your home?",
                "original_answer": "我的家在河边", "natural_english": "My home is by the river."},
            "audio": {"podcast": "audio_podcast.mp3"}, "meta": {"status": "generated"},
            "timelines": {"podcast": {"lines": [{"text": "My home is by the river.",
                "start": 0, "end": 30}], "words": [], "mode": "estimated"}}}))
        archive.writestr("topics/中文话题/items/i1/audio_podcast.mp3", buffer.getvalue())
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": 844})
        # 验证局域网 HTTP 没有 SubtleCrypto 时仍可导入并计算相同 SHA-256。
        page.add_init_script("Object.defineProperty(crypto, 'subtle', {value: undefined})")
        page.goto(BASE_URL + "/#/import")
        page.locator("#pack-file").set_input_files(path)
        expect(page.locator(".album-card")).to_be_visible()
        assert page.evaluate("packAudioFingerprint(new TextEncoder().encode('abc').buffer)") == (
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        page.locator("#corpus-q").fill("河边")
        expect(page.locator(".corpus-search-result")).to_contain_text("河边")
        page.screenshot(path=str(OUT / f"after-{width}-offline-search.png"), full_page=True)
        page.evaluate("location.hash='#/bank?answer_status=answered&sel=q1'")
        expect(page.locator(".bank-row")).to_have_count(1)
        expect(page.locator("#saved-answer")).to_contain_text("我的家在河边")
        page.screenshot(path=str(OUT / f"after-{width}-offline-answer.png"), full_page=True)
        page.locator("#saved-answer a", has_text="播放音频").click()
        page.wait_for_function("document.getElementById('core-audio').currentTime > 0")
        page.evaluate("const a=document.getElementById('core-audio');"
                      "a.currentTime=9;a.pause()")
        page.reload()
        page.wait_for_function("document.getElementById('core-audio').currentTime >= 9")
        assert page.locator("#core-audio").evaluate("a=>a.src").startswith("blob:")
        page.screenshot(path=str(OUT / f"after-{width}-offline-player.png"), full_page=True)
        browser.close()


def test_draft_cross_browser_conflict_submit_and_typed_search():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context1, context2 = browser.new_context(), browser.new_context()
        a, b = context1.new_page(), context2.new_page()
        state = mock(a)
        mock(b, state)
        a.goto(BASE_URL + "/#/bank?sel=q2")
        a.locator("#bank-answer-input").fill("跨浏览器草稿")
        expect(a.locator("#draft-status")).to_contain_text("已保存")
        b.goto(BASE_URL + "/#/bank?sel=q2")
        expect(b.locator("#bank-answer-input")).to_have_value("跨浏览器草稿")
        b.locator("#bank-answer-input").fill("另一个浏览器更新")
        expect(b.locator("#draft-status")).to_contain_text("已保存")
        a.locator("#bank-answer-input").fill("本页保留文字")
        expect(a.locator("#draft-status")).to_contain_text("保存失败")
        a.locator("#draft-retry").click()
        expect(a.locator("#draft-conflict")).to_contain_text("另一个浏览器更新")
        a.locator("#draft-keep-local").click()
        expect(a.locator("#draft-status")).to_contain_text("已保存")
        state["fail_submit"] = True
        a.locator("#bank-answer-submit").click()
        expect(a.locator("#bank-answer-submit")).to_be_enabled()
        expect(a.locator("#bank-answer-input")).to_have_value("本页保留文字")
        state["fail_submit"] = False
        a.locator("#bank-answer-submit").click()
        expect(a.locator("#agent-prompt-box")).to_have_text("Synthetic command")
        assert not state["drafts"]["q2"]["answer"]
        a.goto(BASE_URL + "/#/topics")
        a.locator("#corpus-q").fill("河边")
        expect(a.locator(".corpus-search-result")).to_contain_text("河边")
        expect(a.locator(".nav-item.active")).to_have_attribute("href", "#/topics")
        a.locator("#corpus-clear").click()
        expect(a.locator(".album-card")).to_be_visible()
        browser.close()


def test_pending_submit_retains_new_draft_and_duplicate_click():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        state = mock(page)
        pending = []
        page.route("**/generation-requests", lambda r: pending.append(r))
        page.goto(BASE_URL + "/#/bank?sel=q2")
        page.locator("#bank-answer-input").fill("提交版本")
        expect(page.locator("#draft-status")).to_contain_text("已保存")
        page.locator("#bank-answer-submit").click()
        page.locator("#bank-answer-submit").evaluate("b => b.click()")
        assert len(pending) == 1
        page.locator("#bank-answer-input").fill("等待期间的新文字")
        pending[0].fulfill(json={"topic_id": "t1", "item_id": "i1",
                                 "agent_prompt": "Synthetic command"})
        expect(page.locator("#agent-prompt-box")).to_be_visible()
        assert state["drafts"]["q2"]["answer"] == "等待期间的新文字"
        page.goto(BASE_URL + "/#/topics")
        page.goto(BASE_URL + "/#/bank?sel=q2")
        expect(page.locator("#bank-answer-input")).to_have_value("等待期间的新文字")
        browser.close()


def test_delayed_search_navigation_and_progress_save_failure():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        state = mock(page)
        page.goto(BASE_URL + "/#/topics")
        pending = []
        page.route("**/search?**", lambda r: pending.append(r))
        page.locator("#corpus-q").fill("迟到的搜索")
        expect(page.locator("#corpus-results")).to_have_attribute("aria-busy", "true")
        page.locator(".nav-item[href='#/practice']").click()
        expect(page.locator(".bank-row")).to_have_count(2)
        pending[0].fulfill(json={"results": [], "total": 0, "page": 1, "pageCount": 0})
        expect(page.locator(".bank-row")).to_have_count(2)
        state["fail_progress"] = True
        page.goto(BASE_URL + "/#/play/t1/i1")
        page.wait_for_function("document.getElementById('core-audio').currentTime >= 8",
                               timeout=3000)
        expect(page.locator("#toast-root")).to_contain_text("收听位置保存失败")
        assert page.locator("#core-audio").evaluate("a=>!a.paused")
        assert page.evaluate("Object.keys(JSON.parse("
                             "localStorage.getItem('q05-listen-pending'))).length")
        page.screenshot(path=str(OUT / "after-1280-progress-failure.png"), full_page=True)
        browser.close()


def test_emergency_draft_preserves_mode_when_service_read_fails():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        state = mock(page)
        page.goto(BASE_URL + "/#/bank?sel=q2")
        state["fail_draft"] = True
        page.locator("[name='bank-gen-mode'][value='api']").check()
        page.locator("#bank-answer-input").fill("断网时的未提交文字")
        expect(page.locator("#draft-status")).to_contain_text("保存失败")
        state["fail_draft_read"] = True
        page.reload()
        expect(page.locator("#bank-answer-input")).to_have_value("断网时的未提交文字")
        expect(page.locator("[name='bank-gen-mode'][value='api']")).to_be_checked()
        browser.close()


def test_completion_saved_before_playlist_advances():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        state = mock(page)
        page.goto(BASE_URL + "/#/play/t1/i1")
        page.wait_for_function("document.getElementById('core-audio').currentTime >= 8.1",
                               timeout=3000)
        for _ in range(60):
            if any(r.get("item_id") == "i1" for r in state.get("progress_writes", [])):
                break
            page.wait_for_timeout(50)
        assert state.get("progress_writes"), "实际播放开始后应发起保存请求"
        page.evaluate("PlayerState.playlist=[{id:'i1',title:'First'},{id:'i2',title:'Next'}];"
                      "PlayerState.currentIndex=0;document.getElementById('core-audio')"
                      ".dispatchEvent(new Event('ended'))")
        for _ in range(60):
            if any(r.get("item_id") == "i1" and r.get("completed")
                   for r in state.get("progress_writes", [])):
                break
            page.wait_for_timeout(50)
        assert any(r.get("item_id") == "i1" and r.get("completed")
                   for r in state.get("progress_writes", [])), state.get("progress_writes")
        browser.close()
