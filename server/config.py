"""路径常量与 settings.json 读写。"""
import json
import os
import shutil
import threading
import time
from pathlib import Path
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
PROMPTS_DIR = BASE_DIR / "prompts"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TOPICS_DIR = DATA_DIR / "topics"
EPISODES_DIR = DATA_DIR / "episodes"
TMP_DIR = DATA_DIR / ".tmp"


def _read_version() -> str:
    try:
        return (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip() or "dev"
    except OSError:
        return "dev"


APP_VERSION = _read_version()

SETTINGS_FILE = DATA_DIR / "settings.json"

SETTINGS_LOCK = threading.Lock()


def atomic_write_text(path: Path, content: str) -> None:
    """原子写：先写临时文件再 os.replace，进程崩溃不留半截文件。

    适用于所有元数据/缓存 JSON 与语料 txt（data/ 是产品本体）。
    tmp 名带 uuid：业务锁之外的并发写（timeline/试听缓存）互不踩踏；
    replace 带有界重试：Windows 上目标文件被并发读者短暂占用时不失败。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{uuid4().hex}.tmp~")
    try:
        tmp.write_text(content, encoding="utf-8")
        for attempt in range(5):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.02 * (attempt + 1))
    finally:
        tmp.unlink(missing_ok=True)

DEFAULT_SETTINGS = {
    "tts_provider": "kokoro_local",
    "speech_engine_dir": "D:/project/ChineseAccent",
    "kokoro_question_voice": "af_bella",
    "kokoro_answer_voice": "am_puck",
    "llm_provider": "deepseek",
    "llm_base_url": "https://api.deepseek.com/v1",
    "llm_api_key": "",
    "llm_model": "deepseek-flash",
    "vision_base_url": "",
    "vision_model": "",
    "vision_api_key": "",
    "daily_session_limit": 8,
    "reaction_timer_enabled": False,
    "scene_sync_token": "",
    "episode_gap_ms": 600,  # 剧集中条目之间的停顿
    "dry_run": False,
}


def ensure_dirs() -> None:
    for d in (DATA_DIR, TOPICS_DIR, EPISODES_DIR, TMP_DIR):
        d.mkdir(parents=True, exist_ok=True)


def cleanup_stale_tmp(max_age_hours: float = 24) -> None:
    """清理异常退出遗留的临时工作产物（silence-*.mp3 是缓存，保留）。"""
    if not TMP_DIR.exists():
        return
    cutoff = time.time() - max_age_hours * 3600
    for p in TMP_DIR.iterdir():
        try:
            if p.name.startswith("silence-") or p.name == "voice_previews":
                continue
            if p.stat().st_mtime > cutoff:
                continue
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
        except OSError:
            continue


def load_settings() -> dict:
    with SETTINGS_LOCK:
        settings = dict(DEFAULT_SETTINGS)
        stored: dict = {}
        if SETTINGS_FILE.exists():
            try:
                stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    settings.update({k: v for k, v in stored.items() if k in settings})
                    settings["llm_api_key"] = real_llm_api_key(stored)
            except (json.JSONDecodeError, OSError):
                pass
        elif (DATA_DIR / "settings.example.json").exists():
            try:
                example = DATA_DIR / "settings.example.json"
                stored = json.loads(example.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    settings.update({k: v for k, v in stored.items() if k in settings})
            except (json.JSONDecodeError, OSError):
                pass

        return _normalize_settings(settings)


def _normalize_settings(settings: dict) -> dict:
    settings["tts_provider"] = "kokoro_local"
    if settings.get("llm_provider") not in {"deepseek", "custom"}:
        settings.update({key: DEFAULT_SETTINGS[key] for key in (
            "llm_provider", "llm_base_url", "llm_model",
        )})
    if settings["daily_session_limit"] not in (5, 8, 12, 20):
        settings["daily_session_limit"] = 8
    return settings


def save_settings(update: dict) -> dict:
    with SETTINGS_LOCK:
        current = dict(DEFAULT_SETTINGS)
        if SETTINGS_FILE.exists():
            try:
                stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    current.update({k: v for k, v in stored.items() if k in settings_keys()})
                    current["llm_api_key"] = real_llm_api_key(stored)
            except (json.JSONDecodeError, OSError):
                pass
        for k, v in update.items():
            if k in current:
                current[k] = v
        _normalize_settings(current)
        atomic_write_text(SETTINGS_FILE, json.dumps(current, ensure_ascii=False, indent=2))
        return current


def settings_keys():
    return DEFAULT_SETTINGS.keys()


# 占位符 key（settings.example.json 复制后未替换的情况）一律视为未配置
_PLACEHOLDER_KEYS = {
    "",
    "your_deepseek_api_key_here",
    "your_llm_api_key_here",
}


def _real_key(value: object) -> str:
    key = str(value or "").strip()
    return "" if key.lower() in _PLACEHOLDER_KEYS else key


def real_llm_api_key(settings: dict | None = None) -> str:
    s = settings or {}
    return _real_key(s.get("llm_api_key")) or _real_key(s.get("deepseek_api_key"))


def is_llm_configured(settings: dict) -> bool:
    from .rewrite import text_available

    return text_available(settings)


def speech_python(settings: dict) -> Path:
    root = Path(str(settings.get("speech_engine_dir", DEFAULT_SETTINGS["speech_engine_dir"])))
    return root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def speech_engine_available(settings: dict) -> bool:
    root = Path(str(settings.get("speech_engine_dir", DEFAULT_SETTINGS["speech_engine_dir"])))
    return (root / "backend" / "engine" / "audio_io.py").is_file() and speech_python(
        settings
    ).is_file()


def effective_tts_provider(settings: dict) -> str:
    return "kokoro_local"


def is_dry_run(settings: dict | None = None) -> bool:
    s = settings if settings is not None else load_settings()
    return bool(s.get("dry_run")) or not speech_engine_available(s)
