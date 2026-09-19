"""雅思题库视图的 Playwright E2E（B01）：浏览→筛选→搜索→作答闭环。

运行：服务已启动后 .venv/Scripts/python -m pytest tests/e2e/test_bank_ui.py -q
依赖题库快照 data/question_bank.json（python -m server.bank --sync）；缺失时跳过。
"""
import re
import time

import pytest
import requests
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8765"


def _bank_ready() -> bool:
    try:
        return requests.get(f"{BASE_URL}/api/bank/questions", timeout=10).json().get("available")
    except Exception:
        return False


def test_bank_view_flow():
    if not _bank_ready():
        pytest.skip("题库快照未导入（python -m server.bank --sync）")
    stamp = int(time.time())
    created_topics: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        console_errors = []
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        def _on_console(msg):
            # 资源 404 属预期：刚提交的作答还没有音频，话题页 audio 元素必然 404
            if msg.type == "error" and "Failed to load resource" not in msg.text:
                console_errors.append(msg.text)

        page.on("console", _on_console)
        try:
            # 1. 打开题库默认视图：Part1 列表渲染
            page.goto(f"{BASE_URL}/#/bank")
            page.wait_for_selector(".bank-row", timeout=5000)
            assert page.locator(".bank-tab.active").inner_text().startswith("Part 1")
            assert page.locator(".bank-row").count() > 0

            # 2. Part 标签切换：URL 参数驱动，Part2 行带 Part 徽标
            page.click(".bank-tabs button:nth-child(2)")
            page.wait_for_timeout(400)
            assert "part=2" in page.url
            if page.locator(".bank-row").count() > 0:
                assert page.locator(".bank-part-tag").count() > 0

            # 3. 搜索：回到 Part 1 搜英文题干子串（Part2 搜 hometown 为空属正常）
            page.click(".bank-tabs button:nth-child(1)")
            page.wait_for_timeout(400)
            page.fill("#bank-q", "hometown")
            page.press("#bank-q", "Enter")
            page.wait_for_timeout(400)
            rows = page.locator(".bank-row")
            assert rows.count() > 0, "Part1 搜 hometown 必有结果"
            assert "hometown" in rows.first.inner_text().lower()

            # 4. 选中题目 → 作答卡出现（cue card 全文 + 输入框）
            page.click(".bank-row >> nth=0")
            page.wait_for_selector(".bank-answer-card", timeout=5000)
            assert page.locator("#bank-answer-input").is_visible()

            # 5. 提交中文作答 → 跳转到话题页（真实入库，finally 清理）
            page.fill("#bank-answer-input", f"e2e 题库作答冒烟 {stamp}")
            page.click("#bank-answer-submit")
            page.wait_for_url(re.compile(r"#/topic/"), timeout=5000)
            topic_id = page.url.split("#/topic/")[1]
            created_topics.append(topic_id)
            page.wait_for_selector(".track-row", timeout=5000)
            assert page.locator(".track-row").count() >= 1, "作答应出现在话题条目列表"
        finally:
            for tid in created_topics:
                try:
                    requests.delete(f"{BASE_URL}/api/topics/{tid}", timeout=10)
                except Exception:
                    pass
            browser.close()
        assert not console_errors, f"页面报错：{console_errors}"
