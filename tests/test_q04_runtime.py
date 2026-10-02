"""Q04：启动就绪、更新失败中止与汇总读取的回归。"""
import sys
from pathlib import Path

import pytest

import run
from server import oral_review, study
from tests.test_oral_review import add_sentence, env  # noqa: F401


def test_today_reads_each_material_once(env, monkeypatch):  # noqa: F811
    add_sentence(env, 1, legacy=True)
    original = study.get_material
    calls = []

    def counted(tid, iid):
        calls.append((tid, iid))
        return original(tid, iid)

    monkeypatch.setattr(study, "get_material", counted)
    assert oral_review.today_overview()["due_count"] == 1
    assert len(calls) == len(set(calls)) == 1
    calls.clear()
    assert oral_review.today_overview()["due_count"] == 1
    assert len(calls) == 1, "不能跨请求缓存材料"


def test_browser_opens_only_after_service_ready(monkeypatch):
    events = []
    monkeypatch.setattr(run, "_port_in_use", lambda *_: False)
    monkeypatch.setattr(run, "_check_ffmpeg", lambda: True)
    monkeypatch.setattr(sys, "argv", ["run.py"])

    def wait(host, port, stopped):
        events.append("ready")
        assert not stopped.is_set()
        return True

    monkeypatch.setattr(run, "_wait_for_ready", wait, raising=False)
    monkeypatch.setattr(run.webbrowser, "open", lambda *_: events.append("open"))

    def server(*_, **__):
        import time
        for _ in range(100):
            if "open" in events:
                break
            time.sleep(0.01)

    monkeypatch.setattr(run.uvicorn, "run", server)
    run.main()
    assert events == ["ready", "open"]


def test_update_stops_when_dependencies_fail():
    source = Path("update_app.bat").read_text(encoding="utf-8")
    after_install = source.split("-m pip install", 1)[1].split("[3/4]", 1)[0]
    assert "if errorlevel 1" in after_install
    assert "exit /b 1" in after_install


@pytest.mark.parametrize("args", [["--port"], ["--port", "abc"], ["--port", "70000"]])
def test_invalid_start_arguments_are_actionable(args, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run.py", *args])
    with pytest.raises(SystemExit) as error:
        run.main()
    assert error.value.code == 2
    assert "--port" in capsys.readouterr().err
