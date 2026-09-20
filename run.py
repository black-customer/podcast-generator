"""启动本地服务：python run.py [--no-open] [--port N] [--host H]

默认绑定 127.0.0.1（本机访问）。手机经局域网导入语料包等场景用 --host 0.0.0.0。
启动前做前置检查：端口占用直接报错（绝不静默连到旧服务），ffmpeg 缺失给出安装提示。
"""
import socket
import sys
import threading
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


def main() -> None:
    port = PORT
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    host = "127.0.0.1"
    if "--host" in sys.argv:
        host = sys.argv[sys.argv.index("--host") + 1]
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

    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run("server.main:app", host=host, port=port, log_level="info", reload=reload)


if __name__ == "__main__":
    main()
