"""R05 诊断命令回归：只读、结构化、密钥零明文。"""
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    topics = tmp_path / "topics"
    topics.mkdir()
    from server import config, library
    monkeypatch.setattr(library, "TOPICS_DIR", topics)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    config.atomic_write_text(
        config.SETTINGS_FILE,
        '{"tts_provider":"stepfun","stepfun_api_key":"sk-secret-doctor-KEY-9281"}',
    )
    return tmp_path


def test_doctor_collect_is_readonly_and_masks_keys(isolated):
    from scripts.doctor import collect

    before = sorted(p.name for p in isolated.iterdir())
    items = collect()
    after = sorted(p.name for p in isolated.iterdir())
    assert before == after, "诊断不得写任何文件"

    blob = repr(items)
    assert "sk-secret-doctor-KEY-9281" not in blob, "诊断绝不能输出密钥明文"
    assert any("已配置" in i["detail"] for i in items if "Key" in i["name"] or "引擎" in i["name"])

    names = {i["name"] for i in items}
    assert {"Python", "ffmpeg", "语音引擎配置", "题库", "服务端口 8765"} <= names
    for i in items:
        assert i["level"] in ("OK", "WARN", "FAIL")
        assert isinstance(i["hint"], str)


def test_doctor_main_exit_code_reflects_failures(isolated, monkeypatch, capsys):
    import scripts.doctor as doctor

    monkeypatch.setattr(
        doctor, "collect",
        lambda: [
            {"level": "OK", "name": "A", "detail": "ok", "hint": ""},
            {"level": "FAIL", "name": "B", "detail": "bad", "hint": "do this"},
        ],
    )
    assert doctor.main() == 1
    out = capsys.readouterr().out
    assert "do this" in out and "B" in out

    monkeypatch.setattr(
        doctor, "collect",
        lambda: [{"level": "OK", "name": "A", "detail": "ok", "hint": ""}],
    )
    assert doctor.main() == 0
