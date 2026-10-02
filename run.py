"""启动本地服务：python run.py [--no-open] [--port N] [--host H]

默认绑定 127.0.0.1（本机访问）。手机经局域网导入语料包等场景用 --host 0.0.0.0。
启动前做前置检查：端口占用直接报错（绝不静默连到旧服务），ffmpeg 缺失给出安装提示。
"""
import json
import os
import secrets
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn

PORT = 8765


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((host if host != "0.0.0.0" else "127.0.0.1", port)) == 0


def _check_ffmpeg() -> bool:
    import subprocess

    try:
        return subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, timeout=15
        ).returncode == 0
    except Exception:
        return False


def _wait_for_ready(host: str, port: int, stopped: threading.Event) -> bool:
    """仅在本次服务运行期间等待健康响应，退出后不打开失效页面。"""
    address = "127.0.0.1" if host == "0.0.0.0" else host
    deadline = time.monotonic() + 30
    while not stopped.is_set() and time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://{address}:{port}/api/health", timeout=1) as res:
                body = json.loads(res.read())
                if res.status == 200 and "version" in body and "ffmpeg" in body:
                    return not stopped.is_set()
        except (OSError, ValueError):
            pass
        stopped.wait(0.2)
    return False


def main() -> None:
    port = PORT
    host = "127.0.0.1"
    try:
        if "--port" in sys.argv:
            port = int(sys.argv[sys.argv.index("--port") + 1])
        if not 1 <= port <= 65535:
            raise ValueError("port range")
        if "--host" in sys.argv:
            host = sys.argv[sys.argv.index("--host") + 1]
            if host.startswith("--"):
                raise ValueError("host missing")
    except (ValueError, IndexError):
        print("[参数错误] --port 需要 1–65535 的整数；--host 后需要地址。", file=sys.stderr)
        print("  示例：python run.py --port 8766 --no-open", file=sys.stderr)
        sys.exit(2)
    open_browser = "--no-open" not in sys.argv
    reload = "--reload" in sys.argv

    if _port_in_use(host, port):
        print(f"[启动失败] 端口 {port} 已被占用。", file=sys.stderr)
        print(f"  → 如果 IELTS Pod 已在运行，直接打开 http://127.0.0.1:{port} 即可。",
              file=sys.stderr)
        print(f"  → 否则结束占用该端口的程序，或换个端口启动：python run.py --port {port + 1}",
              file=sys.stderr)
        sys.exit(1)
    if not _check_ffmpeg():
        print("[警告] 未找到 ffmpeg：服务可以启动，但音频生成会失败。", file=sys.stderr)
        print("  → 安装后重开终端：winget install Gyan.FFmpeg"
              "（或从 ffmpeg.org 下载并加入 PATH）", file=sys.stderr)

    if host not in ("127.0.0.1", "localhost", "::1"):
        token = secrets.token_urlsafe(12)
        os.environ["IELTS_POD_LAN_TOKEN"] = token
        print(f"局域网语料包配对码: {token}")
        print("手机 APP 导入页填写电脑地址和此配对码；服务重启后配对码会更新。")

    stopped = threading.Event()
    def open_when_ready() -> None:
        if _wait_for_ready(host, port, stopped):
            webbrowser.open(f"http://127.0.0.1:{port}")
        elif not stopped.is_set():
            print("[启动等待超时] 请查看服务错误，或运行 scripts/doctor.py 排查。", file=sys.stderr)

    if open_browser:
        threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        uvicorn.run("server.main:app", host=host, port=port, log_level="info", reload=reload)
    finally:
        stopped.set()


if __name__ == "__main__":
    main()
