"""桌面录音、复习切源、素材表单和后台任务的连续性回归。"""

import base64
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8765")
ITEM = "/api/topics/continuity-fixture/items/sample-answer"
QUESTION = {"id": "continuity-fixture", "text": "How do you get to work?",
            "part": 1, "answered": False, "topic_name": "交通"}
SNIPPET = "I keep my options open."
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWl8AAAAASUVORK5CYII="
)


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
        )
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.route("**/api/bank/questions?*", lambda route: route.fulfill(json={
            "available": True, "items": [QUESTION], "total": 1, "page": 1,
            "pageCount": 1, "sets": [], "topics": [],
        }))
        page.route("**/api/settings", lambda route: route.fulfill(json={"llm_configured": True}))
        page.route("**/api/arcade/error-board", lambda route: route.fulfill(json={
            "top": [], "today_chunks": [], "prompt": "",
        }))
        yield page
        browser.close()


def test_blind_recording_can_be_replaced_after_successful_retry(page):
    attempts = []

    def transcribe(route):
        attempts.append(route.request.post_data_buffer)
        if len(attempts) == 1:
            route.fulfill(status=503, json={"detail": "本机转写暂不可用"})
        else:
            route.fulfill(json={"blind_token": "test-token", "transcript": "I caught the bus."})

    page.route("**/api/arcade/transcribe-blind?*", transcribe)
    page.goto(f"{BASE_URL}/#/bank?sel={QUESTION['id']}")
    control = page.locator("#arcade-blind")
    control.click()
    expect(control).to_contain_text("0:01")
    control.click()
    expect(control).to_have_text("重试转写")
    control.click()
    expect(control).to_have_text("重录英文盲答")
    expect(page.locator("#bank-answer-input")).to_have_value("I caught the bus.")
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    control.click()
    expect(control).to_contain_text("结束并转写", timeout=2000)
    assert len(attempts) == 2


def _card(identity, prompt, source):
    return {"id": identity, "scaffolding_level": 1, "card_kind": "capture",
            "source_type": source, "trigger_context": prompt, "en": SNIPPET,
            "zh": "保留选择", "key_chunk": "keep my options open", "source_fingerprint": "fixture",
            "audio_url": "", "audio": {"scope": "sentence", "start": 0, "end": None}}


def _queue(route, *cards):
    route.fulfill(json={"cards": cards, "due_count": len(cards), "inbox_count": 0})


def test_switching_review_source_blocks_old_card_grades_and_stale_reads(page):
    old = _card("old", "旧来源第一张", "scene")
    first = _card("first", "新来源第一张", "snippet")
    second = _card("second", "新来源第二张", "snippet")
    filters, grades = {}, []

    def load(route):
        source = route.request.url.partition("&source=")[2]
        if source:
            filters[source] = route
        else:
            _queue(route, old)

    def grade(route):
        grades.append(route.request.url.rsplit("/", 2)[-2])
        route.fulfill(json={})

    page.route("**/api/arcade/blitz?*", load)
    page.route("**/api/cards/*/grade", grade)
    page.goto(f"{BASE_URL}/#/today")
    expect(page.get_by_text(old["trigger_context"])).to_be_visible()
    page.keyboard.press("Space")
    with page.expect_request("**/api/arcade/blitz?*source=scene"):
        page.get_by_role("button", name="看剧表达", exact=True).click()
    page.keyboard.press("Digit1")
    with page.expect_request("**/api/arcade/blitz?*source=snippet"):
        page.get_by_role("button", name="随手摘录", exact=True).click()
    _queue(filters["snippet"], first, second)
    expect(page.get_by_text(first["trigger_context"])).to_be_visible()
    with page.expect_response("**/api/arcade/blitz?*source=scene"):
        filters["scene"].fulfill(status=503, json={"detail": "旧请求失败"})
    expect(page.get_by_text("第 1 / 2 张")).to_be_visible()
    expect(page.locator("#arcade-status")).to_be_empty()
    assert grades == []
    page.get_by_role("button", name="揭晓或重播").click()
    with page.expect_response("**/api/cards/first/grade"):
        page.get_by_role("button", name="1 顺畅").click()
    expect(page.get_by_text(second["trigger_context"])).to_be_visible()
    assert grades == ["first"]
    with page.expect_request("**/api/arcade/blitz?*source=ielts"):
        page.get_by_role("button", name="雅思口语", exact=True).click()
    filters["ielts"].fulfill(status=503, json={"detail": "新来源读取失败"})
    expect(page.locator("#arcade-status")).to_have_text("新来源读取失败")
    expect(page.get_by_text("第 2 / 2 张")).to_be_visible()


