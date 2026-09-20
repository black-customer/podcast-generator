"""Playwright 无头浏览器 E2E：播放器精准交互（M06）+ 全视图冒烟。

运行：服务已启动后 .venv/Scripts/python -m pytest tests/e2e/test_player_ui.py -q
依赖真实库中已有条目（02-sleep-healthy-eating / 001-...，Bruce 主语料）。
"""
import os

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8765")
TOPIC = "02-sleep-healthy-eating"
ITEM = "001-sleep-and-healthy-eating-dialogue"


def test_full_player_workflow():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        console_errors = []
        page.on("pageerror", lambda err: console_errors.append(str(err)))
        def _on_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text)
        page.on("console", _on_console)

        # 1. 首页
        page.goto(f"{BASE_URL}/#/topics")
        page.wait_for_selector(".album-card", timeout=5000)

        # 2. 直接进入目标条目的沉浸播放页
        page.goto(f"{BASE_URL}/#/play/{TOPIC}/{ITEM}")
        page.wait_for_selector("#lyrics-panel", timeout=5000)
        assert page.is_visible(".player-question")
        assert page.is_visible(".reference-rail")
        assert page.is_visible("#pod-stream")
        assert page.is_visible("#btn-tab-pod")
        assert page.is_visible("#remake-item")

        # 3. 全局播放器与新控制按钮
        assert page.is_visible("#global-player")
        assert page.is_visible("#gp-loop-a")
        assert page.is_visible("#gp-loop-b")
        assert page.is_visible("#gp-replay-line")
        assert page.is_visible("#gp-volume")
        assert page.is_visible("#gp-zh-toggle")

        # 4. 时间轴渲染 + 对齐模式标志（诚实显示 measured/estimated）
        page.wait_for_selector("#pod-stream .transcript-row", timeout=5000)
        rows = page.locator("#pod-stream .transcript-row")
        assert rows.count() >= 5
        assert page.locator("#tl-mode-chip").inner_text() != ""

        # 5. 点击第 3 句跳播
        rows.nth(2).click()
        page.wait_for_timeout(400)
        cur = page.evaluate("() => document.getElementById('core-audio').currentTime")
        assert cur > 0, "点击句子后 currentTime 应变化"

        # 6. A-B 循环：设 A → 前进 → 设 B → 越过 B 应回跳
        page.evaluate("() => { document.getElementById('core-audio').currentTime = 5.0; }")
        page.wait_for_timeout(200)
        page.locator("#gp-loop-a").click()
        page.evaluate("() => { document.getElementById('core-audio').currentTime = 7.0; }")
        page.wait_for_timeout(200)
        page.locator("#gp-loop-b").click()
        loop_ab = page.evaluate(
            "() => JSON.stringify({a: PlayerState.loopA, b: PlayerState.loopB})"
        )
        import json
        ab = json.loads(loop_ab)
        assert ab["a"] is not None and ab["b"] is not None and ab["b"] > ab["a"]
        b_point = str(ab["b"])
        jump_expr = (
            "() => { document.getElementById('core-audio').currentTime = " + b_point + " - 0.2; }"
        )
        page.evaluate(jump_expr)
        page.wait_for_timeout(800)
        cur2 = page.evaluate("() => document.getElementById('core-audio').currentTime")
        assert cur2 < ab["b"], f"越过 B 点应回跳，实际 {cur2:.2f} >= B={ab['b']:.2f}"
        page.locator("#gp-loop-clear").click()

        # 7. 句间导航（seekLine：下一句 / 上一句）
        page.evaluate("() => seekLine(1)")
        page.wait_for_timeout(300)
        t_next = page.evaluate("() => document.getElementById('core-audio').currentTime")
        page.evaluate("() => seekLine(-1)")
        page.wait_for_timeout(300)
        t_prev = page.evaluate("() => document.getElementById('core-audio').currentTime")
        assert t_next != t_prev

        # 8. 键盘快捷键：空格暂停/播放
        space_pause = page.evaluate(
            "() => { const a = document.getElementById('core-audio');"
            " const wasPaused = a.paused; a.focus();"
            " document.dispatchEvent(new KeyboardEvent('keydown', {code: 'Space', bubbles: true}));"
            " return {wasPaused, nowPaused: a.paused}; }"
        )
        assert space_pause["wasPaused"] != space_pause["nowPaused"], "空格应切换播放/暂停"

        # 9. 对话条目没有独白音轨 → 独白切换按钮应禁用（避免 404）
        assert page.locator("#btn-tab-mono").is_disabled(), "对话条目的独白按钮应禁用"

        # 10. 音色展台视图（去演示文案后仍可用）
        page.goto(f"{BASE_URL}/#/voices")
        page.wait_for_selector(".voice-card", timeout=5000)
        assert page.locator(".voice-card").count() >= 1

        # 11. 全程无 JS 运行时异常
        assert len(console_errors) == 0, f"Captured console errors: {console_errors}"
        browser.close()


if __name__ == "__main__":
    test_full_player_workflow()
    print("Playwright E2E Test Passed Successfully!")
