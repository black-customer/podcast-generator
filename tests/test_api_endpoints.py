"""验证双轨 API 端点（依赖 data/ 中已有真实生成数据；数据缺失时自动跳过）。"""
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)

def test_api():
    # 1. 检查健康
    r = client.get("/api/health")
    assert r.status_code == 200
    print("Health check:", r.json())

    # 2. 列出话题
    r = client.get("/api/topics")
    assert r.status_code == 200
    topics = r.json()
    print("Topics count:", len(topics))
    target_tid = None
    for t in topics:
        if "workflow" in t["id"]:
            target_tid = t["id"]
            break
    if target_tid is None:
        pytest.skip("data/ 中没有含 'workflow' 的话题数据（隔离测试见 test_core.py）")

    # 3. 获取条目
    r = client.get(f"/api/topics/{target_tid}")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) > 0
    iid = items[0]["id"]

    # 4. 测试独白与播客音频路由
    r_mono = client.get(f"/api/topics/{target_tid}/items/{iid}/audio/monologue")
    assert r_mono.status_code == 200
    assert len(r_mono.content) > 1000000
    print("Monologue audio endpoint OK, size:", len(r_mono.content))

    r_pod = client.get(f"/api/topics/{target_tid}/items/{iid}/audio/podcast")
    assert r_pod.status_code == 200
    assert len(r_pod.content) > 1000000
    print("Podcast audio endpoint OK, size:", len(r_pod.content))

    # 5. 测试整集音频与清单路由
    r_ep_mono = client.get(f"/api/topics/{target_tid}/episode?track=monologue")
    assert r_ep_mono.status_code == 200
    print("Monologue episode manifest OK:", r_ep_mono.json()["file"])

    r_ep_pod = client.get(f"/api/topics/{target_tid}/episode?track=podcast")
    assert r_ep_pod.status_code == 200
    print("Podcast episode manifest OK:", r_ep_pod.json()["file"])

    # 6. 测试声学音色展台路由
    r_voices = client.get("/api/voices")
    assert r_voices.status_code == 200
    voices = r_voices.json()
    assert len(voices) >= 4
    assert any(v["id"] == "tom_holland_vibe" for v in voices)
    print("Voices endpoint OK, count:", len(voices))

    # 7. 测试时间戳 Live Transcript 对齐路由
    r_tl = client.get(f"/api/topics/{target_tid}/items/{iid}/timeline/podcast")
    assert r_tl.status_code == 200
    tl = r_tl.json()
    assert len(tl) > 0
    assert "start" in tl[0] and "end" in tl[0] and "text" in tl[0]
    print("Timeline endpoint OK, line count:", len(tl))

    print("\nALL API ENDPOINTS & ACOUSTIC TIMELINE VERIFIED SUCCESSFULLY!")

if __name__ == "__main__":
    test_api()
