"""看剧场景导入的服务边界与去重。"""
from fastapi.testclient import TestClient

from server import captures, config
from server.main import app


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(captures, "CAPTURES_DIR", tmp_path / "captures")
    return TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 1234))


def _backup():
    return {"format": "caption-study-backup", "schemaVersion": 1, "notes": [{
        "id": "scene-one", "time": 21.2, "seriesId": "demo",
        "source": {"url": "https://www.bilibili.com/bangumi/play/ep10"},
    }]}


def test_scene_pairing_is_narrow(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    ping = "/api/captures/scenes/ping"
    inbox = "/api/captures/scenes/inbox"
    pair = "/api/settings/scene-sync-token"
    assert client.get(ping).status_code == 403
    assert client.post(inbox, json=_backup()).status_code == 403
    origin = {"Origin": "https://www.bilibili.com", "Sec-Fetch-Site": "cross-site"}
    assert client.post(pair, headers=origin, json={}).status_code == 403
    assert client.post(pair, headers={"Origin": "https://localhost"}, json={}).status_code == 403
    response = client.post(pair, json={})
    token = response.json()["token"]
    assert response.headers["cache-control"] == "no-store"
    assert client.post(pair, json={}).json()["token"] == token
    assert token not in client.get("/api/settings").text
    key = "X-Scene-Sync-Token"
    assert client.get(ping, headers={**origin, key: "wrong"}).status_code == 403
    headers = {**origin, key: token}
    assert client.get(ping, headers=headers).json() == {"ok": True}
    remote = TestClient(app, base_url="http://127.0.0.1", client=("192.0.2.55", 1234))
    assert remote.get(ping, headers=headers).status_code == 403
    assert client.get(ping, headers={**headers, "Host": "attacker.test"}).status_code == 403
    assert client.post(ping, headers=headers, json={}).status_code == 403
    assert client.post("/api/captures/scenes/import-json", headers=headers,
                       json=_backup()).status_code == 403
    assert client.get("/api/settings", headers=headers).status_code == 403
    result = client.post(inbox, headers=headers, json={"notes": _backup()["notes"]}).json()
    assert result["imported"] == 1
    assert client.post(pair, json={"reset": True}).json()["token"] != token
    assert client.get(ping, headers=headers).status_code == 403


def test_scene_backup_validation_and_dedup(tmp_path, monkeypatch):
    client = _setup(tmp_path, monkeypatch)
    path = "/api/captures/scenes/import-json"
    backup = _backup()
    assert client.post(path, json={**backup, "schemaVersion": True}).status_code == 400
    assert client.post(path, json={**backup, "format": "anything"}).status_code == 400
    assert client.post(path, content="NaN").status_code == 400
    assert client.post(path, content="{}", headers={"Content-Length": "157286401"}
                       ).status_code == 413
    bad = _backup()
    bad["notes"][0]["source"]["url"] = "https://www.bilibili.com.attacker.test/video/BV1234567890"
    assert client.post(path, json=bad).status_code == 400
    first = client.post(path, json=backup).json()
    again = client.post(path, json=backup).json()
    assert first["imported"] == again["duplicates"] == 1
    assert first["capture_ids"] == again["capture_ids"]
