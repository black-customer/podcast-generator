"""2.0 桌面流程，用合成语料和模拟本机分析覆盖键盘、麦克风与导出入口。"""

import io
import json
import os
import re
import wave
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8765")
ITEM = "/api/topics/arcade-test/items/arcade-item"
QUESTION = "Why do you like swimming?"
SENTENCES = [
    {"zh": "游泳能让我下班后放松。", "en": "It helps me unwind after work.",
     "key_chunk": "helps me unwind", "audio": {"scope": "sentence", "start": 1, "end": 2.3},
     "original_error": {"quote": "It help me unwind", "issue": "第三人称单数",
                        "correction": "It helps me unwind"}},
    {"zh": "我尽量每周游两次。", "en": "I try to go twice a week.",
     "key_chunk": "twice a week", "audio": {"scope": "sentence", "start": 2.4, "end": 4}},
]


def _audio() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as file:
        file.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        file.writeframes(b"\x00\x00" * 16000 * 4)
    return buffer.getvalue()


def _shot(page, filename):
    directory = os.environ.get("ARCADE_SCREENSHOT_DIR")
    if directory:
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        animations = "allow" if filename in {"03-recall.png", "07-blitz.png"} else "disabled"
        page.screenshot(path=str(path / filename), full_page=True, animations=animations)


def _demo_audio():
    real = os.environ.get("ARCADE_REAL_AUDIO_DIR")
    if not real:
        lines = [{"speaker": "A", "text": QUESTION, "start": 0, "end": 0.9}, *[
            {"speaker": "B", "text": row["en"], **row["audio"]} for row in SENTENCES
        ]]
        return _audio(), "audio/wav", lines, [{"text": "Why", "start": 0, "end": 0.2}]
    root = Path(real)
    real_timing = json.loads((root / "local-voice.json").read_text(encoding="utf-8"))
    lines = [{**row, "speaker": row["speaker"].upper()} for row in real_timing["spans"]]
    return (root / "local-voice.mp3").read_bytes(), "audio/mpeg", lines, real_timing["words"]


