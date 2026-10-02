"""Q04：合成 UI 回归，不读写用户设置、不发起真实模型调用。"""
import os
import subprocess
from pathlib import Path
from urllib.parse import unquote

import pytest
import requests
from playwright.sync_api import expect, sync_playwright

from tests.e2e.test_oral_review_ui import _mock_api
from tests.e2e.test_study_ui import sample  # noqa: F401

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8765")


def test_navigation_actual_round_and_recording_recovery():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--use-fake-device-for-media-stream",
                                                       "--use-fake-ui-for-media-stream"])
        page = browser.new_page(viewport={"width": 1280, "height": 800},
                                permissions=["microphone"])
        _mock_api(page)
        page.goto(BASE_URL + "/#/today")
        expect(page.locator("#today-start")).to_have_text("开始本轮 · 1 句")
        expect(page.locator(".nav-item.active")).to_have_count(1)
        expect(page.locator(".nav-item[href='#/practice']")).to_have_text("题库")
        page.locator("#today-start").click()
        expect(page.locator("[data-oral='record-start']")).to_have_class("primary")
        page.locator("[data-oral='record-start']").click()
        page.locator("[data-oral='record-stop']").click()
        expect(page.locator("#oral-download")).to_be_visible()
        page.route("**/review-sessions/session-test/actions", lambda r: r.fulfill(
            status=500, json={"detail": "Synthetic failure"}))
        page.on("dialog", lambda d: d.accept())
        page.locator("[data-oral='no-record']").click()
        expect(page.locator("#oral-error")).to_contain_text("失败")
        assert page.evaluate("document.getElementById('oral-preview').src.startsWith('blob:')")
        page.locator("[data-oral='record-save']").click()
        expect(page.locator(".oral-compare")).to_be_visible()
        expect(page.locator("[data-oral='independent']")).not_to_have_class("primary")
        browser.close()


def test_saved_voice_selection_and_single_request():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        calls = []

        def mock(route):
            path = route.request.url.split("?", 1)[0]
            if path.endswith("/settings"):
                route.fulfill(json={"stepfun_api_key_set": True,
                                    "question_voice_id": "male-one",
                                    "answer_voice_id": "female-one"})
            elif path.endswith("/voices"):
                calls.append(path)
                route.fulfill(json=[
                    {"voice_id": "male-one", "gender": "male", "name": "Synthetic man"},
                    {"voice_id": "female-one", "gender": "female", "name": "Synthetic woman"},
                ])
            else:
                route.fulfill(json={})

        page.route("**/api/**", mock)
        page.goto(BASE_URL + "/#/setup")
        expect(page.locator("#setup-grid-q .voice-pick.selected")).to_have_count(1)
        expect(page.locator("#setup-grid-a .voice-pick.selected")).to_have_count(1)
        assert len(calls) == 1
        browser.close()


def test_setup_duplicate_save_and_failure_preserves_input():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        pending = []

        def mock(route):
            if route.request.method == "PUT":
                pending.append(route)
            elif "/voices" in route.request.url:
                route.fulfill(json=[{"voice_id": "lively-girl", "gender": "female"},
                                    {"voice_id": "vibrant-youth", "gender": "male"}])
            else:
                route.fulfill(json={})

        page.route("**/api/**", mock)
        page.goto(BASE_URL + "/#/setup")
        page.locator("#setup-grid-q .voice-pick").wait_for()
        page.locator("#setup-key").fill("synthetic-not-a-real-key")
        button = page.locator("#setup-finish")
        button.click()
        expect(button).to_be_disabled()
        button.evaluate("button => button.click()")
        assert len(pending) == 1
        pending[0].fulfill(status=500, json={"detail": "Synthetic save failure"})
        expect(page.locator("#setup-finish-hint")).to_contain_text("保存失败")
        expect(button).to_be_enabled()
        expect(page.locator("#setup-key")).to_have_value("synthetic-not-a-real-key")
        browser.close()


