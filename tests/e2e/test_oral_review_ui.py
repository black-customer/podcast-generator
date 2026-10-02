"""L04 桌面口答流程：今日入口、答案隐藏、恢复与录音异常。"""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8765")
CARD = {"id": "card-1", "topic_id": "demo", "item_id": "demo-item", "sentence_index": 0,
        "question": "What do you do after work?", "zh": "我下班后散步。",
        "source": "What do you do after work?", "due_date": "2026-09-30",
        "paused": False, "availability": "ready"}
ENGLISH = "I go for a walk after work."


def _screenshot(page, name):
    folder = Path("data/.tmp/oral-review-ui")
    folder.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(folder / name), full_page=True)


def _mock_api(page, recording_failure=False, unavailable=False, delayed_action=False):
    session = {"id": "session-test", "card_ids": ["card-1"], "current_index": 0,
               "state": "active", "phase": "prompt", "hint_used": False,
               "responded": False, "recording_id": None, "no_recording": False,
               "results": [], "current_card": dict(CARD)}
    data = {"recording_failure": recording_failure, "attempts": 0}

    def answer():
        card = dict(CARD)
        if unavailable:
            card["availability"] = "missing"
        if session["phase"] == "compare":
            card.update({"en": ENGLISH, "explanation": "go for a walk 表示散步。",
                         "usage": "描述下班后的活动。"})
        session["current_card"] = card if session["state"] == "active" else None

    def handler(route):
        url = route.request.url.split("?", 1)[0]
        method = route.request.method
        if url.endswith("/api/study/today"):
            body = {"today": "2026-09-30", "due_count": 1, "due_preview": [CARD],
                    "continue_learning": [], "active_session_id": None,
                    "needs_material_count": 0, "history": {"undated_legacy_count": 0}}
        elif url.endswith("/api/study/review-sessions") and method == "POST":
            body = session
        elif url.endswith("/api/study/review-sessions/session-test") and method == "GET":
            answer()
            body = session
        elif url.endswith("/api/study/review-sessions/session-test/actions"):
            import json

            action = json.loads(route.request.post_data)["action"]
            if action == "hint":
                session["hint_used"] = True
                body = {**session, "hint_text": ENGLISH}
            elif action == "skip":
                session.update({"state": "completed", "current_index": 1,
                                "current_card": None, "results": [{
                                    "card_id": "card-1", "zh": CARD["zh"], "outcome": "skipped"}]})
                body = session
            else:
                session["phase"] = "compare"
                session["no_recording"] = True
                session["responded"] = action == "answered_without_recording"
                if action == "show_answer":
                    session["hint_used"] = True
                answer()
                body = session
                if delayed_action:
                    data["pending_route"] = route
                    data["pending_body"] = dict(body)
                    return
        elif url.endswith("/api/study/review-sessions/session-test/recording"):
            if data["recording_failure"]:
                data["recording_failure"] = False
                route.fulfill(status=500, json={"detail": "synthetic disk failure"})
                return
            session.update({"phase": "compare", "responded": True,
                            "recording_id": "record-1", "no_recording": False})
            answer()
            body = {"recording": {"id": "record-1"}, "session": session}
        elif url.endswith("/api/study/review-sessions/session-test/attempts"):
            data["attempts"] += 1
            session.update({"state": "completed", "current_index": 1,
                            "current_card": None, "results": [{
                                "card_id": "card-1", "zh": CARD["zh"],
                                "outcome": "independent", "recorded": bool(session["recording_id"]),
                                "next_due_date": "2026-10-03"}]})
            body = {"rating": "independent", "recorded": bool(session["recording_id"]),
                    "spoken_self_report": True, "next_due_date": "2026-10-03"}
        elif url.endswith("/api/study/history"):
            body = {"dictation_passed_total": 1, "dictation_undated_count": 0,
                    "undated_legacy_count": 0, "sources": [{"topic_id": "demo",
                        "item_id": "demo-item", "question": CARD["question"]}],
                    "days": [{"date": "2026-09-30",
                    "attempt_count": 1, "distinct_sentence_count": 1,
                    "dictation_passed_count": 1, "ratings": {
                        "independent": 1, "needs_hint": 0, "unable": 0},
                    "attempts": [{"topic_id": "demo", "item_id": "demo-item",
                        "question": CARD["question"], "zh": CARD["zh"],
                        "rating": "independent", "recorded": bool(session["recording_id"]),
                        "recording_id": session["recording_id"],
                        "next_due_date": "2026-10-03"}]}]}
        else:
            route.continue_()
            return
        route.fulfill(json=body)

    page.route("**/api/study/**", handler)
    return data


def test_today_round_no_recording_and_history():
    out = Path("data/.tmp/oral-review-ui")
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1536, "height": 1024})
        data = _mock_api(page)
        try:
            page.goto(f"{BASE_URL}/")
            page.get_by_role("heading", name="今天练什么").wait_for()
            assert ENGLISH not in page.locator(".today-page").inner_text()
            page.screenshot(path=str(out / "today.png"), full_page=True)
            page.locator("#today-start").click()
            page.locator(".oral-prompt").wait_for()
            assert ENGLISH not in page.locator(".oral-page").inner_text()
            page.screenshot(path=str(out / "prompt.png"), full_page=True)
            page.reload()
            page.locator(".oral-prompt").wait_for()
            page.locator("[data-oral='no-record']").click()
            page.locator(".oral-compare").wait_for()
            assert ENGLISH in page.locator(".oral-compare").inner_text()
            assert page.locator("[data-oral='independent']").is_enabled()
            page.screenshot(path=str(out / "compare.png"), full_page=True)
            page.locator("[data-oral='independent']").click()
            page.get_by_role("heading", name="本轮口答完成").wait_for()
            assert "未录音／本人自评" in page.locator(".oral-page").inner_text()
            _screenshot(page, "round-complete.png")
            assert data["attempts"] == 1
            page.goto(f"{BASE_URL}/#/study-history")
            page.get_by_role("heading", name="口答学习记录").wait_for()
            assert page.locator(".history-facts div").first.inner_text().splitlines() == [
                "默写通过", "1 句"]
            page.screenshot(path=str(out / "history.png"), full_page=True)
        finally:
            browser.close()


