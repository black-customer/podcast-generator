import json

import httpx

from scripts import package
from server import config, rewrite
from server.api import _masked_settings


def test_deepseek_bundle_validates_evidence_and_chunk(monkeypatch):
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs["json"]))
        return httpx.Response(200, json={"choices": [{"message": {"content": '''{
          "natural_english":"It helps me unwind.",
          "podcast_text":"A: Why do you swim?\\nB: It helps me unwind.",
          "podcast_script":"A: Why do you swim?\\nB: It helps me unwind.",
          "study_material":{"complete_chinese":"游泳帮助我放松。","sentences":[{
            "en":"It helps me unwind.","zh":"这让我放松。","usage":"help 人做事",
            "explanation":"helps 与主语一致","key_chunk":"helps me unwind",
            "original_error":{"quote":"It help me unwind","issue":"主谓一致",
            "correction":"It helps me unwind","category":"subject_verb_agreement"}}]}
        }'''}}]})

    monkeypatch.setattr(rewrite.httpx, "post", post)
    settings = {**config.DEFAULT_SETTINGS, "llm_api_key": "test-value"}
    result = rewrite.generate_complete_bundle(settings, "Why do you swim?", "It help me unwind")
    assert len(calls) == 1
    url, payload = calls[0]
    assert url == "https://api.deepseek.com/v1/chat/completions"
    assert payload["model"] == "deepseek-flash"
    assert payload["response_format"] == {"type": "json_object"}
    sentence = result["study_material"]["sentences"][0]
    assert sentence["key_chunk"] == "helps me unwind"
    assert sentence["original_error"]["category"] == "subject_verb_agreement"


def test_text_credentials_are_write_only():
    data = _masked_settings({"llm_api_key": "test-one", "deepseek_api_key": "test-two"})
    assert data["llm_api_key"] == ""
    assert data["llm_api_key_set"]
    assert "test-two" not in repr(data)


def test_explicit_stepfun_and_keyless_local_config():
    old = {**config.DEFAULT_SETTINGS, "stepfun_api_key": "test"}
    assert not config.is_llm_configured(old)
    assert rewrite.text_config({**old, "llm_provider": "stepfun"})[0] == rewrite.TEXT_API_URL
    url, model, key = rewrite.text_config({
        **config.DEFAULT_SETTINGS, "llm_provider": "custom", "llm_base_url": "http://localhost/v1",
        "llm_model": "example", "stepfun_api_key": "test",
    })
    assert (url, model, key) == ("http://localhost/v1/chat/completions", "example", "")


def test_bundle_keeps_valid_texts_when_material_needs_independent_retry(monkeypatch):
    texts = {"natural_english": "It helps me unwind.",
             "podcast_text": "A: Why do you swim?\nB: It helps me unwind.",
             "podcast_script": "A: Why do you swim?\nB: It helps me unwind."}
    invalid = {**texts, "study_material": {"complete_chinese": "我放松了。", "sentences": []}}
    monkeypatch.setattr(rewrite, "_chat", lambda *_: json.dumps(invalid))
    result = rewrite.generate_complete_bundle({}, "Why do you swim?", "I can relax.")
    assert result == {**rewrite.normalize_dialogue_payload(texts, "Why do you swim?"),
                      "study_material": None}


def test_portable_audit_rejects_key_in_example_without_printing_it(monkeypatch, tmp_path, capsys):
    example = tmp_path / "data" / "settings.example.json"
    example.parent.mkdir()
    example.write_text('{"llm_api_key":"synthetic-test-key"}', encoding="utf-8")
    monkeypatch.setattr(package, "BASE", tmp_path)
    monkeypatch.setattr(package, "OUT", tmp_path / "portable.zip")
    assert package.main() == 1
    assert not package.OUT.exists()
    output = capsys.readouterr()
    assert "synthetic-test-key" not in output.out + output.err
