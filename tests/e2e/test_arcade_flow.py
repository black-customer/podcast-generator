"""桌面闭环用合成语料覆盖范围抽题、双轨录音、重试、复习与电台。"""

import io
import json
import os
import re
import wave
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from server.prosody import annotate_sentence

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
        animations = "allow" if filename in {"01-home.png", "06-recall.png"} else "disabled"
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
        prompt = lines[0]["text"]
        rows = [{**row, "prosody": annotate_sentence(row["en"]),
                 "audio": {"scope": "sentence", "start": line["start"],
                                 "end": line["end"]}}
                for row, line in zip(SENTENCES, lines[1:], strict=True)]
        assessment = {"wpm": 118, "long_pauses": 1, "matched_chunks": ["helps me unwind"]}
        blind = {"id": "blind", "url": f"{ITEM}/arcade/recordings/blind",
                 "analysis": {"wpm": 89, "long_pauses": 3}}
        demo = {"question": prompt, "status": "ready", "original_answer": "It help me unwind.",
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
            "llm_configured": True, "llm_provider": "deepseek", "llm_api_key_set": True,
            "tts_provider": "kokoro_local", "kokoro_answer_voice": "golden_self", "models": [],
        }))
        page.route("**/api/speech/status", lambda route: route.fulfill(json={
            "available": True, "kokoro": True, "profile": {"finetuned": False},
        }))
        page.route("**/api/arcade/blitz?include_pending=true", lambda route: route.fulfill(
            json={"due_count": 1, "cards": [{
            **rows[0], "topic_id": "arcade-test", "item_id": "arcade-item",
            "audio_url": demo_url, "source_fingerprint": "test-fingerprint", "sentence_index": 0,
        }]}))
        page.route("**/api/arcade/error-board", lambda route: route.fulfill(json={
            "top": [{"label": "主谓一致", "count": 2}, {"label": "时态", "count": 1}],
            "today_chunks": ["helps me unwind"], "prompt": "引导我用 helps me unwind。",
        }))
        question = {"id": "arcade-q", "text": prompt, "part": 1, "topic_name": "游泳",
                    "topic_name_en": "Swimming", "answered": False}
        page.route("**/api/bank/questions?*", lambda route: route.fulfill(json={
            "available": True, "items": [question], "total": 1, "page": 1, "pageCount": 1,
            "topics": [{"id": "swim", "name_zh": "游泳", "count": 1}],
            "sets": [{"id": "fall", "name_zh": "秋季题库", "count": 1}],
        }))
        page.route("**/api/jobs/arcade-job", lambda route: route.fulfill(json={
            "state": "error", "errors": [{"message": "当前 Key 无文本模型权限（HTTP 403）"}],
        }))
        page.route("**/api/jobs/retry-job", lambda route: route.fulfill(json={"state": "done"}))
        page.route(f"**{ITEM}/retry-api", lambda route: route.fulfill(json={
            "job_id": "retry-job", "topic_id": "arcade-test", "item_id": "arcade-item",
        }))

        def create(route):
            body = route.request.post_data_json
            assert body["answer"] == "It help me unwind."
            assert body["chinese_intent"] == "下班后放松。"
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
        page.route("**/api/arcade/transcribe-intent?*", lambda route: route.fulfill(json={
            "transcript": "下班后放松。",
        }))
        page.route(f"**{ITEM}/arcade/recordings?*", recording)
        page.route(f"**{ITEM}/arcade/export-evolution", lambda route: route.fulfill(
            body=b"synthetic-mp3", content_type="audio/mpeg"))

        page.goto(f"{BASE_URL}/#/today")
        expect(page.get_by_text(SENTENCES[0]["zh"], exact=True)).to_be_visible()
        _shot(page, "01-home.png")
        page.get_by_text("我的口语病历榜").click()
        expect(page.get_by_text("主谓一致")).to_be_visible()
        page.get_by_role("button", name="范围随机抽题").click()
        page.locator("#arcade-draw [name=set]").select_option("fall")
        page.locator("#arcade-draw [name=topic]").select_option("swim")
        _shot(page, "02-draw.png")
        with page.expect_request(lambda request: "random=1" in request.url) as draw:
            page.get_by_role("button", name="随机抽题", exact=True).click()
        assert "part=all" in draw.value.url and "set_filter=fall" in draw.value.url
        assert "topic=swim" in draw.value.url
        expect(page.get_by_role("button", name="一键生成并直接开练")).to_be_visible()
        page.get_by_role("button", name="录制英文盲答").click()
        stop = page.get_by_role("button", name="结束并转写")
        expect(stop).to_be_visible()
        page.wait_for_function("document.querySelector('#arcade-blind').textContent.includes('0:01')")
        stop.click()
        expect(page.locator("#bank-answer-input")).to_have_value("It help me unwind.")
        page.get_by_role("button", name="录制中文意图").click()
        expect(page.locator("#arcade-intent")).to_contain_text("0:01")
        page.locator("#arcade-intent").click()
        expect(page.locator("#arcade-intent-input")).to_have_value("下班后放松。")
        expect(page.get_by_role("button", name="一键生成并直接开练")).to_be_enabled()
        _shot(page, "03-dual-capture.png")
        page.get_by_role("button", name="一键生成并直接开练").click()
        expect(page.locator("#api-job-hint")).to_contain_text("403")
        page.get_by_role("button", name="重新用 AI 生成").click()
        expect(page.locator("[data-stage='1']")).to_be_visible()
        expect(page.locator(".arcade-line").first).to_contain_text(prompt)
        longest = max(words, key=lambda word: word["end"] - word["start"])
        token = page.get_by_role("button", name=longest["text"], exact=True).first
        token.click()
        expect(token).to_have_class(re.compile(r"\bspoken\b"))
        _shot(page, "04-listen.png")
        token.blur()
        page.keyboard.press("Space")
        expect(page.get_by_text("It help me unwind", exact=True)).to_be_visible()
        expect(page.locator("#arcade-repair-answer p")).to_be_hidden()
        _shot(page, "05-repair.png")
        page.keyboard.press("Space")
        expect(page.locator("#arcade-repair-answer p")).to_be_visible()
        page.keyboard.press("Space")
        expect(page.locator(".arcade-reaction")).to_be_visible()
        expect(page.locator(".arcade-reveal")).to_be_hidden()
        _shot(page, "06-recall.png")
        page.keyboard.press("Space")
        expect(page.locator(".arcade-reveal")).to_contain_text("helps me unwind")
        page.wait_for_function("window.arcadeClipCalls.length === 1")
        played = page.evaluate("window.arcadeClipCalls[0]")
        assert played[1] == rows[0]["audio"]["start"]
        assert abs(played[1] + played[2] - rows[0]["audio"]["end"]) < 0.001
        page.get_by_text("发音标", exact=True).click()
        expect(page.locator(".arcade-pronunciation")).to_be_visible()
        _shot(page, "07-prosody.png")
        page.locator("[data-prosody]").blur()
        clips_before_take = page.evaluate("window.arcadeClipCalls.length")
        page.keyboard.down("r")
        expect(page.get_by_role("button", name="结束录音 · 0:01")).to_be_visible()
        page.keyboard.up("r")
        expect(page.get_by_text("识别到 helps me unwind")).to_be_visible()
        page.wait_for_function("count => window.arcadeClipCalls.length >= count + 2",
                               arg=clips_before_take)
        reference, take = page.evaluate(
            "count => window.arcadeClipCalls.slice(count, count + 2)", clips_before_take,
        )
        assert abs(reference[0] + reference[2] - take[0]) < 0.001
        page.keyboard.press("1")
        expect(page.get_by_text(SENTENCES[1]["zh"])).to_be_visible()
        page.keyboard.press("Space")
        page.keyboard.press("2")
        expect(page.get_by_role("button", name="开始脱稿录音")).to_be_visible()
        _shot(page, "08-final.png")
        page.get_by_role("button", name="开始脱稿录音").click()
        page.get_by_role("button", name="结束录音 · 0:01").click()
        expect(page.get_by_role("heading", name="口语前后对比")).to_be_visible()
        expect(page.get_by_text("89 → 118 WPM")).to_be_visible()
        expect(page.get_by_text("3 → 1 次")).to_be_visible()
        expect(page.locator(".arcade-hit.matched")).to_contain_text("helps me unwind")
        _shot(page, "09-results.png")
        with page.expect_download() as download:
            page.get_by_role("button", name="导出三合一 MP3").click()
        assert download.value.suggested_filename == "口语前后对比.mp3"
        page.get_by_role("link", name="返回首页").click()
        expect(page.locator("#arcade-home-card .arcade-recall")).to_be_visible()
        expect(page.locator("#arcade-home-card .arcade-reveal")).to_be_hidden()
        page.keyboard.press("Space")
        page.keyboard.press("1")
        expect(page.get_by_text("本轮刷句完成")).to_be_visible()
        assert [grade["rating"] for grade in grades] == ["good", "again", "good"]
        assert uploads == ["chunk", "final"]
        page.goto(f"{BASE_URL}/#/manage")
        expect(page.locator("#arcade-llm-provider")).to_have_value("deepseek")
        expect(page.get_by_text("已识别个人声纹", exact=False)).to_be_visible()
        expect(page.locator("#role-cards [data-role=a]")).to_have_value("golden_self")
        previews = []

        def preview(route):
            voice = route.request.url.split("/")[-2]
            previews.append(voice)
            route.fulfill(body=audio_data, content_type=media)

        page.route("**/api/voices/kokoro_local/*/sample", preview)
        for control in page.locator(".arcade-voice-gallery [data-preview-vid]").all():
            original = control.inner_text()
            control.click()
            expect(control).to_have_text("停止试听")
            control.click()
            expect(control).to_have_text(original)
        assert len(set(previews)) == 7
        _shot(page, "10-settings.png")
        assert not errors
        browser.close()


