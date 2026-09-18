"""工作台管理视图的 Playwright 冒烟测试（不触发真实 TTS：只验证 UI 渲染与交互流）。

运行：服务已启动后 .venv/Scripts/python -m pytest tests/e2e/test_manage_ui.py -q
"""
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8765"


def test_manage_view_workflow():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        console_errors = []
        page.on("pageerror", lambda err: console_errors.append(str(err)))
        def _on_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text)
        page.on("console", _on_console)

        # 1. 打开工作台
        page.goto(f"{BASE_URL}/#/manage")
        page.wait_for_selector("#mg-settings-form", timeout=5000)
        assert page.is_visible("#mg-topic-list")

        # 2. 设置表单应载入当前值且模型下拉有选项
        assert page.locator("#mg-s-model option").count() >= 1
        assert page.is_visible("#mg-test-btn")

        # 3. 新建话题 → 自动选中 → 面板出现生成工具栏
        import time as _t
        topic_name = f"e2e-manage-{int(_t.time())}"
        try:
            page.fill("#mg-new-topic", topic_name)
            page.click("#mg-create-topic")
            page.wait_for_selector("#mg-gen-topic", timeout=5000)

            # 4. 新建条目 → 列表出现 → 打开编辑器
            page.fill("#mg-new-q", "Do you like coffee?")
            page.click("#mg-create-item")
            page.wait_for_selector("#mg-item-list .mg-item-row", timeout=5000)
            page.locator("#mg-item-list [data-edit]").click()
            page.wait_for_selector("#mg-f-question", timeout=5000)
            assert page.input_value("#mg-f-question") == "Do you like coffee?"

            # 5. 修改中文回答并保存 → 重新加载后仍在（PATCH 部分更新语义）
            page.fill("#mg-f-chinese", "我超爱咖啡。")
            page.click("#mg-save-item")
            page.wait_for_timeout(800)
            page.locator("#mg-item-list [data-edit]").click()
            page.wait_for_selector("#mg-f-chinese", timeout=5000)
            q_val = page.input_value("#mg-f-question")
            assert q_val == "Do you like coffee?", "保存后问题不应被清空"
            assert page.input_value("#mg-f-chinese") == "我超爱咖啡。"
        finally:
            # 失败也要清理，避免遗留空话题污染真实语料库
            import requests
            try:
                topics = requests.get(f"{BASE_URL}/api/topics", timeout=10).json()
                for t in topics:
                    if t["name"] == topic_name:
                        requests.delete(f"{BASE_URL}/api/topics/{t['id']}", timeout=10)
            except Exception:
                pass

        # 8. 无 JS 运行时异常
        assert len(console_errors) == 0, f"Captured console errors: {console_errors}"
        browser.close()


if __name__ == "__main__":
    test_manage_view_workflow()
    print("Manage UI E2E Passed!")