def test_snippet_fields_and_image_survive_refresh_switch_and_save_failure(page):
    delayed, writes = {}, []

    def load_captures(route):
        if not delayed:
            delayed["route"] = route
        else:
            route.fulfill(json={"captures": []})

    def save(route):
        writes.append(route.request.post_data_json)
        if len(writes) == 1:
            route.fulfill(status=503, json={"detail": "素材保存暂不可用"})
        else:
            route.fulfill(json={"id": "synthetic"})

    page.route("**/api/captures", load_captures)
    page.route("**/api/cards", lambda route: route.fulfill(json={"cards": []}))
    page.route("**/api/captures/snippet", save)
    with page.expect_request("**/api/captures"):
        page.goto(f"{BASE_URL}/#/captures")
    import_tab = page.locator("[data-capture-tab=import]")
    import_tab.click()
    snippet = page.get_by_label("英文摘录")
    page.get_by_label("标题（可选）").fill("出行")
    page.get_by_label("来源链接（可选）").fill("https://example.com/clip")
    page.get_by_label("备注（可选）").fill("路上听到")
    page.get_by_label("截图（可选）").set_input_files({
        "name": "sample.png", "mimeType": "image/png", "buffer": PNG,
    })
    preview = page.get_by_role("img", name="待保存截图 1")
    expect(preview).to_be_visible()
    snippet.fill(SNIPPET)
    delayed["route"].fulfill(json={"captures": [{"extract_state": "pending"}]})
    expect(page.locator("[data-distill]")).to_be_enabled()
    expect(snippet).to_be_focused()
    expect(snippet).to_have_value(SNIPPET)
    page.locator("[data-capture-tab=inbox]").click()
    import_tab.click()
    expect(snippet).to_have_value(SNIPPET)
    expect(page.get_by_label("标题（可选）")).to_have_value("出行")
    expect(preview).to_be_visible()
    submit = page.get_by_role("button", name="保存素材")
    submit.click()
    expect(page.locator("#capture-status")).to_have_text("素材保存暂不可用")
    expect(snippet).to_have_value(SNIPPET)
    expect(preview).to_be_visible()
    submit.click()
    expect(page.locator("#capture-status")).to_contain_text("素材已保存")
    assert writes[0] == writes[1]
    assert writes[1]["source_url"] == "https://example.com/clip"
    assert writes[1]["note"] == "路上听到"
    assert len(writes[1]["images"]) == 1
    import_tab.click()
    expect(snippet).to_be_empty()
    expect(preview).to_have_count(0)


def test_material_poll_retries_and_reconnects_without_restarting_job(page):
    reads, starts = [], []
    ready = {"status": "ready", "question": QUESTION["text"], "sentences": [],
             "alignment": {"lines": [], "words": []}, "audio_url": ""}

    def load(route):
        reads.append(route.request.url)
        if len(reads) in {2, 4, 5, 6}:
            route.fulfill(status=503, json={"detail": "逐句材料读取暂不可用"})
        elif len(reads) < 7:
            route.fulfill(json={**ready, "status": "preparing", "reason": "逐句材料正在准备"})
        else:
            route.fulfill(json=ready)

    page.route(f"**{ITEM}/arcade", load)
    page.route("**/study/prepare", lambda route: (
        starts.append(route.request.url), route.fulfill(json={"status": "preparing"}),
    ))
    page.goto(f"{BASE_URL}/#/train/continuity-fixture/sample-answer")
    retry = page.get_by_role("button", name="重新读取进度")
    expect(retry).to_be_visible(timeout=10000)
    assert len(reads) == 6
    retry.click()
    expect(page.get_by_role("heading", name="完整地道示范")).to_be_visible()
    assert len(reads) == 7 and starts == []


