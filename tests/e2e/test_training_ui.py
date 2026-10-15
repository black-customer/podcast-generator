"""新单题闭环：合成 Android 状态与桌面隔离接口，不改用户语料。"""

import copy
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright

from server import training
from tests.e2e.test_mobile_learning_ui import BASE, phone  # noqa: F401

ROOT = Path(__file__).resolve().parents[2]
MATERIAL = {
    "source_fingerprint": "synthetic",
    "complete_chinese": "我喜欢做饭。做饭让我放松。",
    "sentences": [
        {
            "zh": "我喜欢做饭。",
            "en": "I enjoy cooking.",
            "explanation": "enjoy 后使用动名词。",
            "usage": "描述爱好。",
        },
        {
            "zh": "做饭让我放松。",
            "en": "It helps me relax.",
            "explanation": "help 后使用动词原形。",
            "usage": "说明原因。",
        },
    ],
    "outline": [{"label": "爱好与原因", "indices": [0, 1]}],
    "followup": "Why do some people prefer eating out?",
}


def seed_phone(page, part=1):
    page.goto(BASE + "/#/today")
    page.wait_for_function("typeof MobileRuntime !== 'undefined' && MobileRuntime.state")
    page.evaluate(
        """([m,part])=>{
      const s=window.__mobileState;s.topics.t={id:'t',name:'合成训练',items:{i:{id:'i',
       title:'Do you enjoy cooking?',texts:{question:'Do you enjoy cooking?',
       original_answer:'I like cooking.'},
       meta:{ielts_part:part},audio:{},material:m}}};
      sessionStorage.setItem('synthetic-native-state',JSON.stringify(s));
    }""",
        [MATERIAL, part],
    )
    page.goto(BASE + "/#/train/t/i")
    expect(page.get_by_role("heading", name="Do you enjoy cooking?", exact=True)).to_be_visible()


def begin(page):
    page.get_by_role("button", name="不录音，直接继续", exact=True).click()
    page.get_by_role("button", name="确认文字，查看学习材料").click()
    page.get_by_role("button", name="开始这一轮练习").click()


def finish_sentences(page):
    for _ in range(2):
        page.get_by_role("button", name="独立说出了", exact=True).click()
    page.get_by_role("button", name="隐藏提示，独立回答").click()


def whole(page, result="独立完成", part=1):
    page.locator("#training-no-recording").check()
    if part == 3:
        page.get_by_role("button", name="展示相关追问").click()
        page.locator("#training-followup-done").check()
    for checkbox in page.locator('[name="training-check"]').all():
        checkbox.check()
    page.get_by_role("button", name=result, exact=True).click()


def test_mobile_complete_repair_delayed_and_undo(phone):  # noqa: F811
    page = phone
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    seed_phone(page)
    begin(page)
    page.get_by_role("button", name="默写巩固").click()
    page.locator("#training-dictation").fill("I really like cooking.")
    page.get_by_role("button", name="检查与参考的差异").click()
    expect(page.locator("#training-diff")).to_contain_text("不代表表达错误")
    page.get_by_role("button", name="看参考", exact=True).click()
    expect(page.get_by_role("button", name="独立说出了", exact=True)).to_be_disabled()
    page.get_by_role("button", name="隐藏英文，再说一次").click()
    page.get_by_role("button", name="借助帮助后说出了").click()
    page.get_by_role("button", name="独立说出了", exact=True).click()
    page.get_by_role("button", name="隐藏提示，独立回答").click()
    whole(page)
    expect(page.get_by_role("heading", name="本次完成，待复验")).to_be_visible()
    assert page.evaluate("__mobileState.topics.t.items.i.progress.training.successes") == 0
    page.get_by_role("button", name="撤销上一步").click()
    expect(page.locator("#training-no-recording")).to_be_visible()
    whole(page)
    for day in ("2026-10-04", "2026-10-07"):
        page.evaluate(
            "day=>{window.__mobileNow=day+'T10:00:00+08:00';"
            "sessionStorage.setItem('synthetic-native-clock',window.__mobileNow);}",
            day,
        )
        page.get_by_role("button", name="只看原题，开始复验").click()
        expect(page.locator(".training-reference")).to_have_count(0)
        whole(page)
    expect(page.get_by_role("heading", name="稳定掌握·本人复验", exact=True)).to_be_visible()
    page.get_by_role("button", name="只看原题，开始复验").click()
    page.locator("#training-no-recording").check()
    page.get_by_text("选择需要补练的句子", exact=True).click()
    page.locator('[name="training-weak"][value="1"]').check()
    page.get_by_role("button", name="仍有困难", exact=True).click()
    expect(page.locator(".training-prompt")).to_have_text("做饭让我放松。")
    assert page.evaluate("__mobileState.topics.t.items.i.progress.training.successes") == 0
    assert not errors


def test_part_two_notes_and_part_three_followup(phone):  # noqa: F811
    page = phone
    seed_phone(page, 2)
    begin(page)
    finish_sentences(page)
    page.locator("#training-notes").fill("周末 / 健康 / 放松")
    page.locator("#training-notes").blur()
    page.get_by_role("button", name="开始一分钟准备").click()
    expect(page.locator("#training-prep-time")).to_contain_text("60")
    seed_phone(page, 3)
    begin(page)
    finish_sentences(page)
    whole(page, part=3)
    expect(page.get_by_role("heading", name="本次完成，待复验")).to_be_visible()


