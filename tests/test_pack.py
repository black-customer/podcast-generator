"""B02 语料包导出测试：包结构、幂等、话题过滤、API 端点。"""
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi.testclient import TestClient

from server import library, pack
from server.config import DATA_DIR
from server.main import app

client = TestClient(app)


@pytest.fixture()
def packed_topic(tmp_path: Path, monkeypatch):
    """临时库中建一个含双轨假音频与时间轴的话题（不触碰真实 data/）。"""
    topics = tmp_path / "topics"
    topics.mkdir(parents=True)
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    t = library.create_topic("pack-test-dummy")
    tid = t["id"]
    try:
        created = library.create_item(
            tid,
            {
                "question": "Pack test question?",
                "chinese": "打包测试回答",
                "natural_english": "A pack test answer.",
                "fish_script": "A: Pack test.\nB: Pack test reply.",
            },
        )
        d = library.item_path(tid, created["id"])
        (d / "audio_monologue.mp3").write_bytes(b"FAKE-MONO-MP3-BYTES")
        (d / "audio_podcast.mp3").write_bytes(b"FAKE-POD-MP3-BYTES")
        (d / "timeline_podcast.json").write_text(
            json.dumps([{"start": 0.0, "end": 1.0, "text": "Pack test."}]), encoding="utf-8"
        )
        yield tid
    finally:
        library.delete_topic(tid)


def _read_zip(path: Path) -> zipfile.ZipFile:
    return zipfile.ZipFile(path)


def test_pack_carries_material_but_never_private_progress(tmp_path, packed_topic, monkeypatch):
    from server import study

    topic = library.get_topic(packed_topic)
    iid = topic["items"][0]["id"]
    expected = {"version": 1, "source_fingerprint": "synthetic", "complete_chinese": "测试",
                "sentences": [{"en": "Test.", "zh": "测试", "explanation": "讲解",
                               "usage": "用法"}]}
    monkeypatch.setattr(study, "get_material", lambda *a: {"status": "ready", "material": expected})
    path = library.item_path(packed_topic, iid)
    (path / "state.json").write_text('{"private": "do-not-export"}', encoding="utf-8")
    output = tmp_path / "material.zip"
    pack.build_pack(output, [packed_topic])
    with zipfile.ZipFile(output) as z:
        payload = json.loads(z.read(f"topics/{packed_topic}/items/{iid}/item.json"))
        assert payload["material"] == expected
        assert b"do-not-export" not in z.read(f"topics/{packed_topic}/items/{iid}/item.json")


def test_build_pack_structure(tmp_path: Path, packed_topic: str):
    out = tmp_path / "p1.zip"
    result = pack.build_pack(out_path=out, topic_ids=[packed_topic])
    zf = _read_zip(out)
    names = zf.namelist()
    assert "pack.json" in names
    assert f"topics/{packed_topic}/items/" in str(names)
    assert any(n.endswith("/item.json") for n in names)
    manifest = json.loads(zf.read("pack.json"))
    assert manifest["counts"] == {"topics": 1, "items": 1}
    assert manifest["content_hash"]
    # 条目 payload：文本 + 双轨音频 + 预计算时间轴（缓存命中 → estimated 模式）
    item_names = [n for n in names if n.endswith("/item.json")]
    payload = json.loads(zf.read(item_names[0]).decode("utf-8"))
    assert payload["texts"]["chinese"] == "打包测试回答"
    assert payload["audio"]["monologue"] == "audio_monologue.mp3"
    assert payload["audio"]["podcast"] == "audio_podcast.mp3"
    tl = payload["timelines"]["podcast"]
    assert tl["mode"] == "estimated"
    assert tl["lines"][0]["text"] == "Pack test."
    assert zf.read(f"topics/{packed_topic}/items/{payload['id']}/audio_monologue.mp3") == (
        b"FAKE-MONO-MP3-BYTES"
    )
    # 题库快照按本地存在性入包
    bank_in_pack = "bank.json" in names
    assert bank_in_pack == (DATA_DIR / "question_bank.json").exists()
    assert manifest.get("has_bank", False) == bank_in_pack
    # store 不压缩：手机端零依赖解包的前提
    infos = [i for i in zf.infolist() if i.filename.endswith(".mp3")]
    assert all(i.compress_type == zipfile.ZIP_STORED for i in infos)
    assert result["size_bytes"] == out.stat().st_size


def test_build_pack_idempotent_hash(tmp_path: Path, packed_topic: str):
    a = pack.build_pack(out_path=tmp_path / "a.zip", topic_ids=[packed_topic])
    b = pack.build_pack(out_path=tmp_path / "b.zip", topic_ids=[packed_topic])
    assert a["manifest"]["content_hash"] == b["manifest"]["content_hash"], "同数据同哈希"


def test_build_pack_missing_topic(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        pack.build_pack(out_path=tmp_path / "x.zip", topic_ids=["no-such-topic"])


def test_api_pack_export(packed_topic: str):
    try:
        r = client.get(f"/api/pack/export?topics={packed_topic}")
        assert r.status_code == 200
        assert r.content[:2] == b"PK"
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        assert "pack.json" in zf.namelist()
        r404 = client.get("/api/pack/export?topics=no-such")
        assert r404.status_code == 404
    finally:
        pass  # 端点经 BackgroundTask 自删导出文件（corpus-<uuid>.pack.zip），无需手动清理
