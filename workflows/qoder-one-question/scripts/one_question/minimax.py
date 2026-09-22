"""Minimax H3 本地服务适配器（图生视频，用于封面动态开场）。

按官方异步任务接口实现：提交 → 轮询 → 用 file_id 换取下载地址。
配置只从环境变量读，绝不写进任何文件：
    MINIMAX_BASE_URL   例如 http://127.0.0.1:8000
    MINIMAX_API_KEY    可选，本地服务常留空
服务不可达、超时或返回异常时一律返回 None，让出片流程继续——
静态封面永远比没有封面强。
"""
from __future__ import annotations

import base64
import json
import os
import socket
import time
import urllib.request
from pathlib import Path

CREATE_PATH = "/v1/video_generation"
QUERY_PATH = "/v1/query/video_generation"
FILE_PATH = "/v1/files/retrieve"
TERMINAL_FAIL = {"Fail", "Failed", "Error"}


def available() -> bool:
    """只回答一件事：那个地址上有没有东西在听。"""
    base = os.environ.get("MINIMAX_BASE_URL", "").strip()
    if not base:
        return False
    host = base.split("://", 1)[-1].rstrip("/").split("/", 1)[0]
    if ":" in host:
        hostname, _, port_s = host.partition(":")
        port = int(port_s or 443)
    else:
        hostname, port = host, 443
    try:
        with socket.create_connection((hostname, port), timeout=3):
            return True
    except OSError:
        return False


def _req(url: str, payload: dict | None = None, timeout: float = 30.0) -> dict:
    base = os.environ.get("MINIMAX_BASE_URL", "").rstrip("/")
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    method = "POST" if data else "GET"
    req = urllib.request.Request(base + url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace") or "{}")


def image_to_video(image: Path, prompt: str, out: Path, *, duration: int = 5,
                   ratio: str = "9:16", poll_seconds: float = 240.0) -> Path | None:
    """把一张静态封面变成几秒有呼吸感的开场。失败返回 None，不抛异常。"""
    try:
        b64 = base64.b64encode(image.read_bytes()).decode()
        created = _req(CREATE_PATH, {
            "model": os.environ.get("MINIMAX_MODEL", "MiniMax-H3"),
            "prompt": prompt, "duration": duration, "ratio": ratio,
            "first_frame_image": f"data:image/png;base64,{b64}",
            "prompt_optimizer": True,
        })
        task_id = (created.get("task_id") or created.get("data", {}).get("task_id") or "").strip()
        if not task_id:
            return None
        deadline = time.monotonic() + poll_seconds
        file_id = ""
        while time.monotonic() < deadline:
            state = _req(f"{QUERY_PATH}?task_id={task_id}")
            status = str(state.get("status") or state.get("base_resp", {}).get("status_code", ""))
            if status in TERMINAL_FAIL:
                return None
            if status in ("Success", "Succeed") or state.get("file_id"):
                file_id = state.get("file_id") or ""
                break
            time.sleep(5)
        if not file_id:
            return None
        meta = _req(f"{FILE_PATH}?file_id={file_id}")
        url = meta.get("files", [{}])[0].get("download_url") or meta.get("download_url") or ""
        if not url:
            return None
        with urllib.request.urlopen(url, timeout=180) as r:
            out.write_bytes(r.read())
        return out if out.stat().st_size > 50_000 else None
    except Exception:  # noqa: BLE001  适配器永远不让主流程崩
        return None
