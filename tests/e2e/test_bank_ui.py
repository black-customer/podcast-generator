"""雅思题库视图的 Playwright E2E（B01）：浏览→筛选→搜索→作答闭环。

运行：服务已启动后 .venv/Scripts/python -m pytest tests/e2e/test_bank_ui.py -q
依赖题库快照 data/question_bank.json（python -m server.bank --sync）；缺失时跳过。
"""
import os
import re
import time

import pytest
import requests
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8765")


def _bank_ready() -> bool:
    try:
        return requests.get(f"{BASE_URL}/api/bank/questions", timeout=10).json().get("available")
    except Exception:
        return False


def test_bank_view_flow():
    if not _bank_ready():
        pytest.skip("题库快照未导入（python -m server.bank --sync）")
    stamp = int(time.time())
    before_topics = {t["id"] for t in requests.get(f"{BASE_URL}/api/topics", timeout=10).json()}
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

            # 2.5 考季筛选：5-8月下拉 → 行标签只剩 5–8月；必考项有"必考"徽标
            page.click(".bank-tabs button:nth-child(1)")
            page.wait_for_timeout(300)
            page.select_option(".bank-toolbar select >> nth=1", "qs_2026_05_08")
            page.wait_for_timeout(400)
            assert "set=qs_2026_05_08" in page.url
            rows = page.locator(".bank-row")
            assert rows.count() > 0, "Part1 5-8月必有结果"
            tags = page.locator(".bank-row").first.locator(".bank-topic-tag").all_inner_texts()
            assert any("5–8月" in t for t in tags), f"行标签缺考季: {tags}"
            page.select_option(".bank-toolbar select >> nth=1", "core")
            page.wait_for_timeout(400)
            # Part1 必考只有 1 题（如为 0 也不算失败——数据决定），只验证不报错
            page.select_option(".bank-toolbar select >> nth=1", "")
            page.wait_for_timeout(300)

            # 3. 搜索：回到 Part 1 搜英文题干子串（Part2 搜 hometown 为空属正常）
            page.click(".bank-tabs button:nth-child(1)")
            page.wait_for_timeout(400)
            page.fill("#bank-q", "hometown")
            page.press("#bank-q", "Enter")
            page.wait_for_timeout(400)
            rows = page.locator(".bank-row")
            assert rows.count() > 0, "Part1 搜 hometown 必有结果"
            assert "hometown" in rows.first.inner_text().lower()

            # 4. 清空搜索 → 选中已作答且有音频的题 → 作答卡出现「去听已有的音频」跳转按钮
            # （点击行后 hashchange 异步派发 + fetch 渲染，须等 DOM 稳定再操作）
            page.fill("#bank-q", "")
            page.press("#bank-q", "Enter")
            page.wait_for_timeout(500)
            page.locator(".bank-row", has_text="已有音频").first.click()
            page.wait_for_timeout(700)
            page.wait_for_selector(".bank-answer-card", timeout=5000)
            assert page.locator("text=去听已有的音频").count() == 1

            # 4.5 选中未作答题 → 输入框可见可作答
            # （不精确断言跳转按钮数：同题干可能跨册重复，另一册版本或已作答）
            un = requests.get(
                f"{BASE_URL}/api/bank/questions?part=1&page_size=100", timeout=10
            ).json()
            target = next((it for it in un["items"] if not it["answered"]), None)
            assert target, "Part1 应存在未作答题目"
            page.locator(".bank-row", has_text=target["text"][:40]).first.click()
            page.wait_for_timeout(700)
            page.wait_for_selector("#bank-answer-input", timeout=5000)

            # 5. 提交中文作答（Agent 模式默认）→ 出现 Agent 指令与等待态（真实入库，finally 清理）
            page.fill("#bank-answer-input", f"e2e 题库作答冒烟 {stamp}")
            page.click("#bank-answer-submit")
            page.wait_for_selector("#agent-prompt-box", timeout=5000)
            prompt_text = page.locator("#agent-prompt-box").inner_text()
            assert "pipeline.py complete" in prompt_text
            m_topic = re.search(r"--topic-id (\S+)", prompt_text)
            m_item = re.search(r"--item-id (\S+)", prompt_text)
            assert m_topic and m_item, prompt_text
            created_topics.append(m_topic.group(1))
            assert "api_key" not in prompt_text.lower(), "Agent 指令不得包含密钥字段"
            assert page.locator("#agent-copy-btn").count() == 1
        finally:
            try:
                after = {t["id"] for t in requests.get(f"{BASE_URL}/api/topics", timeout=10).json()}
                created_topics.extend(after - before_topics - set(created_topics))
            except Exception:
                pass
            for tid in set(created_topics):
                try:
                    requests.delete(f"{BASE_URL}/api/topics/{tid}", timeout=10)
                except Exception:
                    pass
            browser.close()
        assert not console_errors, f"页面报错：{console_errors}"