def test_no_key_preflight_and_empty_home():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        requests = []
        page.on("request", lambda request: requests.append(request) if
                request.url.endswith("/api/generation-requests") else None)
        settings = {"llm_configured": False, "tts_provider": "stepfun", "stepfun_api_key_set": True}
        page.route("**/api/settings", lambda route: route.fulfill(json=settings))
        page.route("**/api/arcade/blitz?include_pending=true", lambda route: route.fulfill(
            json={"due_count": 0, "cards": []}))
        question = {"id": "q-no-key", "text": QUESTION, "part": 1, "answered": False,
                    "topic_name": "游泳"}
        page.route("**/api/bank/questions?*", lambda route: route.fulfill(json={
            "available": True, "items": [question], "total": 1, "page": 1, "pageCount": 1,
            "topics": [], "sets": [],
        }))
        page.goto(f"{BASE_URL}/#/today")
        expect(page.get_by_role("button", name="随机抽题", exact=True)).to_be_enabled()
        expect(page.get_by_role("link", name="去设置", exact=False)).to_be_visible()
        page.set_viewport_size({"width": 430, "height": 900})
        _shot(page, "11-narrow-empty.png")
        page.set_viewport_size({"width": 1440, "height": 900})
        page.get_by_role("button", name="随机抽题", exact=True).click()
        expect(page.get_by_role("heading", name="题库")).to_be_visible()
        expect(page.get_by_role("link", name="去设置", exact=False)).to_be_visible()
        page.locator("#bank-answer-input").fill("I like swimming.")
        page.locator("[name=bank-gen-mode][value=api]").check()
        page.get_by_role("button", name="一键生成并直接开练").click()
        expect(page.locator("#bank-ai-preflight a")).to_be_focused()
        assert not requests
        browser.close()