def test_unavailable_material_can_be_skipped_without_rating():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1536, "height": 1024})
        _mock_api(page, unavailable=True)
        try:
            page.goto(f"{BASE_URL}/#/oral-review/session-test")
            page.get_by_text("材料已变化或条目已删除", exact=False).wait_for()
            _screenshot(page, "material-unavailable.png")
            assert page.locator("[data-oral='no-record']").count() == 0
            page.locator("[data-oral='skip']").click()
            page.get_by_role("heading", name="本轮口答完成").wait_for()
            assert "本轮跳过" in page.locator(".oral-page").inner_text()
        finally:
            browser.close()


def test_recording_navigation_cancel_preserves_current_recording():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--use-fake-device-for-media-stream",
                                                    "--use-fake-ui-for-media-stream"])
        context = browser.new_context(viewport={"width": 1536, "height": 1024},
                                      permissions=["microphone"])
        page = context.new_page()
        _mock_api(page)
        try:
            page.goto(f"{BASE_URL}/#/oral-review/session-test")
            page.locator("[data-oral='record-start']").click()
            page.wait_for_function("document.querySelector('#oral-rec-status')?.textContent.includes('正在录音')")
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.locator("#nav-today").click()
            page.wait_for_url("**/#/oral-review/session-test")
            assert page.locator("[data-oral='record-stop']").is_enabled()
            page.locator("[data-oral='record-stop']").click()
            page.locator("#oral-download").wait_for(state="visible")
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator("[data-oral='no-record']").click()
            page.locator(".oral-compare").wait_for()
        finally:
            browser.close()


def test_hint_and_microphone_denial_keep_self_report_available():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1536, "height": 1024})
        context.add_init_script("""Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
          value: async () => { throw new DOMException('Permission denied', 'NotAllowedError'); }
        });""")
        page = context.new_page()
        _mock_api(page)
        try:
            page.goto(f"{BASE_URL}/#/oral-review/session-test")
            page.locator("[data-oral='record-start']").click()
            page.wait_for_function("document.querySelector('#oral-rec-status')?.textContent.includes('无法使用麦克风')")
            assert page.locator("[data-oral='record-start']").is_enabled()
            _screenshot(page, "microphone-denied.png")
            page.locator("[data-oral='hint']").click()
            page.locator("#oral-hint").wait_for(state="visible")
            page.locator("[data-oral='no-record']").click()
            page.locator(".oral-compare").wait_for()
            assert page.locator("[data-oral='independent']").is_disabled()
            assert page.locator("[data-oral='needs_hint']").is_enabled()
        finally:
            browser.close()


def test_recording_save_failure_keeps_blob_for_retry():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--use-fake-device-for-media-stream",
                                                    "--use-fake-ui-for-media-stream"])
        context = browser.new_context(viewport={"width": 1536, "height": 1024},
                                      permissions=["microphone"])
        page = context.new_page()
        _mock_api(page, recording_failure=True)
        try:
            page.goto(f"{BASE_URL}/#/oral-review/session-test")
            page.locator("[data-oral='record-start']").click()
            page.wait_for_timeout(350)
            page.locator("[data-oral='record-stop']").click()
            page.locator("[data-oral='record-save']").wait_for(state="visible")
            page.locator("[data-oral='record-save']").click()
            page.wait_for_function(
                "document.querySelector('#oral-error')?.textContent.includes('synthetic')"
            )
            assert page.locator("#oral-download").is_visible()
            _screenshot(page, "recording-save-failed.png")
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.locator("[data-oral='no-record']").click()
            assert page.locator("[data-oral='no-record']").is_enabled()
            page.locator("[data-oral='record-save']").click()
            page.locator(".oral-compare").wait_for()
            assert page.locator("audio[aria-label='回听本次口答']").count() == 1
        finally:
            browser.close()


def test_narrow_desktop_layout_has_no_horizontal_overflow():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1024, "height": 768})
        _mock_api(page)
        try:
            for path, selector in (("#/today", ".today-page"),
                                   ("#/study-history", ".oral-history")):
                page.goto(f"{BASE_URL}/{path}")
                page.locator(selector).wait_for()
                assert page.evaluate("document.body.scrollWidth <= innerWidth")
                assert page.evaluate("document.querySelector('#app').scrollWidth <= "
                                     "document.querySelector('#app').clientWidth + 1")
        finally:
            browser.close()


def test_late_oral_action_does_not_replace_new_route():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1536, "height": 1024})
        data = _mock_api(page, delayed_action=True)
        try:
            page.goto(f"{BASE_URL}/#/oral-review/session-test")
            page.locator("[data-oral='no-record']").click()
            page.locator("#nav-today").click()
            page.get_by_role("heading", name="今天练什么").wait_for()
            data["pending_route"].fulfill(json=data["pending_body"])
            page.wait_for_timeout(200)
            assert page.locator(".today-page").count() == 1
            assert page.locator(".oral-compare").count() == 0
        finally:
            browser.close()