def test_desktop_save_failure_retry_and_material_fallback():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(service_workers="block")
        state = training.initial({}, "desktop")
        ctx = {
            "state": state,
            "material": copy.deepcopy(MATERIAL),
            "part": 1,
            "material_status": "ready",
            "item": {"question": "Do you enjoy cooking?", "original_answer": "I like cooking."},
            "recordings": [],
            "history": [],
        }
        failed = []

        def handler(route):
            path = urlparse(route.request.url).path
            if path.endswith("/actions"):
                payload = route.request.post_data_json
                if not failed:
                    failed.append(payload["action_id"])
                    route.fulfill(status=503, json={"detail": "synthetic save failed"})
                    return
                if payload["action"] == "start":
                    assert payload["action_id"] == failed[0]
                ctx["state"] = training.reduce(
                    ctx["state"], payload, MATERIAL, "2026-10-15T10:00:00", 1
                )
            route.fulfill(json=ctx)

        page.route("**/api/topics/t/items/i/study/training**", handler)
        page.goto(BASE + "/#/train/t/i")
        page.get_by_role("button", name="不录音，直接继续").click()
        expect(page.locator("#training-status")).to_contain_text("synthetic save failed")
        expect(page.get_by_role("button", name="不录音，直接继续")).to_be_visible()
        page.get_by_role("button", name="不录音，直接继续").click()
        page.get_by_role("button", name="确认文字，查看学习材料").click()
        page.get_by_role("button", name="开始这一轮练习").click()
        output = Path(os.environ.get("TRAINING_SCREENSHOTS", "test-results/training"))
        output.mkdir(parents=True, exist_ok=True)
        for width in (1536, 1280, 1024):
            page.set_viewport_size({"width": width, "height": 1000})
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            page.screenshot(path=str(output / f"desktop-{width}.png"), full_page=True)
        finish_sentences(page)
        whole(page)
        expect(page.get_by_role("heading", name="本次完成，待复验")).to_be_visible()
        browser.close()


def test_recording_failure_survives_reload_and_retries_same_upload():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
        )
        page = browser.new_page(permissions=["microphone"], service_workers="block")
        state = training.initial({}, "recording")
        for n, action in enumerate(("start", "inputs", "understand", "outline_done")):
            state = training.reduce(
                state,
                {
                    "version": 2,
                    "fingerprint": "recording",
                    "action_id": str(n),
                    "action": action,
                    "focus": [],
                },
                MATERIAL,
                "2026-10-15T10:00:00",
                1,
            )
        ctx = {
            "state": state,
            "material": MATERIAL,
            "part": 1,
            "material_status": "ready",
            "item": {"question": "Do you enjoy cooking?"},
            "recordings": [],
        }
        uploads = []

        def handler(route):
            if route.request.url.split("?")[0].endswith("/recordings"):
                uploads.append(route.request.url)
                if len(uploads) == 1:
                    route.fulfill(status=503, json={"detail": "synthetic offline"})
                    return
                ctx["recordings"] = [{"id": "saved", "stage": "recall", "created_at": "now"}]
                route.fulfill(json={"id": "saved"})
                return
            if route.request.url.endswith("/actions"):
                ctx["state"] = training.reduce(
                    ctx["state"], route.request.post_data_json, MATERIAL, "2026-10-15T10:00:00", 1
                )
            route.fulfill(json=ctx)

        page.route("**/api/topics/t/items/i/study/**", handler)
        page.goto(BASE + "/#/train/t/i")
        page.get_by_role("button", name="开始录音", exact=True).click()
        page.wait_for_timeout(250)
        page.get_by_role("button", name="停止并保存", exact=True).click()
        expect(page.locator("#training-status")).to_contain_text("synthetic offline")
        page.reload()
        page.get_by_role("button", name="恢复并保存录音", exact=True).click()
        expect(page.locator("#training-status")).to_contain_text("录音已保存")
        assert uploads[0] == uploads[1]
        for checkbox in page.locator('[name="training-check"]').all():
            checkbox.check()
        page.get_by_role("button", name="独立完成", exact=True).click()
        expect(page.get_by_role("heading", name="本次完成，待复验")).to_be_visible()
        assert ctx["state"]["attempts"][-1]["recording_id"] == "saved"
        browser.close()


def test_training_layout_screenshots(phone):  # noqa: F811
    page = phone
    seed_phone(page)
    begin(page)
    output = Path(os.environ.get("TRAINING_SCREENSHOTS", "test-results/training"))
    output.mkdir(parents=True, exist_ok=True)
    for width in (390, 430):
        page.set_viewport_size({"width": width, "height": 900})
        for theme in ("light", "dark"):
            page.evaluate(
                "theme=>{document.body.dataset.mobileTheme=theme;MobileAppearance.refresh();}",
                theme,
            )
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            page.screenshot(path=str(output / f"phone-{width}-{theme}.png"), full_page=True)
    page.evaluate("document.documentElement.style.fontSize='22px'")
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    page.screenshot(path=str(output / "phone-large-text.png"), full_page=True)
    page.goto(BASE + "/#/today")
    expect(page.get_by_role("heading", name="继续训练", exact=True)).to_be_visible()
    page.screenshot(path=str(output / "phone-home.png"), full_page=True)