def test_history_filter_failure_retains_controls():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        _mock_api(page)
        page.goto(BASE_URL + "/#/study-history")
        page.locator("#oral-history-date").wait_for()
        page.locator("#oral-history-date").evaluate("input => input.dataset.retained = 'yes'")
        page.route("**/api/study/history?*", lambda route: route.fulfill(
            status=500, json={"detail": "Synthetic history failure"}))
        page.locator("#oral-history-date").fill("2026-10-02")
        expect(page.locator("#view-retry")).to_be_visible()
        assert page.locator("#oral-history-date").get_attribute("data-retained") == "yes"
        expect(page.locator("#oral-history-date")).to_have_value("2026-10-02")
        browser.close()


def test_delayed_episode_does_not_replace_new_route():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        _mock_api(page)
        pending = []
        page.route("**/api/topics/demo", lambda r: r.fulfill(json={"id": "demo", "items": []}))
        page.route("**/api/topics/demo/episode?*", lambda r: pending.append(r))
        page.goto(BASE_URL + "/#/episode/demo/podcast")
        page.get_by_role("heading", name="整集与章节").wait_for()
        page.locator("#nav-today").click()
        page.locator("#today-start").wait_for()
        pending[0].fulfill(json={"topic_name": "Synthetic episode", "items": [],
                                 "item_count": 0, "total_sec": 0})
        page.wait_for_timeout(100)
        expect(page.locator("#today-start")).to_be_visible()
        browser.close()


