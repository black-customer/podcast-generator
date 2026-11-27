"""验证桌面词书书架、短局和不提交复习结果的热身。"""

import io
import os
import re
import wave
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8765")


def _sample_audio() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        audio.writeframes(b"\0\0" * 16000)
    return buffer.getvalue()


def test_shelf_and_home_warmup():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000},
                                service_workers="block")
        enabled, grades = set(), []
        deck_page = page.request.get(BASE + "/api/decks").json()
        sample = {"card_kind": "deck", "source_type": "deck", "deck_title": "自然对话引擎",
                  "deck_url": "/api/decks/conversation-engine/cards/give-me-a-second",
                  "audio_url": "/synthetic-warmup.wav", "scaffolding_level": 1,
                  "id": "deck:demo", "source_fingerprint": "demo", "en": "Give me a second.",
                  "zh": "给我几秒钟。", "trigger_context": "同事正等你打开邮件。",
                  "key_chunk": "give me a second", "cloze_prompt": "[G___] [m_] [a_] [s_____]."}

        def shelf(route):
            for book in deck_page["decks"]:
                book["enabled"] = book["id"] in enabled
                if book["id"] == "my-speaking":
                    book["units"], book["progress"], book["active_unit"] = [], {
                        "unseen": 0, "learning": 0, "mastered": 0}, None
            route.fulfill(json=deck_page)

        def toggle(route):
            key = route.request.url.split("/")[-2]
            if route.request.post_data_json["enabled"]:
                enabled.add(key)
            else:
                enabled.remove(key)
            route.fulfill(json={"id": key, "enabled": key in enabled})

        page.route("**/api/decks", shelf)
        page.route("**/api/decks/*/toggle", toggle)
        page.route("**/api/decks/*/cards/*/grade", lambda route: (
            grades.append(route.request.post_data_json), route.fulfill(json={})))
        next_sample = {**sample, "en": "Let me think.", "key_chunk": "let me think",
                       "trigger_context": "朋友问你最喜欢哪场演出。"}
        page.route("**/api/arcade/blitz?*", lambda route: route.fulfill(json={
            "cards": [sample, next_sample] if "warmup=true" in route.request.url else
            [sample] * (3 if "limit=3" in route.request.url else 8), "due_count": 0,
        }))
        page.route("**/synthetic-warmup.wav", lambda route: route.fulfill(
            body=_sample_audio(), content_type="audio/wav"))
        page.goto(BASE + "/#/decks")
        for label in ("通用口语", "日常生活与社交", "雅思口语专项", "个人词书"):
            expect(page.get_by_role("heading", name=label, exact=True)).to_be_visible()
        page.get_by_role("button", name="启用自然对话引擎").click()
        expect(page.get_by_role("button", name="暂停自然对话引擎")).to_be_visible()
        shots = os.environ.get("DECK_SCREENSHOT_DIR")
        if shots:
            path = Path(shots)
            path.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(path / "shelf-desktop.png"), full_page=True)
        page.get_by_role("button", name="开始学习").first.click()
        expect(page).to_have_url(re.compile(r"#/today\?deck=conversation-engine$"))
        page.get_by_role("button", name="先刷 3 张").click()
        expect(page.locator("#arcade-home-progress")).to_have_text("第 1 / 3 张")
        page.get_by_role("button", name="先听 2 分钟").click()
        expect(page.get_by_role("region", name="听力热身")).to_be_visible()
        page.get_by_role("button", name="暂停").click()
        expect(page.get_by_role("button", name="继续播放")).to_be_visible()
        page.get_by_label("播放速度").select_option("0.85")
        page.get_by_role("button", name="继续播放").click()
        expect(page.get_by_role("mark")).to_have_text("Give me a second")
        expect(page.locator(".arcade-warmup [role=status]")).to_have_text("听示范")
        if shots:
            page.screenshot(path=str(path / "warmup-desktop.png"), full_page=True)
        expect(page.locator("[data-warmup-context]")).to_have_text(next_sample["trigger_context"])
        page.keyboard.press("1")
        page.get_by_role("button", name="切回开口练习").click()
        expect(page.locator("#arcade-home-progress")).to_have_text("第 1 / 3 张")
        assert grades == []
        page.set_viewport_size({"width": 390, "height": 844})
        page.goto(BASE + "/#/decks")
        expect(page.get_by_role("heading", name="口语词书")).to_be_visible()
        expect(page.get_by_role("heading", name="个人词书")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth === innerWidth")
        if shots:
            page.screenshot(path=str(path / "shelf-narrow.png"), full_page=True)
        browser.close()
