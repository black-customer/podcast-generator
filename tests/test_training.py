"""单题训练领域回归；全部使用临时合成语料，无外部调用。"""

import copy
import json
import subprocess
from pathlib import Path

import pytest

from server import training

MATERIAL = {
    "source_fingerprint": "text-v1",
    "sentences": [
        {"zh": "我喜欢做饭。", "en": "I enjoy cooking."},
        {
            "zh": "让我放松。",
            "en": "It helps me relax.",
            "original_error": {
                "quote": "It help me",
                "issue": "主谓一致",
                "correction": "It helps me",
            },
        },
    ],
}


def apply(state, action, day="2026-10-15", **kwargs):
    if action == "understand":
        kwargs.setdefault("focus", [0, 1])
    payload = {
        "version": 2,
        "action_id": str(len(state.get("receipts", {}))),
        "fingerprint": "v1",
        "action": action,
        **kwargs,
    }
    return training.reduce(state, payload, MATERIAL, day + "T10:00:00+08:00", 1)


def ready():
    state = training.initial({}, "v1")
    for name in ("start", "inputs", "understand"):
        state = apply(state, name)
    state = apply(state, "sentence", index=0, rating="independent")
    state = apply(state, "sentence", index=1, rating="independent")
    return apply(state, "outline_done")


def test_retrieval_is_not_dictation_or_reveal():
    state = training.initial({}, "v1")
    for name in ("start", "inputs", "understand"):
        state = apply(state, name)
    state = apply(state, "reveal", index=0)
    with pytest.raises(ValueError):
        apply(state, "sentence", index=0, rating="independent")
    state = apply(state, "dictation", index=0, draft="I enjoy cooking.", passed=True)
    assert not state["sentences"].get("0", {}).get("oral")
    state = apply(state, "hide", index=0)
    state = apply(state, "sentence", index=0, rating="needs_hint")
    assert state["sentences"]["0"]["oral"] == "needs_hint"


def test_delayed_mastery_failure_and_idempotency():
    state = ready()
    state = apply(state, "whole", rating="independent", no_recording=True)
    assert state["status"] == "awaiting_review" and state["due_date"] == "2026-10-16"
    state = apply(state, "review", "2026-10-16")
    state = apply(state, "whole", "2026-10-16", rating="independent", no_recording=True)
    assert state["due_date"] == "2026-10-19" and state["successes"] == 1
    state = apply(state, "review", "2026-10-16")
    state = apply(state, "whole", "2026-10-16", rating="independent", no_recording=True)
    assert state["successes"] == 1 and state["due_date"] == "2026-10-19"
    state = apply(state, "review", "2026-10-19")
    state = apply(state, "whole", "2026-10-19", rating="independent", no_recording=True)
    assert state["status"] == "mastered" and state["due_date"] == "2026-10-26"
    state = apply(state, "review", "2026-10-26")
    state = apply(
        state, "whole", "2026-10-26", rating="unable", no_recording=True, weak_indices=[1]
    )
    assert state["status"] == "training" and state["successes"] == 0
    assert state["focus"] == [1] and state["sentences"]["0"]["oral"] == "independent"
    assert state["attempts"][-1]["rating"] == "unable"


def test_receipt_undo_stale_and_readonly_migration():
    old = {"stage": "summary", "facts": {"0": {"passed": True}}, "recordings": [{"id": "old"}]}
    source = copy.deepcopy(old)
    state = training.initial(old, "v1")
    assert old == source and state["status"] == "awaiting_review"
    assert state["successes"] == 0 and state["legacy_completed"]
    payload = {"version": 2, "fingerprint": "v1", "action_id": "one", "action": "review"}
    state = training.reduce(state, payload, MATERIAL, "2026-10-15T10:00:00+08:00", 1)
    assert training.reduce(state, payload, MATERIAL, "2026-10-15T10:00:00+08:00", 1) == state
    state = apply(state, "undo")
    assert state["phase"] == "summary"
    assert training.reduce(state, payload, MATERIAL, "2026-10-15T10:00:00+08:00", 1) == state
    with pytest.raises(ValueError):
        training.reduce(
            state,
            {**payload, "action_id": "stale", "fingerprint": "old"},
            MATERIAL,
            "2026-10-15T10:00:00+08:00",
            1,
        )


def test_part_three_requires_followup_and_hints_block_success():
    state = ready()
    with pytest.raises(ValueError):
        training.reduce(
            state,
            {
                "version": 2,
                "action_id": "p3",
                "fingerprint": "v1",
                "action": "whole",
                "rating": "independent",
                "no_recording": True,
            },
            MATERIAL,
            "2026-10-15T10:00:00+08:00",
            3,
        )
    state = apply(state, "whole_hint")
    with pytest.raises(ValueError):
        apply(state, "whole", rating="independent", no_recording=True)


