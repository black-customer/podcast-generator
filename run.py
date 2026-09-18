"""启动本地服务：python run.py [--no-open]"""
import sys
import threading
import webbrowser

import uvicorn

PORT = 8765


def main() -> None:
    open_browser = "--no-open" not in sys.argv
    # 默认关闭热重载（日常生成场景无需 watch）；开发时加 --reload 开启
    reload = "--reload" in sys.argv
    if open_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    uvicorn.run("server.main:app", host="127.0.0.1", port=PORT, log_level="info", reload=reload)


if __name__ == "__main__":
    main()