def test_arcade_from_bank_blind_recording_through_blitz():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=[
            "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
        ])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.add_init_script("""(() => {
          window.arcadeClipCalls = [];
          const start = AudioBufferSourceNode.prototype.start;
          AudioBufferSourceNode.prototype.start = function(...args) {
            window.arcadeClipCalls.push(args);
            return start.apply(this, args);
          };
        })()""")
        errors, grades, uploads = [], [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        demo_url = f"{ITEM}/audio/podcast"
        audio_data, media, lines, words = _demo_audio()
        rows = [{**row, "audio": {"scope": "sentence", "start": line["start"],
                                 "end": line["end"]}}
                for row, line in zip(SENTENCES, lines[1:], strict=True)]
        assessment = {"wpm": 118, "long_pauses": 1, "matched_chunks": ["helps me unwind"]}
        blind = {"id": "blind", "url": f"{ITEM}/arcade/recordings/blind",
                 "analysis": {"wpm": 89, "long_pauses": 3}}
        demo = {"question": QUESTION, "status": "ready", "original_answer": "It help me unwind.",
                "source_fingerprint": "test-fingerprint", "dry_run": False, "voice": "golden_self",
                "sentences": rows, "blind": blind, "final": None, "audio_url": demo_url,
                "answer_spans": [row["audio"] for row in rows], "alignment": {
                    "mode": "sse", "lines": lines, "words": words}}
        grade_url = f"**{ITEM}/arcade/grade"
        page.route(grade_url, lambda route: (
            grades.append(route.request.post_data_json), route.fulfill(json={"ok": True})
        ))
        page.route(f"**{ITEM}/arcade", lambda route: route.fulfill(json=demo))
        page.route(f"**{demo_url}", lambda route: route.fulfill(
            body=audio_data, content_type=media))
        page.route(f"**{ITEM}/arcade/recordings/*", lambda route: route.fulfill(
            body=audio_data, content_type=media))
        page.route("**/api/settings", lambda route: route.fulfill(json={
            "llm_available": True, "llm_provider": "deepseek", "llm_api_key_set": True,
            "tts_provider": "kokoro_local", "kokoro_answer_voice": "golden_self", "models": [],
        }))
        page.route("**/api/speech/status", lambda route: route.fulfill(json={
            "available": True, "kokoro": True, "profile": {"finetuned": False},
        }))
        page.route("**/api/arcade/blitz?summary=true", lambda route: route.fulfill(
            json={"due_count": 1}))
        page.route("**/api/arcade/blitz", lambda route: route.fulfill(json={"cards": [{
            **rows[0], "topic_id": "arcade-test", "item_id": "arcade-item",
            "audio_url": demo_url, "source_fingerprint": "test-fingerprint", "sentence_index": 0,
        }]}))
        page.route("**/api/arcade/error-board", lambda route: route.fulfill(json={
            "top": [{"label": "主谓一致", "count": 2}, {"label": "时态", "count": 1}],
            "today_chunks": ["helps me unwind"], "prompt": "引导我用 helps me unwind。",
        }))
        question = {"id": "arcade-q", "text": QUESTION, "part": 1, "topic_name": "游泳",
                    "topic_name_en": "Swimming", "answered": False}
        page.route("**/api/bank/questions?*", lambda route: route.fulfill(json={
            "available": True, "items": [question], "total": 1, "page": 1, "pages": 1,
        }))
        page.route("**/api/jobs/arcade-job", lambda route: route.fulfill(json={"state": "done"}))

        def create(route):
            body = route.request.post_data_json
            assert body["answer"] == "It help me unwind."
            assert body["mode"] == "api" and body["blind_token"] == "blind-token"
            route.fulfill(json={"topic_id": "arcade-test", "item_id": "arcade-item",
                                "job_id": "arcade-job"})

        def recording(route):
            stage = "final" if "stage=final" in route.request.url else "chunk"
            uploads.append(stage)
            route.fulfill(json={"id": stage, "url": f"{ITEM}/arcade/recordings/{stage}",
                                "analysis": assessment})

        page.route("**/api/generation-requests", create)
        page.route("**/api/arcade/transcribe-blind?*", lambda route: route.fulfill(json={
            "blind_token": "blind-token", "transcript": "It help me unwind.",
        }))
        page.route(f"**{ITEM}/arcade/recordings?*", recording)
        page.route(f"**{ITEM}/arcade/export-evolution", lambda route: route.fulfill(
            body=b"synthetic-mp3", content_type="audio/mpeg"))

        page.goto(f"{BASE_URL}/#/today")
        expect(page.get_by_role("heading", name="3 分钟闪电刷句")).to_be_visible()
        expect(page.get_by_text("主谓一致")).to_be_visible()
        _shot(page, "01-home.png")
        page.get_by_role("link", name="去题库选题").click()
        page.locator(".bank-row").first.click()
        expect(page.get_by_role("button", name="一键生成并直接开练")).to_be_visible()
        page.get_by_role("button", name="直接开口盲答").click()
        stop = page.get_by_role("button", name="结束并转写")
        expect(stop).to_be_visible()
        page.wait_for_function("document.querySelector('#arcade-blind').textContent.includes('0:01')")
        stop.click()
        expect(page.locator("[data-stage='1']")).to_be_visible()
        expect(page.get_by_text("It help me unwind", exact=True)).to_be_visible()
        expect(page.locator(".arcade-line").first).to_contain_text(QUESTION)
        longest = max(words, key=lambda word: word["end"] - word["start"])
        token = page.get_by_role("button", name=longest["text"], exact=True).first
        token.click()
        expect(token).to_have_class(re.compile(r"\bspoken\b"))
        _shot(page, "02-listen.png")
        token.blur()
        page.keyboard.press("Space")
        expect(page.locator(".arcade-reaction")).to_be_visible()
        expect(page.locator(".arcade-reveal")).to_be_hidden()
        _shot(page, "03-recall.png")
        page.keyboard.press("Space")
        expect(page.locator(".arcade-reveal")).to_contain_text("helps me unwind")
        page.wait_for_function("window.arcadeClipCalls.length === 1")
        played = page.evaluate("window.arcadeClipCalls[0]")
        assert played[1] == rows[0]["audio"]["start"]
        assert abs(played[1] + played[2] - rows[0]["audio"]["end"]) < 0.001
        _shot(page, "04-reveal.png")
        page.keyboard.down("r")
        expect(page.get_by_role("button", name="结束录音 · 0:01")).to_be_visible()
        page.keyboard.up("r")
        expect(page.get_by_text("识别到 helps me unwind")).to_be_visible()
        page.wait_for_function("window.arcadeClipCalls.length === 3")
        reference, take = page.evaluate("window.arcadeClipCalls.slice(1)")
        assert abs(reference[0] + reference[2] - take[0]) < 0.001
        page.keyboard.press("1")
        expect(page.get_by_text(SENTENCES[1]["zh"])).to_be_visible()
        page.keyboard.press("Space")
        page.keyboard.press("2")
        expect(page.get_by_role("button", name="开始脱稿录音")).to_be_visible()
        _shot(page, "05-final.png")
        page.get_by_role("button", name="开始脱稿录音").click()
        page.get_by_role("button", name="结束录音 · 0:01").click()
        expect(page.get_by_role("heading", name="口语前后对比")).to_be_visible()
        expect(page.get_by_text("89 → 118 WPM")).to_be_visible()
        expect(page.get_by_text("3 → 1 次")).to_be_visible()
        expect(page.locator(".arcade-hit.matched")).to_contain_text("helps me unwind")
        _shot(page, "06-results.png")
        with page.expect_download() as download:
            page.get_by_role("button", name="导出三合一 MP3").click()
        assert download.value.suggested_filename == "口语前后对比.mp3"
        page.get_by_role("link", name="返回首页").click()
        page.get_by_role("link", name="开始刷句").click()
        expect(page.locator("[data-stage='blitz']")).to_be_visible()
        expect(page.locator(".arcade-reveal")).to_be_hidden()
        _shot(page, "07-blitz.png")
        page.keyboard.press("Space")
        page.keyboard.press("1")
        expect(page.get_by_text("本轮刷句完成")).to_be_visible()
        assert [grade["rating"] for grade in grades] == ["good", "again", "good"]
        assert uploads == ["chunk", "final"]
        page.goto(f"{BASE_URL}/#/manage")
        expect(page.locator("#arcade-llm-provider")).to_have_value("deepseek")
        expect(page.get_by_text("已识别个人声纹", exact=False)).to_be_visible()
        expect(page.locator("#role-cards [data-role=a]")).to_have_value("golden_self")
        _shot(page, "08-settings.png")
        assert not errors
        browser.close()