@pytest.mark.parametrize("width", [390, 430])
def test_mobile_synthetic_pack_and_lan(sample, width):  # noqa: F811
    tid, _ = sample
    package = requests.get(f"{BASE_URL}/api/pack/export", params={"topics": tid}, timeout=30)
    assert package.status_code == 200
    out = Path(f"data/.tmp/q04-ui/after/mobile-{width}")
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": 844})
        page.goto(BASE_URL + "/#/import")
        page.locator("#pack-lan-btn").wait_for()
        page.screenshot(path=str(out / "import.png"), full_page=True)
        page.route("http://192.168.1.5:8765/api/pack/export", lambda r: r.fulfill(
            body=package.content, content_type="application/zip",
            headers={"Access-Control-Allow-Origin": "*",
                     "Access-Control-Allow-Headers": "X-Lan-Token",
                     "Access-Control-Allow-Methods": "GET,OPTIONS"}))
        page.locator("#pack-addr").fill("http://192.168.1.5:8765")
        page.locator("#pack-token").fill("synthetic-pairing")
        page.locator("#pack-lan-btn").click()
        page.locator(".album-card").first.wait_for()
        page.screenshot(path=str(out / "corpus.png"), full_page=True)
        assert page.evaluate("PackState.active")
        page.locator(".album-card").first.click()
        page.locator(".track-row").first.click()
        page.locator(".transcript-row").first.wait_for()
        page.wait_for_function("document.getElementById('core-audio').duration > 0")
        page.locator(".transcript-row").last.click()
        assert page.evaluate("document.getElementById('core-audio').currentTime") > 0
        page.locator(".reference-tab.active").click()
        expect(page.locator("body")).to_have_class(
            "reading-notes-theme pack-mode player-route hide-zh")
        page.screenshot(path=str(out / "player.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.locator(".desktop-study-nav:visible").count() == 0
        browser.close()


def test_recording_download_matches_mime():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL + "/#/setup")
        for mime, suffix in (("audio/webm;codecs=opus", "webm"), ("audio/ogg", "ogg"),
                             ("audio/mp4", "m4a")):
            assert page.evaluate("mime => ExperienceUI.recordingExtension(mime)", mime) == suffix
        browser.close()


@pytest.mark.parametrize("width,height", [(1536, 1024), (1280, 800), (1024, 768)])
def test_desktop_synthetic_screenshots(sample, width, height):  # noqa: F811
    tid, iid = sample
    item = requests.get(f"{BASE_URL}/api/topics/{tid}/items/{iid}", timeout=10).json()
    topic = requests.get(f"{BASE_URL}/api/topics/{tid}", timeout=10).json()
    audio = requests.get(f"{BASE_URL}/api/topics/{tid}/items/{iid}/audio/podcast", timeout=10)
    assert audio.status_code == 200
    summary = {"id": tid, "name": "合成验收 · Daily life", "category": "ielts",
               "stats": {"total": 1, "generated": 1, "ready": 0, "empty": 0, "error": 0},
               "total_sec": 8, "items": topic["items"]}
    reference = os.environ.get("Q04_REFERENCE") == "1"
    out = Path(f"data/.tmp/q04-ui/{'before' if reference else 'after'}/{width}")
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        if reference:
            def old_asset(route):
                path = route.request.url.split("/static/", 1)[1]
                if path.endswith((".js", ".css")):
                    source = subprocess.check_output(["git", "show", f"l04:web/{path}"])
                    route.fulfill(body=source, content_type="text/css" if path.endswith(".css")
                                  else "text/javascript")
                else:
                    route.continue_()

            page.route("**/static/**", old_asset)
            index = subprocess.check_output(["git", "show", "l04:web/index.html"])
            page.route(BASE_URL + "/", lambda route: route.fulfill(
                body=index, content_type="text/html"))
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def mock(route):
            path = unquote(route.request.url.split("?", 1)[0])
            if path.endswith("/api/topics"):
                body = [summary]
            elif path.endswith("/api/health"):
                body = {"version": "synthetic", "mode": "dry_run", "ffmpeg": {"ok": True}}
            elif path.endswith("/api/study/review"):
                body = [{"topic_id": tid, "item_id": iid, "sentence_index": 0,
                         "topic_name": "合成验收", "zh": "我通常下班后去散步。",
                         "source": item["question"]}]
            elif path.endswith("/api/settings"):
                body = {"tts_provider": "stepfun", "dry_run": True,
                        "stepfun_api_key_set": False, "fish_api_key_set": False,
                        "question_voice_id": "lively-girl", "answer_voice_id": "vibrant-youth",
                        "models": ["s2-pro"], "model": "s2-pro"}
            elif path.endswith("/api/voices"):
                body = [{"voice_id": "lively-girl", "gender": "female", "name": "合成女声",
                         "provider": "stepfun"},
                        {"voice_id": "vibrant-youth", "gender": "male", "name": "合成男声",
                         "provider": "stepfun"}]
            elif path.endswith("/api/bank/questions"):
                body = {"available": True, "total": 1, "page": 1, "pageCount": 1,
                        "topics": [], "sets": [], "items": [{"id": "sample-question",
                            "part": 2, "text": "Describe a place where you enjoy walking.\n"
                            "You should say where it is, who you go with, and why you like it.",
                            "text_zh": "描述一个你喜欢散步的地方。说明地点、同行的人和原因。",
                            "topic_name": "Daily life", "topic_name_en": "Daily life"}]}
            elif path.endswith(f"/api/topics/{tid}"):
                body = topic
            elif path.endswith(f"/api/topics/{tid}/episode"):
                body = {"topic_name": "合成整集", "item_count": 1, "total_sec": 8,
                        "items": [{"id": iid, "title": item["question"], "offset_sec": 0}]}
            elif path.endswith(f"/api/topics/{tid}/episode/audio"):
                route.fulfill(body=audio.content, content_type="audio/mpeg")
                return
            elif path.endswith("/api/jobs/synthetic"):
                body = {"state": "running", "phase": "tts"}
            elif path.endswith(f"/api/topics/{tid}/items/{iid}"):
                body = item
            else:
                route.fallback()
                return
            route.fulfill(json=body)

        _mock_api(page)
        page.route("**/api/**", mock)

        def capture(name, url, selector):
            target = BASE_URL + "/" + url
            page.goto(target)
            page.reload()
            page.locator(selector).first.wait_for()
            page.screenshot(path=str(out / f"{name}.png"), full_page=True)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), name
            if not reference:
                assert page.locator(".nav-item.active").count() <= 1, name

        capture("today", "#/today", "#today-start")
        capture("oral-prompt", "#/oral-review/session-test", "#oral-recorder")
        page.locator("[data-oral='no-record']").click()
        page.locator(".oral-compare").wait_for()
        page.screenshot(path=str(out / "oral-compare.png"), full_page=True)
        page.locator("[data-oral='independent']").click()
        page.get_by_role("heading", name="本轮口答完成").wait_for()
        page.screenshot(path=str(out / "oral-summary.png"), full_page=True)
        capture("history", "#/study-history", ".oral-history")
        capture("setup", "#/setup", "#setup-grid-q .voice-pick")
        capture("settings", "#/manage", "#role-cards .voice-pick")
        page.locator(".content-admin > summary").click()
        page.screenshot(path=str(out / "advanced-management.png"), full_page=True)
        capture("voices", "#/voices", ".voice-card")
        capture("bank", "#/practice?part=2", ".bank-row")
        page.locator(".bank-row").click()
        page.locator("#bank-answer-input").wait_for()
        page.screenshot(path=str(out / "answer-long-question.png"), full_page=True)
        page.evaluate("ids => showAgentWait({topic_id: ids[0], item_id: ids[1], "
                      "agent_prompt: '合成验收指令：保留原始意思，按三份英文文本契约完成。'})",
                      [tid, iid])
        page.screenshot(path=str(out / "agent-wait.png"), full_page=True)
        page.evaluate("ids => showApiJobWait({topic_id: ids[0], item_id: ids[1], "
                      "job_id: 'synthetic'})",
                      [tid, iid])
        page.screenshot(path=str(out / "api-wait.png"), full_page=True)
        capture("corpus", "#/topics", ".album-card")
        capture("topic", f"#/topic/{tid}", ".track-row")
        capture("player", f"#/play/{tid}/{iid}", ".transcript-row")
        capture("episode", f"#/episode/{tid}/podcast", "#ep-chapters")
        capture("done", f"#/done/{tid}/{iid}", ".study-done")
        capture("learning-intro", f"#/learn/{tid}/{iid}", ".study-intro")
        page.locator("#study-begin").click()
        page.locator(".study-recorder").wait_for()
        page.screenshot(path=str(out / "before-recording.png"), full_page=True)
        page.locator("[data-act='skip-record']").click()
        page.locator(".study-word").first.wait_for()
        page.screenshot(path=str(out / "dictation.png"), full_page=True)
        page.locator(".study-word").first.fill("Wrong")
        page.locator("[data-act='check']").click()
        page.screenshot(path=str(out / "dictation-feedback.png"), full_page=True)
        page.locator("[data-act='hint']").click()
        page.locator("#study-hint").wait_for(state="visible")
        page.screenshot(path=str(out / "dictation-hint.png"), full_page=True)
        requests.patch(f"{BASE_URL}/api/topics/{tid}/items/{iid}/study/progress",
                       json={"stage": "chinese"}, timeout=10).raise_for_status()
        capture("chinese-recording", f"#/learn/{tid}/{iid}", ".study-full-chinese")
        requests.patch(f"{BASE_URL}/api/topics/{tid}/items/{iid}/study/progress",
                       json={"stage": "recall"}, timeout=10).raise_for_status()
        capture("recall-recording", f"#/learn/{tid}/{iid}", ".study-recorder")
        requests.patch(f"{BASE_URL}/api/topics/{tid}/items/{iid}/study/progress",
                       json={"stage": "summary"}, timeout=10).raise_for_status()
        capture("learning-summary", f"#/learn/{tid}/{iid}", ".study-recordings, .study-task")
        capture("sentence-library", "#/review", ".study-review-list")
        capture("sentence-detail", f"#/review/{tid}/{iid}/0", "#oral-card-control")
        capture("import", "#/import", "#pack-lan-btn")
        assert not errors, errors
        browser.close()
