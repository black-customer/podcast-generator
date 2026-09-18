"""Playwright 无头浏览器 E2E 自动化测试预言机 (tests/e2e/test_player_ui.py)"""
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8765"

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

        # 1. 访问首页
        page.goto(BASE_URL)
        page.wait_for_selector(".hero-title", timeout=5000)
        assert "高保真母语口语媒体库" in page.content()

        # 2. 点击进入专辑详情
        album_card = page.wait_for_selector(".album-card", timeout=5000)
        assert album_card is not None
        album_card.click()
        page.wait_for_selector(".track-row", timeout=5000)
        assert "专辑 · 英语口语语料库" in page.content()

        # 3. 点击曲目进入沉浸式播放器与剧本页
        first_track = page.locator(".track-row").first
        first_track.click()
        page.wait_for_selector("#lyrics-panel", timeout=5000)
        assert page.is_visible("#vinyl-disk")
        assert page.is_visible("#pod-stream")
        assert page.is_visible("#btn-tab-pod")
        assert page.is_visible("#btn-tab-mono")

        # 4. 验证底部全局播放器与控制器
        assert page.is_visible("#global-player")
        assert page.is_visible("#gp-play")
        assert page.is_visible("#gp-rewind")
        assert page.is_visible("#gp-forward")
        assert page.is_visible("#gp-speed")

        # 5. 测试播客点击跳播与时间轴渲染
        page.wait_for_selector("#pod-stream .dialogue-bubble", timeout=5000)
        pod_bubbles = page.locator("#pod-stream .dialogue-bubble")
        assert pod_bubbles.count() >= 5
        # 点击第 3 句进行跳播测试
        third_bubble = pod_bubbles.nth(2)
        third_bubble.click()
        page.wait_for_timeout(300)
        cur_time = page.evaluate("() => document.getElementById('core-audio').currentTime")
        assert cur_time > 0, "Expected audio.currentTime to advance on click-to-seek"

        # 6. 测试独白版切换、歌词渲染与精准跳播
        mono_tab_btn = page.locator("#btn-tab-mono")
        mono_tab_btn.click()
        page.wait_for_selector("#mono-stream .monologue-line", timeout=5000)
        assert page.is_visible("#mono-stream")
        assert not page.is_visible("#pod-stream")
        mono_lines = page.locator("#mono-stream .monologue-line")
        assert mono_lines.count() >= 10, f"Expected >= 10 monologue lines, got {mono_lines.count()}"

        # 点击独白第 4 句进行跳播
        fourth_mono = mono_lines.nth(3)
        fourth_mono.click()
        page.wait_for_timeout(300)
        mono_time = page.evaluate("() => document.getElementById('core-audio').currentTime")
        assert mono_time > 0, "Expected audio.currentTime to advance on monologue click-to-seek"

        # 7. 切回播客版
        pod_tab_btn = page.locator("#btn-tab-pod")
        pod_tab_btn.click()
        page.wait_for_timeout(300)
        assert page.is_visible("#pod-stream")
        assert not page.is_visible("#mono-stream")

        # 8. 测试倍速切换
        speed_btn = page.locator("#gp-speed")
        assert speed_btn.inner_text() == "1.0x"
        speed_btn.click()
        assert speed_btn.inner_text() == "1.2x"
        speed_btn.click()
        assert speed_btn.inner_text() == "1.5x"

        # 9. 测试声学音色展台视图
        page.goto(f"{BASE_URL}/#/voices")
        page.wait_for_selector(".voice-card", timeout=5000)
        voice_cards = page.locator(".voice-card")
        assert voice_cards.count() >= 4
        assert "Peter Parker" in page.content()

        # 10. 断言全程无 JS 运行时异常
        assert len(console_errors) == 0, f"Captured console errors: {console_errors}"
        browser.close()

if __name__ == "__main__":
    test_full_player_workflow()
    print("Playwright E2E Test Passed Successfully!")
