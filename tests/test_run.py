"""Windows 启动前置检查在默认 GBK 控制台也必须可读、可退出。"""
import sys

import pytest

import run


def test_port_conflict_message_is_gbk_safe(monkeypatch, capsys):
    monkeypatch.setattr(run, "_port_in_use", lambda _host, _port: True)
    monkeypatch.setattr(sys, "argv", ["run.py", "--no-open"])
    with pytest.raises(SystemExit) as exc:
        run.main()
    assert exc.value.code == 1
    output = capsys.readouterr().err
    assert "8765" in output and "已被占用" in output
    output.encode("gbk")
