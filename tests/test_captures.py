"""素材、语块及私有备份契约的隔离回归。"""

import base64
import json

import pytest

from scripts import package
from server import capture_distill, captures, rewrite

PIXEL = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lE"
         "QVR42mP8/x8AAwMCAO+WNwoAAAAASUVORK5CYII=")


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(captures, "CAPTURES_DIR", tmp_path / "captures")
    return tmp_path / "captures"


def card():
    return {
        "target_chunk": "put someone on the spot", "chunk_in_sentence": "put you on the spot",
        "en": "I didn't mean to put you on the spot.", "zh": "我并非故意为难你。",
        "chunk_zh": "让人措手不及", "trigger_context": "你突然让别人当场作答。",
        "disambiguator": "突然被要求表态", "explanation": "强调必须当场回答。",
        "usage_boundary": "用于临时点名", "feynman_hook": "像聚光灯突然打到脸上。",
        "transfer_prompt_zh": "想想被面试官突然点名的场景。",
        "transfer_example_en": "The interviewer put me on the spot.",
    }


def scene(note_id="note-1"):
    return {"id": note_id, "seriesId": "series-1", "seriesTitle": "Sample", "epTitle": "E2",
            "time": 258, "userNote": "这是测试素材", "imageUrl": PIXEL,
            "source": {"url": "https://www.bilibili.com/video/BV1234567890?p=2"}}


def test_card_validation_requires_contiguous_target_and_evidence():
    raw = card()
    saved = captures.validate_card_payload(raw)
    assert saved["cloze_prompt"] == "I didn't mean to [p__] [y__] [o_] [t__] [s___]."
    with pytest.raises(ValueError):
        captures.validate_card_payload(raw | {"chunk_in_sentence": "mean on the spot"})
    error = {"quote": "I puts you", "issue": "动词形式", "correction": "I put you"}
    with pytest.raises(ValueError):
        captures.validate_card_payload(raw | {"original_error": error})
    result = captures.validate_card_payload(raw | {"original_error": error},
                                            original_english="I puts you on the spot.")
    assert result["original_error"] == error
    with pytest.raises(ValueError):
        captures.validate_card_payload(raw | {"original_error": error | {"issue": "口音"}},
                                       original_english="I puts you on the spot.")


def test_agent_validates_whole_batch_then_writes_inbox(store):
    first = captures.ingest_snippet(text="The interviewer put me on the spot.")
    second = captures.ingest_snippet(images=[PIXEL])
    payload = {"captures": [{"capture_id": first["id"], "cards": [card()]},
                            {"capture_id": second["id"], "cards": [card() | {"zh": ""}]}]}
    with pytest.raises(ValueError):
        capture_distill.complete_from_json(payload)
    assert captures.list_cards() == []
    payload["captures"][1]["cards"] = [card()]
    capture_distill.complete_from_json(payload)
    assert len(captures.list_cards(status="inbox")) == 2
    assert not list(store.rglob("*.tmp~"))
    prompt = capture_distill.build_agent_prompt([second["id"]])
    assert (store / second["id"] / "assets" / "frame.png").as_posix() in prompt


def test_scene_retries_preserve_first_source(store):
    first = captures.ingest_scenes([scene()])
    again = captures.ingest_scenes([scene() | {"userNote": "已修改"}])
    assert first["imported"] == 1 and again["duplicates"] == 1
    entry = captures.get_capture(first["capture_ids"][0])
    assert entry["source"]["userNote"] == "这是测试素材"
    assert entry["source"]["source_url"].endswith("?p=2&t=258")
    with pytest.raises(ValueError):
        captures.ingest_scenes([scene("bad") | {"source": {"url": "https://example.org/"}}])
    assert len(captures.list_captures()) == 1


def test_distill_passes_image_to_vision_service_and_keeps_result_in_inbox(store, monkeypatch):
    capture = captures.ingest_snippet(text="A note", images=[PIXEL])
    calls = []

    def post(url, **kwargs):
        import httpx

        calls.append((url, kwargs))
        return httpx.Response(200, json={"choices": [
            {"message": {"content": json.dumps({"cards": [card()]})}},
        ]})

    monkeypatch.setattr(rewrite.httpx, "post", post)
    monkeypatch.setattr(capture_distill, "load_settings", lambda: {
        "vision_base_url": "https://vision.example.test/v1", "vision_model": "fixture",
        "vision_api_key": "placeholder-fixture", "llm_api_key": "separate-fixture",
    })
    saved = capture_distill.distill_capture_api(capture["id"])
    assert saved[0]["status"] == "inbox"
    url, request = calls[0]
    assert url == "https://vision.example.test/v1/chat/completions"
    assert request["headers"]["Authorization"] == "Bearer placeholder-fixture"
    content = request["json"]["messages"][-1]["content"]
    assert content[1] == {"type": "image_url", "image_url": {"url": PIXEL}}


def test_invalid_image_and_portable_audit(tmp_path, store, monkeypatch):
    image = base64.b64encode(b"<svg>not an image</svg>").decode()
    with pytest.raises(ValueError):
        captures.ingest_snippet(images=["data:image/png;base64," + image])
    assert captures.list_captures() == []
    path = tmp_path / "data" / "captures" / "cap_example" / "source.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(package, "BASE", tmp_path)
    monkeypatch.setattr(package, "OUT", tmp_path / "private.zip")
    monkeypatch.setattr(package, "INCLUDE_DIRS", ["data/captures"])
    assert package.main() == 1
    assert not package.OUT.exists()


def test_capture_configuration_redacts_tokens():
    from server.api import _masked_settings

    data = _masked_settings({"vision_api_key": "test-vision-secret",
                             "scene_sync_token": "test-sync-secret"})
    assert "test-vision-secret" not in repr(data) and "test-sync-secret" not in repr(data)
