"""以串行 JSON Lines 请求复用外部语音环境，闲置时释放模型。"""

import atexit
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

from . import config

VOICES = {"af_bella": "Bella", "am_liam": "Liam", "am_michael": "Michael",
          "am_puck": "Puck", "golden_self": "我的母语分身"}


class SpeechError(RuntimeError):
    pass


class SpeechCancelled(SpeechError):
    pass


class SpeechBridge:
    def __init__(self, command: list[str], cwd: Path, idle_seconds: float = 300):
        self.command = command
        self.cwd = cwd
        self.idle_seconds = idle_seconds
        self.lock = threading.RLock()
        self.process: subprocess.Popen | None = None
        self.idle: threading.Timer | None = None
        self.request_id = 0

    def _start(self) -> None:
        self.responses: queue.Queue = queue.Queue()
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
        env.setdefault("NUMBA_CACHE_DIR", str(config.TMP_DIR / "speech-numba"))
        self.process = subprocess.Popen(
            self.command, cwd=self.cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, encoding="utf-8", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=env,
        )
        threading.Thread(target=self._read, args=(self.process.stdout, self.responses),
                         daemon=True).start()

    @staticmethod
    def _read(stream, responses: queue.Queue) -> None:
        try:
            for line in stream:
                responses.put(json.loads(line))
        except (OSError, ValueError):
            pass
        finally:
            stream.close()
            responses.put(None)

    def close(self) -> None:
        with self.lock:
            if self.idle:
                self.idle.cancel()
                self.idle = None
            if self.process:
                process, self.process = self.process, None
                if process.poll() is None:
                    process.kill()
                process.wait()
                process.stdin.close()

    def _expire(self, request_id: int) -> None:
        with self.lock:
            if self.request_id == request_id:
                self.close()

    def call(self, method: str, *, timeout: float = 180,
             cancel: threading.Event | None = None, **params) -> dict:
        with self.lock:
            if cancel and cancel.is_set():
                raise SpeechCancelled("已取消")
            if self.idle:
                self.idle.cancel()
            self.request_id += 1
            request_id = self.request_id
            try:
                if not self.process or self.process.poll() is not None:
                    self.close()
                    self._start()
                message = {"id": request_id, "method": method, "params": params}
                self.process.stdin.write(json.dumps(message, default=os.fspath) + "\n")
                self.process.stdin.flush()
                deadline = time.monotonic() + timeout
                while True:
                    if cancel and cancel.is_set():
                        raise SpeechCancelled("已取消")
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise SpeechError("本地语音引擎请求超时，可以重试")
                    try:
                        response = self.responses.get(timeout=min(0.2, remaining))
                        break
                    except queue.Empty:
                        continue
                if not isinstance(response, dict) or response.get("id") != request_id:
                    raise SpeechError("本地语音引擎已断开，可以重试")
            except OSError as exc:
                self.close()
                raise SpeechError("无法启动或连接本地语音引擎") from exc
            except SpeechError:
                self.close()
                raise
            self.idle = threading.Timer(self.idle_seconds, self._expire, args=(request_id,))
            self.idle.daemon = True
            self.idle.start()
            if "error" in response:
                raise SpeechError(str(response["error"]))
            return response["result"]


_guard = threading.Lock()
_bridges: dict[Path, SpeechBridge] = {}


@atexit.register
def close_workers() -> None:
    with _guard:
        for bridge in _bridges.values():
            bridge.close()


def request(settings: dict, method: str, **params) -> dict:
    if not config.speech_engine_available(settings):
        raise SpeechError("找不到 ChineseAccent 语音环境，请在设置中检查目录")
    python = config.speech_python(settings).absolute()
    with _guard:
        if python not in _bridges:
            worker = Path(__file__).with_name("speech_worker.py").resolve()
            _bridges[python] = SpeechBridge([str(python), "-u", str(worker)], python.parents[2])
        bridge = _bridges[python]
    return bridge.call(method, **params)


def status(settings: dict) -> dict:
    try:
        return {"available": True, **request(settings, "status", timeout=15)}
    except SpeechError as exc:
        return {"available": False, "reason": str(exc), "profile": None}
