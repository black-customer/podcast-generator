"""B02 APP 离线包模式 E2E：导出 → 文件导入 → pack 模式列表/播放页/题库。

运行：服务已启动后 .venv/Scripts/python -m pytest tests/e2e/test_pack_ui.py -q
覆盖 packreader.js（stored zip 解析）、packmode.js（packApi 契约模拟、mediaUrl）、
app.js 的 api() 拦截与视图复用。浏览器上下文每次新建，IndexedDB 存档互不污染。
"""
import os
import re
from pathlib import Path

import pytest
import requests
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8765")
EXPORT_TOPIC = "01-my-studies"  # 小体积全生成话题（3 条目 86 秒）


@pytest.fixture(scope="module")
def pack_zip(tmp_path_factory) -> Path:
    r = requests.get(f"{BASE_URL}/api/pack/export?topics={EXPORT_TOPIC}", timeout=120)
    assert r.status_code == 200 and r.content[:2] == b"PK"
    p = tmp_path_factory.mktemp("pack") / "corpus.pack.zip"
    p.write_bytes(r.content)
    return p


def test_pack_mode_offline_flow(pack_zip: Path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        console_errors = []
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        def _on_console(msg):
            if msg.type == "error" and "Failed to load resource" not in msg.text:
                console_errors.append(msg.text)

        page.on("console", _on_console)
        try:
            # 1. 导入页：文件导入 → 自动跳转 #/topics（隐藏 input 先显形再注入）
            page.goto(f"{BASE_URL}/#/import")
            page.wait_for_selector("#pack-file", state="attached", timeout=5000)
            page.evaluate("document.getElementById('pack-file').style.display='block'")
            page.set_input_files("#pack-file", str(pack_zip))
            page.wait_for_url(re.compile(r"#/topics"), timeout=10000)
            assert page.evaluate("PackState.active") is True
            assert page.evaluate("document.body.classList.contains('pack-mode')")

            # 2. pack 模式话题列表：数据来自本地包
            page.wait_for_selector(".album-card", timeout=5000)
            names = page.evaluate("PackState.manifest.counts")
            assert names["topics"] >= 1

            # 3. 进入话题：条目行渲染（packApi 模拟 /api/topics/:id）
            page.click(".album-card >> nth=0")
            page.wait_for_selector(".track-row", timeout=5000)
            assert page.evaluate("document.querySelectorAll('.track-row').length") >= 1

            # 4. 播放页：音频 src 是 blob URL（不落服务器），时间轴渲染（预计算数据直出）
            page.click(".track-row >> nth=0")
            page.wait_for_selector(".reading-sheet", timeout=5000)
            page.wait_for_timeout(600)
            src = page.evaluate("document.getElementById('core-audio').src")
            assert src.startswith("blob:"), f"pack 模式音频应为 blob URL，实际 {src[:60]}"
            lyrics = page.evaluate("""() => {
              const pods = document.querySelectorAll('.transcript-row, .dialogue-bubble').length;
              const mono = (document.getElementById('mono-stream') || {}).innerText || '';
              return { pods, monoHasText: mono.length > 0 && !mono.includes('正在加载') };
            }""")
            assert lyrics["pods"] > 0 or lyrics["monoHasText"], f"时间轴未渲染：{lyrics}"

            # 5. 题库 pack 模式：bank.json 生效 + 随机取题
            page.goto(f"{BASE_URL}/#/bank")
            page.wait_for_selector(".bank-row", timeout=5000)
            assert page.evaluate("PackState.bank !== null")
            page.click("text=随机来一题")
            page.wait_for_selector(".bank-answer-card", timeout=5000)

            # 6. 离线语义：服务端专属接口被拒（工作台导航也已隐藏）
            hidden = page.evaluate(
                "getComputedStyle(document.querySelector('.nav-item[data-filter=manage]')).display"
            )
            assert hidden == "none"
        finally:
            browser.close()
        assert not console_errors, f"页面报错：{console_errors}"
