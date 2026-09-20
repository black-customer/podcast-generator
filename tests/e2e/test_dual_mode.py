"""R03 Agent/API 双模式 E2E：指令复制 → Agent CLI 完成 → 完成页呈现 → 下载入口。

运行：服务已启动后 .venv/Scripts/python -m pytest tests/e2e/test_dual_mode.py -q
Agent 执行侧用 pipeline.py complete --no-audio（e2e 绝不触发真实 TTS）；
音频出现以非空占位文件模拟——完成页与轮询只依赖文件存在性。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest
import requests
from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE))
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8765")

RESULT_JSON = {
    "natural_english": (
        "Well, my favorite teacher was my high school English teacher. She was really "
        "patient, and she always pushed us to ask better questions instead of just "
        "memorizing answers."
    ),
    "podcast_text": (
        "A: Who was your favorite teacher?\n"
        "B: My high school English teacher, for sure. She was really patient, and she "
        "always pushed us to ask better questions instead of just memorizing answers."
    ),
    "podcast_script": (
        "A: Who was your favorite teacher [pause] then?\n"
        "B: My high school English teacher, for sure [break] She was really patient, and "
        "she always pushed us to ask better questions instead of just memorizing answers."
    ),
}


def _bank_ready() -> bool:
    try:
        return requests.get(f"{BASE_URL}/api/bank/questions", timeout=10).json().get("available")
    except Exception:
        return False


def test_agent_mode_copy_cli_complete_and_done_page():
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
            if msg.type == "error" and "Failed to load resource" not in msg.text:
                console_errors.append(msg.text)

        page.on("console", _on_console)
        try:
            # 1. 选题作答（Agent 模式默认选中）
            page.goto(f"{BASE_URL}/#/bank")
            page.wait_for_selector(".bank-row", timeout=5000)
            un = requests.get(
                f"{BASE_URL}/api/bank/questions?part=1&page_size=100", timeout=10
            ).json()
            target = next((it for it in un["items"] if not it["answered"]), None)
            assert target, "Part1 应存在未作答题目"
            page.locator(".bank-row", has_text=target["text"][:40]).first.click()
            page.wait_for_selector("#bank-answer-input", timeout=5000)
            assert page.locator("input[name='bank-gen-mode'][value='agent']").is_checked()
            page.fill("#bank-answer-input", f"dual mode e2e {stamp}: 我的老师很有耐心。")
            page.click("#bank-answer-submit")

            # 2. Agent 指令出现：含完成命令与目标 id，不含任何密钥字段
            page.wait_for_selector("#agent-prompt-box", timeout=5000)
            prompt_text = page.locator("#agent-prompt-box").inner_text()
            assert "pipeline.py complete" in prompt_text
            assert "skills/ielts-audio/SKILL.md" in prompt_text
            topic_id = re.search(r"--topic-id (\S+)", prompt_text).group(1)
            item_id = re.search(r"--item-id (\S+)", prompt_text).group(1)
            created_topics.append(topic_id)
            assert "api_key" not in prompt_text.lower()

            # 3. 一键复制有反馈
            page.click("#agent-copy-btn")
            page.wait_for_timeout(300)
            assert "已复制" in page.locator("#agent-copy-btn").inner_text()

            # 4. 模拟 Agent 执行：canonical CLI（--no-audio，不触发真实 TTS）
            with tempfile.NamedTemporaryFile(
                "w", suffix=".json", delete=False, encoding="utf-8"
            ) as fh:
                json.dump(RESULT_JSON, fh, ensure_ascii=False)
                result_path = fh.name
            py = BASE / ".venv" / "Scripts" / "python.exe"
            r = subprocess.run(
                [str(py), "pipeline.py", "complete", "--topic-id", topic_id,
                 "--item-id", item_id, "--result-json", result_path, "--no-audio"],
                cwd=str(BASE), capture_output=True, text=True, timeout=120,
            )
            assert r.returncode == 0, r.stderr or r.stdout
            assert "play_url" in r.stdout and item_id in r.stdout

            # 5. 音频出现（占位文件；完成页/轮询只依赖存在性）→ 等待轮询自动跳转完成页
            audio_file = (
                BASE / "data" / "topics" / topic_id / "items" / item_id / "audio_podcast.mp3"
            )
            audio_file.write_bytes(b"ID3" + b"\0" * 2048)
            page.wait_for_url(re.compile(r"#/done/"), timeout=8000)
            page.wait_for_selector(".done-natural", timeout=5000)
            assert "favorite teacher" in page.locator(".done-natural").inner_text()
            assert page.locator("text=打开精听播放器").count() == 1
            assert page.locator("text=下载 MP3").count() >= 1
            # 表演稿对普通用户不可见
            body_text = page.locator("body").inner_text()
            assert "[pause]" not in body_text and "[break]" not in body_text
        finally:
            for tid in created_topics:
                try:
                    requests.delete(f"{BASE_URL}/api/topics/{tid}", timeout=10)
                except Exception:
                    pass
            browser.close()
        assert not console_errors, f"页面报错：{console_errors}"