def test_radio_restores_running_job_on_return_and_cancels_it(page):
    starts, cancels = [], []
    job = {"id": "continuity-radio", "state": "running", "phase": "tts", "total": 4, "done": 2,
           "radio_scope": ["daily", "bilingual", "golden_self", None, None, None]}
    unrelated = {**job, "id": "other-radio",
                 "radio_scope": ["item", "en", "am_puck", "other-topic", "other-item", None]}

    def start(route):
        starts.append(route.request.post_data_json)
        route.fulfill(json={"job_id": job["id"]})

    def cancel(route):
        cancels.append(route.request.url)
        job["state"] = "cancelled"
        route.fulfill(json={"cancelled": True})

    page.route("**/api/teaching-podcasts", lambda route: route.fulfill(json={"episodes": []}))
    page.route("**/api/teaching-podcasts/daily", start)
    page.route("**/api/jobs", lambda route: route.fulfill(json=[unrelated, job] if starts else []))
    page.route(f"**/api/jobs/{job['id']}", lambda route: route.fulfill(json=job))
    page.route(f"**/api/jobs/{job['id']}/cancel", cancel)
    page.goto(f"{BASE_URL}/#/radio")
    submit = page.get_by_role("button", name="生成今日电台")
    expect(submit).to_be_enabled()
    page.get_by_label("语言").select_option("bilingual")
    page.get_by_label("男搭档").select_option("golden_self")
    submit.click()
    progress = page.get_by_role("progressbar")
    expect(progress).to_have_attribute("aria-valuenow", "50")
    page.locator(".nav-item[href='#/practice']").click()
    expect(page.get_by_role("heading", name="题库")).to_be_visible()
    page.locator(".nav-item[href='#/radio']").click()
    expect(progress).to_have_attribute("aria-valuenow", "50")
    expect(page.get_by_label("语言")).to_have_value("bilingual")
    expect(page.get_by_label("男搭档")).to_have_value("golden_self")
    page.get_by_role("button", name="取消生成").click()
    expect(page.locator("#radio-status")).to_have_text("已取消生成。")
    expect(submit).to_be_enabled()
    assert starts == [{"language_mode": "bilingual", "partner_voice": "golden_self"}]
    assert len(cancels) == 1


@pytest.mark.parametrize("width", [390, 860, 1440])
def test_question_bank_has_direct_return_to_today_on_online_web(page, width):
    page.route("**/api/arcade/blitz?*", lambda route: _queue(
        route, _card("nav", "练习示例", "scene"),
    ))
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(f"{BASE_URL}/#/practice")
    expect(page.get_by_role("heading", name="题库")).to_be_visible()
    today = page.get_by_role("link", name="今日练习", exact=True)
    expect(today).to_be_visible()
    assert page.locator("html").evaluate("(element) => element.scrollWidth <= innerWidth")
    shots = os.environ.get("CONTINUITY_SCREENSHOT_DIR")
    if shots:
        target = Path(shots)
        target.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=target / f"bank-{width}.png", animations="disabled")
    today.click()
    expect(page.get_by_role("heading", name="今日练习")).to_be_visible()
    expect(today).to_have_attribute("aria-current", "page")


def test_global_shortcuts_leave_question_bank_keys_alone(page):
    page.goto(f"{BASE_URL}/#/practice")
    expect(page.get_by_role("heading", name="题库")).to_be_visible()
    events = page.evaluate("""() => [
      {code: 'ArrowRight'}, {code: 'Space'}, {code: 'KeyR', repeat: true},
      {code: 'KeyA', ctrlKey: true}, {code: 'ArrowLeft', altKey: true},
    ].map(options => document.body.dispatchEvent(
      new KeyboardEvent('keydown', {bubbles: true, cancelable: true, ...options})
    ))""")
    assert events == [True] * 5
    expect(page.locator("#toast-root")).to_be_empty()


def test_intent_button_returns_to_recording_after_transcription(page):
    page.route("**/api/arcade/transcribe-intent?*", lambda route: route.fulfill(
        json={"transcript": "上班坐公交。"},
    ))
    page.goto(f"{BASE_URL}/#/bank?sel={QUESTION['id']}")
    expect(page.locator("#bank-answer-input")).to_be_enabled()
    control = page.locator("#arcade-intent")
    control.click()
    expect(control).to_contain_text("0:01")
    control.click()
    expect(page.locator("#arcade-intent-input")).to_have_value("上班坐公交。")
    expect(control).to_have_text("录制中文意图")
    expect(page.locator("#bank-answer-submit")).to_be_enabled()