def test_mobile_matches_python_scenarios():
    root = Path(__file__).resolve().parents[1]
    actions = [{"action": "start"}, {"action": "inputs"}, {"action": "understand", "focus": [0, 1]}]
    actions += [{"action": "sentence", "index": n, "rating": "independent"} for n in (0, 1)]
    actions += [
        {"action": "outline_done"},
        {"action": "whole", "rating": "independent", "no_recording": True},
    ]
    state = training.initial({}, "v1")
    snapshots = []
    for n, a in enumerate(actions):
        a.update(version=2, action_id=str(n), fingerprint="v1")
        state = training.reduce(state, a, MATERIAL, "2026-10-15T10:00:00+08:00", 1)
        snapshots.append(state)
    code = """const T=require('./web/training-core.js');let s=T.initial({},'v1');
    const d=JSON.parse(require('fs').readFileSync(0,'utf8'));const out=d.actions.map(a=>{
    s=T.reduce(s,a,d.material,'2026-10-15T10:00:00+08:00',1);return s;});
    process.stdout.write(JSON.stringify(out));"""
    result = subprocess.run(
        ["node", "-e", code],
        input=json.dumps({"actions": actions, "material": MATERIAL}),
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == snapshots


@pytest.fixture()
def stored(tmp_path, monkeypatch):
    from server import library, study, study_progress

    monkeypatch.setattr(library, "TOPICS_DIR", tmp_path / "topics")
    monkeypatch.setattr(study_progress, "PRIVATE_DIR", tmp_path / "private")
    topic = library.create_topic("Training")
    item = library.create_item(
        topic["id"],
        {
            "question": "Do you enjoy cooking?",
            "original_answer": "I enjoy cooking.",
            "natural_english": "I enjoy cooking.",
            "podcast_text": "A: Do you enjoy cooking?\nB: I enjoy cooking.",
        },
    )
    (library.item_path(topic["id"], item["id"]) / "audio_podcast.mp3").write_bytes(b"audio")
    study.save_material(
        topic["id"],
        item["id"],
        {
            "complete_chinese": "我喜欢做饭。",
            "sentences": [
                {
                    "zh": "我喜欢做饭。",
                    "en": "I enjoy cooking.",
                    "explanation": "用法",
                    "usage": "说明",
                }
            ],
        },
    )
    return topic["id"], item["id"], tmp_path


def test_api_readonly_receipts_audio_change_and_legacy_preserved(stored):
    from fastapi.testclient import TestClient

    from server import library, study_progress
    from server.main import app

    tid, iid, tmp = stored
    url = f"/api/topics/{tid}/items/{iid}/study/training"
    client = TestClient(app)
    ctx = client.get(url).json()
    assert ctx["state"]["status"] == "unstarted"
    assert not (tmp / "private").exists()
    payload = {
        "version": 2,
        "fingerprint": ctx["state"]["fingerprint"],
        "action_id": "start",
        "action": "start",
        "unexposed": False,
    }
    assert client.post(url + "/actions", json=payload).status_code == 200
    assert client.post(url + "/actions", json=payload).json()["state"]["phase"] == "inputs"
    study_progress.save_progress(tid, iid, {"facts": {"0": {"passed": True}}})
    (library.item_path(tid, iid) / "audio_podcast.mp3").write_bytes(b"changed")
    assert client.post(url + "/actions", json=payload).status_code == 409
    fresh = client.get(url).json()
    assert fresh["changed"]
    payload.update(action_id="new", fingerprint=fresh["state"]["fingerprint"])
    client.post(url + "/actions", json=payload)
    saved = study_progress.get_progress(tid, iid)
    assert saved["facts"]["0"]["passed"]
    assert len(saved["training_history"]) == 1


def test_unrelated_recordings_cannot_be_evidence(stored):
    tid, iid, _ = stored
    state = training.get(tid, iid)["state"]
    with pytest.raises(ValueError, match="录音"):
        training.action(
            tid,
            iid,
            {
                "version": 2,
                "fingerprint": state["fingerprint"],
                "action_id": "forged",
                "action": "start",
                "recording_id": "foreign",
            },
        )


def test_material_arriving_does_not_erase_pending_baseline(stored):
    from server import library
    tid, iid, _ = stored
    path = library.item_path(tid, iid)
    material_path = path / "study_material.json"
    saved = material_path.read_bytes()
    material_path.unlink()
    state = training.get(tid, iid)["state"]
    body = {"version": 2, "fingerprint": state["fingerprint"],
            "action_id": "a", "action": "start", "unexposed": True}
    state = training.action(tid, iid, body)["state"]
    training.action(tid, iid, {**body, "action_id": "b", "action": "inputs",
                             "answer": "I cook.", "intent": "放松", "feedback": "建议"})
    material_path.write_bytes(saved)
    ctx = training.get(tid, iid)
    assert ctx["state"]["phase"] == "understand"
    assert ctx["state"]["inputs"]["answer"] == "I cook."
    assert ctx["state"]["baseline_unexposed"]


def test_mobile_training_exchange_and_readonly():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(["node", "tests/training_mobile.cjs"], cwd=root,
                            capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout + result.stderr


def test_recording_retry_does_not_create_duplicates(stored):
    from server import study_progress
    tid, iid, _ = stored
    first = study_progress.save_recording(tid, iid, "recall", b"audio", 1, "audio/webm",
                                         upload_key="one-upload")
    again = study_progress.save_recording(tid, iid, "recall", b"audio", 1, "audio/webm",
                                         upload_key="one-upload")
    assert first["id"] == again["id"]
    assert len(study_progress.get_progress(tid, iid)["recordings"]) == 1
    with pytest.raises(ValueError):
        study_progress.save_recording(tid, iid, "recall", b"different", 1, "audio/webm",
                                      upload_key="one-upload")
