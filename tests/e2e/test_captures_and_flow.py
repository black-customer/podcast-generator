"""浏览器演练素材分拣、来源筛选与轮内重考。"""

import base64
import json
import os
import wave
from io import BytesIO
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from server.prosody import annotate_sentence
from tests.test_captures import PIXEL, card

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8765")
ID = "card_9f8e7d6c5b4a3210"


def test_capture_inbox_and_micro_session():
    parent = {"id": "cap_a1b2c3d4e5f67890", "source_type": "scene", "title": "合成场景 · 04:18",
              "source": {"assets": ["frame.png"], "note_id": "test-note", "time": 258,
                         "series_title": "合成场景", "episode_title": "第一集",
                         "source_url": "https://www.bilibili.com/video/BV1234567890?t=258"}}
    fixture = {**card(), "id": ID, "capture_id": parent["id"], "capture": parent,
               "card_kind": "capture", "source_type": "scene", "scaffolding_level": 1,
               "status": "inbox", "cloze_prompt": "I didn't mean to [p__] [y__] [o_] the spot.",
               "key_chunk": "put you on the spot", "source_fingerprint": "sample",
               "audio_url": f"/api/cards/{ID}/audio",
               "audio": {"scope": "sentence", "start": 0, "end": None}}
    fixture["prosody"] = annotate_sentence(fixture["en"])
    grades, snippets, imports = [], [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def mock(route):
            method, url = route.request.method, route.request.url
            tail = url.split("/api/", 1)[1]
            if tail == "captures":
                data = {"captures": [{"id": parent["id"], "title": "随手摘录",
                                     "extract_state": "pending"}] if snippets else []}
            elif tail == "captures/snippet":
                snippets.append(route.request.post_data_json)
                data = {"id": parent["id"]}
            elif tail == "captures/scenes/import-json":
                imports.append(route.request.post_data_json)
                data = {"imported": 1, "duplicates": 0}
            elif tail == "cards":
                data = {"cards": [fixture]}
            elif tail.endswith("/approve"):
                fixture["status"] = "active"
                data = fixture
            elif tail.startswith("arcade/blitz"):
                data = {"cards": [fixture] if fixture["status"] == "active" else [],
                        "due_count": 1, "inbox_count": 0, "session_limit": 8,
                        "reaction_timer_enabled": False}
            elif tail.endswith("/grade") and method == "POST":
                rating = route.request.post_data_json["rating"]
                grades.append(rating)
                if rating == "suspend":
                    fixture["status"] = "archived"
                data = {"scaffolding_level": 1}
            else:
                route.fallback()
                return
            route.fulfill(json=data)

        page.route("**/api/**", mock)
        page.route("**/assets/frame.png", lambda r: r.fulfill(
            body=base64.b64decode(PIXEL.split(",")[1]), content_type="image/png"))
        audio = BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            wav.writeframes(bytes(32000))
        page.route(f"**/cards/{ID}/audio", lambda r: r.fulfill(
            body=audio.getvalue(), content_type="audio/wav"))
        page.goto(BASE_URL + "/#/captures")
        expect(page.get_by_role("heading", name=fixture["target_chunk"])).to_be_visible()
        expect(page.get_by_role("img", name="素材的原始截屏")).to_be_visible()
        shots = os.environ.get("CAPTURE_SCREENSHOT_DIR")
        if shots:
            Path(shots).mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(Path(shots) / "inbox.png"))
        page.keyboard.press("Enter")
        expect(page.get_by_text("已入库，本机正在准备示范音频。")).to_be_visible()
        page.get_by_role("button", name="导入新素材").first.click()
        page.get_by_label("英文摘录").fill("This is a synthetic example.")
        page.get_by_role("button", name="保存素材").click()
        expect(page.get_by_text("素材已保存，可在收件箱提炼。")).to_be_visible()
        assert snippets[0]["text"] == "This is a synthetic example."
        page.get_by_role("button", name="导入新素材").first.click()
        backup = {"format": "caption-study-backup", "schemaVersion": 1, "notes": [{
            "id": "test-note", "time": 258,
            "source": {"url": "https://www.bilibili.com/video/BV1234567890"}, "imageUrl": PIXEL,
        }]}
        page.locator("#scene-backup").set_input_files({
            "name": "scenes.json", "mimeType": "application/json",
            "buffer": json.dumps(backup).encode(),
        })
        expect(page.get_by_text("已导入 1 条，跳过 0 条重复记录。")).to_be_visible()
        assert imports == [backup]
        page.get_by_role("link", name="返回今日练习").click()
        expect(page.locator(".chunk-cloze")).to_contain_text("[p__]")
        page.get_by_role("button", name="看剧表达").click()
        scene_filter = page.get_by_role("button", name="看剧表达")
        expect(scene_filter).to_have_attribute("aria-pressed", "true")
        expect(page.locator(".arcade-reaction")).to_have_count(0)
        page.locator("[data-review-source=scene]").blur()
        page.keyboard.press("Space")
        expect(page.locator(".arcade-plain-answer")).to_be_visible()
        page.keyboard.press("p")
        expect(page.locator(".arcade-pronunciation")).to_be_visible()
        page.keyboard.press("2")
        expect(page.locator("#arcade-home-progress")).to_contain_text("重考")
        page.keyboard.press("Space")
        page.keyboard.press("1")
        expect(page.get_by_role("heading", name="今日一局达标")).to_be_visible()
        assert grades == ["again", "good"]
        page.get_by_role("button", name="再来一局").click()
        expect(page.locator(".chunk-cloze")).to_be_visible()
        page.set_viewport_size({"width": 430, "height": 900})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        if shots:
            page.screenshot(path=str(Path(shots) / "practice-narrow.png"))
        page.keyboard.press("x")
        expect(page.get_by_role("heading", name="今日一局达标")).to_be_visible()
        assert grades[-1] == "suspend" and not errors
        browser.close()