def test_failed_bank_filter_leaves_previous_results_interactive(page):
    pending = []
    page.route("**/api/bank/questions?part=2&*", lambda route: pending.append(route))
    page.goto(f"{BASE_URL}/#/practice")
    first = page.locator(".bank-row").first
    expect(first).to_be_visible()
    with page.expect_request("**/api/bank/questions?part=2&*"):
        page.get_by_role("button", name="Part 2 · 独白描述").click()
    loading = page.get_by_role("status", name="", exact=True).filter(has_text="正在读取筛选结果")
    expect(loading).to_be_visible()
    assert loading.bounding_box()["y"] < first.bounding_box()["y"]
    pending[0].fulfill(status=503, json={"detail": "题库暂时不可用"})
    expect(page.get_by_role("heading", name="筛选读取失败")).to_be_visible()
    expect(page.locator(".bank-results")).not_to_have_attribute("aria-busy", "true")
    expect(page.locator(".bank-results")).not_to_have_attribute("inert", "")
    expect(first).to_be_visible()


def test_player_routes_use_item_path_without_track_query(page):
    item = {"id": "sample", "title": QUESTION["text"], "question": QUESTION["text"],
            "status": "generated", "has_audio_podcast": True}
    following = {**item, "id": "next", "title": "A second question",
                 "question": "A second question"}
    page.route("**/api/topics/continuity-fixture", lambda route: route.fulfill(json={
        "id": "continuity-fixture", "name": "交通", "items": [item, following],
    }))
    page.route("**/api/topics/continuity-fixture/items/*", lambda route: route.fulfill(
        status=404, json={"detail": "unexpected player path"},
    ))
    page.route("**/api/topics/continuity-fixture/items/sample",
               lambda route: route.fulfill(json=item))
    page.route("**/api/topics/continuity-fixture/items/next",
               lambda route: route.fulfill(json=following))
    page.goto(f"{BASE_URL}/#/play/continuity-fixture/sample?track=podcast")
    expect(page.locator(".player-question")).to_have_text(QUESTION["text"])
    expect(page.locator("#gp-title")).to_have_text(QUESTION["text"])
    page.evaluate("() => { PlayerState.loopA = 1; PlayerState.loopB = 2; }")
    page.get_by_role("button", name="下一首").click()
    expect(page.locator(".player-question")).to_have_text(following["question"])
    expect(page.locator("#gp-title")).to_have_text(following["title"])
    assert page.evaluate("[PlayerState.loopA, PlayerState.loopB]") == [None, None]


def test_service_worker_prefers_fresh_code_and_falls_back_offline(page):
    page.goto(f"{BASE_URL}/#/practice")
    result = page.evaluate("""async () => {
      const script = await fetch('/sw.js').then(response => response.text());
      const cached = {value: 'cached'};
      const state = {offline: false, cacheMode: null};
      let fire;
      const worker = {location, addEventListener(name, handler) {
        if (name === 'fetch') fire = handler;
      }};
      const cache = {match: async () => cached, open: async () => ({put: async () => {}})};
      const network = async (_, options) => {
        state.cacheMode = options?.cache;
        if (state.offline) throw new Error('offline');
        return {ok: true, type: 'basic', value: 'fresh', clone: () => ({})};
      };
      new Function('self', 'caches', 'fetch', script)(worker, cache, network);
      const read = async path => {
        let response;
        fire({request: {url: new URL(path, location).href, method: 'GET'},
              waitUntil() {}, respondWith(value) { response = value; }});
        return (await response)?.value || null;
      };
      const fresh = await Promise.all(
        ['/', '/static/style.css', '/static/app.js'].map(read)
      );
      state.offline = true;
      return {fresh, cacheMode: state.cacheMode, offline: await read('/static/app.js'),
              api: await read('/api/settings')};
    }""")
    assert result == {"fresh": ["fresh", "fresh", "fresh"], "cacheMode": "no-cache",
                      "offline": "cached", "api": None}
