"""桌面配置预检、三文本拼装、重试与录音和试听缓存回归。"""
import json

import pytest

from server import api, arcade, bank, config, jobs, library, rewrite, speech_bridge, tts
from tests.test_generation_modes import client, env, wait_job  # noqa: F401


def test_preflight_does_not_create_a_topic(client):  # noqa: F811
    settings = config.DEFAULT_SETTINGS | {"stepfun_api_key": "fixture-stepfun"}
    assert not api._masked_settings(settings).get("llm_configured", True)
    config.save_settings({"stepfun_api_key": "fixture-stepfun"})
    response = client["client"].post("/api/generation-requests", json={
        "mode": "api", "question": "How do you cook?", "topic": "Cooking", "answer": "Oil.",
    })
    assert response.status_code == 422
    assert not list(client["topics_dir"].iterdir())


@pytest.mark.parametrize("old_script", [None, "[curious] A: Foo\nB: Yes.\nMore."])
def test_api_uses_deterministic_dialogue(monkeypatch, old_script):
    def chat(_settings, messages, _cancel):
        assert "芝麻酱" in repr(messages)
        return json.dumps({"natural_english": "I use sesame dressing.",
                           "podcast_script": old_script})

    monkeypatch.setattr(rewrite, "_chat", chat)
    result = rewrite.generate_complete_bundle({}, "What do you use?", "I use sauce.",
                                              chinese_intent="芝麻酱")
    assert result["podcast_text"] == "A: What do you use?\nB: I use sesame dressing."
    assert result["podcast_script"] == (
        "A: [curious] What do you use?\nB: [relaxed] I use sesame dressing."
    )


def test_parse_wrapped_dialogue():
    assert tts.parse_dialogue("[curious] Examiner: Why?\nCandidate: I cook.\nIt helps.") == [
        ("a", "[curious] Why?"), ("b", "I cook. It helps.")
    ]


def test_intent_upload_is_transient_and_retry_reuses_blind_answer(client, monkeypatch):  # noqa: F811
    tmp = client["tmp"] / ".tmp"
    monkeypatch.setattr(arcade, "TMP_DIR", tmp)
    from server import study_progress
    monkeypatch.setattr(study_progress, "PRIVATE_DIR", client["tmp"] / "progress")
    transcriptions = []

    def speech(_settings, method, **params):
        assert params["path"].read_bytes() == b"recording"
        transcriptions.append((method, params.get("language"), params["path"]))
        return {"transcript": "芝麻酱" if method == "transcribe_intent" else "I use sauce."}

    monkeypatch.setattr(speech_bridge, "request", speech)
    http = client["client"]
    headers = {"Content-Type": "audio/wav"}
    intent = http.post("/api/arcade/transcribe-intent?duration_sec=2", content=b"recording",
                       headers=headers)
    assert intent.json() == {"transcript": "芝麻酱"}
    assert not transcriptions[0][2].exists()
    blind = http.post("/api/arcade/transcribe-blind?duration_sec=2", content=b"recording",
                      headers=headers)
    assert transcriptions[1][1] == "en"
    created = http.post("/api/generation-requests", json={
        "mode": "agent", "question": "What do you use?", "topic": "Cooking",
        "answer": "I use sauce.", "chinese_intent": "芝麻酱",
        "blind_token": blind.json()["blind_token"],
    }).json()
    tid, iid = created["topic_id"], created["item_id"]
    url = f"/api/topics/{tid}/items/{iid}/retry-api"
    assert http.post(url).status_code == 422
    config.save_settings({"llm_provider": "custom", "llm_base_url": "http://localhost/v1"})
    monkeypatch.setattr(rewrite, "_chat", lambda *_: '{"natural_english":"I use sesame dressing."}')
    monkeypatch.setattr(tts, "generate_item_audio", lambda *_args, **_kwargs: None)
    job = http.post(url).json()
    assert wait_job(http, job["job_id"])["state"] == "done"
    assert (job["topic_id"], job["item_id"]) == (tid, iid)
    assert library.get_item_full(tid, iid)["original_answer"] == "I use sauce."
    assert study_progress.get_progress(tid, iid)["training_inputs"]["intent"] == "芝麻酱"
    entry = arcade._read(arcade._folder(tid, iid))[0]
    assert entry["stage"] == "blind"
    assert http.get(arcade._public(entry, tid, iid)["url"]).content == b"recording"
    assert len(list(library.item_path(tid, iid).parent.iterdir())) == 1
    assert not jobs._ACTIVE_TOPICS


def test_voice_previews_reuse_files_for_range_requests(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(api, "TMP_DIR", client["tmp"] / ".tmp")
    calls = []

    def synth(_settings, method, **params):
        if method == "profile_revision":
            return {"profile_hash": "profile-a"}
        assert method == "preview_line"
        calls.append(params["voice"])
        params["output"].write_bytes(b"RIFF preview bytes")
        return {}

    monkeypatch.setattr(speech_bridge, "request", synth)
    http = client["client"]
    voices = ["af_bella", "af_heart", "am_puck", "am_liam", "am_michael", "am_fenrir",
              "golden_self"]
    for voice in voices:
        url = f"/api/voices/kokoro_local/{voice}/sample"
        assert http.get(url).status_code == 200
        assert http.get(url, headers={"Range": "bytes=0-3"}).content == b"RIFF"
        assert http.get(url, headers={"Range": "bytes=0-3"}).status_code == 206
    assert calls == voices


def test_random_all_parts_and_exclusion(client, monkeypatch):  # noqa: F811
    snapshot = {"questions": [
        {"id": str(n), "part": n, "topic_id": "t", "text": f"Question {n}?", "text_zh": ""}
        for n in range(1, 4)
    ], "topics": [{"id": "t", "name_en": "T", "name_zh": "T"}], "sets": [
        {"id": "season", "name_zh": "Season", "start_month": 9, "end_month": 12,
         "question_ids": ["1", "2"]},
    ]}
    monkeypatch.setattr(bank, "load_bank", lambda: snapshot)
    out = client["client"].get("/api/bank/questions", params={
        "part": "all", "random": "true", "set_filter": "season", "topic": "t",
        "exclude_id": "1", "answer_status": "unanswered",
    })
    assert out.status_code == 200
    assert [row["id"] for row in out.json()["items"]] == ["2"]