def test_radio_generates_plays_and_downloads_both_modes():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 980})
        offered = []
        sample = os.environ.get("RADIO_REAL_AUDIO")
        if sample:
            audio_file = Path(sample)
            audio_data = audio_file.read_bytes()
            episode = json.loads(audio_file.with_suffix(".json").read_text(encoding="utf-8"))
            content_type = "audio/mpeg"
        else:
            audio_data, content_type = _audio(), "audio/wav"
            episode = {"id": "real-fixture", "title": "What do you cook at home?",
                       "duration": 4, "audio_url": "/api/teaching-podcasts/fixture/audio",
                       "voices": {"A": "af_bella", "B": "am_puck"}, "lines": [
                           {"speaker": "A", "text": "What do you cook at home?",
                            "start": 0, "end": 2},
                           {"speaker": "B", "text": "I reach for sesame dressing.",
                            "start": 2, "end": 4},
                       ]}

        def generate(route):
            request = route.request.post_data_json
            offered.append(request)
            route.fulfill(json={**episode, "language_mode": request["language_mode"]})

        page.route("**/api/teaching-podcasts", lambda route: route.fulfill(json={"episodes": []}))
        page.route("**/api/teaching-podcasts/daily", generate)
        page.route("**/api/topics/arcade-test/items/arcade-item/teaching-podcast", generate)
        def serve_audio(route):
            headers = {"Accept-Ranges": "bytes"}
            requested = re.fullmatch(r"bytes=(\d+)-(\d*)", route.request.headers.get("range", ""))
            if requested:
                start = int(requested[1])
                end = min(int(requested[2] or len(audio_data) - 1), len(audio_data) - 1)
                headers["Content-Range"] = f"bytes {start}-{end}/{len(audio_data)}"
                route.fulfill(status=206, body=audio_data[start:end + 1],
                              content_type=content_type, headers=headers)
            else:
                route.fulfill(body=audio_data, content_type=content_type, headers=headers)

        page.route("**/api/teaching-podcasts/*/audio*", serve_audio)

        page.goto(f"{BASE_URL}/#/radio?topic=arcade-test&item=arcade-item&generate=1")
        expect(page.get_by_text("电台已生成。")).to_be_visible()
        turns = page.locator(".radio-transcript button")
        expect(turns.first).to_have_attribute("aria-current", "true")
        expect(page.locator(".radio-player")).to_contain_text("Bella 与 Puck")
        turns.nth(1).click()
        expect(turns.nth(1)).to_have_attribute("aria-current", "true")
        page.locator(".radio-playback select").select_option("1.3")
        playback = page.locator(".radio-playback audio")
        assert playback.evaluate("(audio) => audio.playbackRate") == 1.3
        _shot(page, "12-radio.png")
        with page.expect_download() as result:
            page.get_by_role("button", name="下载 MP3").click()
        assert result.value.suggested_filename == f"教学电台-{episode['id']}.mp3"
        assert result.value.path().read_bytes() == audio_data
        page.locator(".nav-item[href='#/radio']").click()
        daily = page.get_by_role("button", name="生成今日电台")
        expect(daily).to_be_visible()
        page.locator("[name=language_mode]").select_option("bilingual")
        expect(page.locator("[name=partner_voice]")).to_be_disabled()
        daily.click()
        expect(page.locator(".radio-player")).to_contain_text("晓晓与云希")
        assert offered == [
            {"language_mode": "en", "partner_voice": "am_puck"},
            {"language_mode": "bilingual", "partner_voice": "am_puck"},
        ]
        browser.close()
