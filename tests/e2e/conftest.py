"""浏览器回归隔离 Q05 私有写入；专门测试可用更具体的模拟覆盖。"""
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Browser, BrowserContext


@pytest.fixture(autouse=True)
def isolate_private_continuity(monkeypatch):
    original_context = Browser.new_context

    def context(self, *args, **kwargs):
        # Service Worker 接管后 Page.route 无法拦截私有写入，模拟回归必须禁用它。
        kwargs.setdefault("service_workers", "block")
        return original_context(self, *args, **kwargs)

    monkeypatch.setattr(Browser, "new_context", context)
    def bind(page):
        drafts, progress = {}, {}

        def handler(route):
            request = route.request
            path = urlparse(request.url).path
            query = parse_qs(urlparse(request.url).query)
            body = request.post_data_json if request.method == "PUT" else {}
            if "answer-drafts" in path:
                qid = path.rsplit("/", 1)[1]
                if path.endswith("/answer-drafts"):
                    result = {"drafts": list(drafts.values())}
                else:
                    current = drafts.get(qid, {"answer": "", "mode": "agent", "revision": 0})
                    if request.method == "PUT":
                        current = {**body, "question_id": qid,
                                   "revision": current["revision"] + 1}
                        drafts[qid] = current
                    elif request.method == "DELETE":
                        current = {"answer": "", "mode": "agent",
                                   "revision": current["revision"] + 1}
                        drafts[qid] = current
                    result = current
            elif path.endswith("/latest"):
                result = next(iter(progress.values()), {"latest": None})
            else:
                source = {name: query.get(name, [default])[0] for name, default in
                          [("kind", "item"), ("topic_id", ""), ("item_id", ""),
                           ("track", "podcast")]}
                result = {**source, "position": 0, "state": "ready",
                          "audio_fingerprint": "isolated-test-audio"}
                if request.method == "PUT":
                    result.update(body)
                    progress[str(body)] = result
            route.fulfill(json=result)

        page.route("**/api/answer-drafts**", handler)
        page.route("**/api/listening-progress**", handler)
        return page

    for cls in (Browser, BrowserContext):
        original = cls.new_page

        def wrapped(self, *args, _original=original, **kwargs):
            if isinstance(self, Browser):
                kwargs.setdefault("service_workers", "block")
            return bind(_original(self, *args, **kwargs))

        monkeypatch.setattr(cls, "new_page", wrapped)
