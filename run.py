"""启动本地服务：python run.py [--no-open] [--port N] [--host H]

默认绑定 127.0.0.1（本机访问）。手机经局域网导入语料包等场景用 --host 0.0.0.0。
"""
import sys
import threading
import webbrowser

import uvicorn

PORT = 8765


def main() -> None:
    port = PORT
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    host = "127.0.0.1"
    if "--host" in sys.argv:
        host = sys.argv[sys.argv.index("--host") + 1]
    open_browser = "--no-open" not in sys.argv
    reload = "--reload" in sys.argv
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{port}")).start()
    uvicorn.run("server.main:app", host=host, port=port, log_level="info", reload=reload)


if __name__ == "__main__":
    main()
