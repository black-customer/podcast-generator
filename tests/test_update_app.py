"""update_app.bat 端口清理的身份校验：只结束本项目的服务进程，不误杀无关软件。

测试直接从 bat 文件解析真实的 PowerShell 命令执行（仅把端口字面量换成测试端口），
保证脚本与测试不漂移。
"""
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(platform.system() != "Windows",
                                reason="update_app.bat 与 PowerShell 清理逻辑仅 Windows")

BAT = Path(__file__).resolve().parent.parent / "update_app.bat"
TEST_PORT = 8787


def _port_cleanup_command() -> str:
    text = BAT.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'powershell -NoProfile.*?-Command "(.+)"', text)
    assert match, "update_app.bat 应包含单行 powershell 端口清理命令"
    return match.group(1).replace("8765", str(TEST_PORT))


def _spawn(args: list[str]) -> subprocess.Popen:
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 10
    import socket

    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", TEST_PORT), timeout=0.5):
                return proc
        except OSError:
            if proc.poll() is not None:
                raise AssertionError(f"进程提前退出: {args}") from None
            time.sleep(0.2)
    raise AssertionError(f"进程未在端口上监听: {args}")


@pytest.mark.parametrize(
    "args",
    [
        # 无关程序：本项目 venv 的 python，但命令行不含 run.py / uvicorn
        [sys.executable, "-m", "http.server", str(TEST_PORT)],
    ],
)
def test_foreign_process_on_port_is_not_killed(args):
    proc = _spawn(args)
    try:
        run = subprocess.run(
            ["powershell", "-NoProfile", "-Command", _port_cleanup_command()],
            capture_output=True, timeout=30,
        )
        assert proc.poll() is None, "无关进程被误杀"
        assert run.returncode == 2, f"应以外码 2 提示占用者非本应用，实际 {run.returncode}"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_own_server_on_port_is_killed():
    proc = _spawn([sys.executable, "-m", "uvicorn", "server.main:app",
                   "--host", "127.0.0.1", "--port", str(TEST_PORT)])
    try:
        run = subprocess.run(
            ["powershell", "-NoProfile", "-Command", _port_cleanup_command()],
            capture_output=True, timeout=30,
        )
        out = (run.stdout or b"").decode("utf-8", "replace")
        err = (run.stderr or b"").decode("utf-8", "replace")
        assert run.returncode == 0, out + err
        deadline = time.time() + 10
        while proc.poll() is None and time.time() < deadline:
            time.sleep(0.2)
        assert proc.poll() is not None, "本项目服务进程应被结束"
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
