"""路径常量与 settings.json 读写。"""
import json
import os
import shutil
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
PROMPTS_DIR = BASE_DIR / "prompts"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TOPICS_DIR = DATA_DIR / "topics"
EPISODES_DIR = DATA_DIR / "episodes"
TMP_DIR = DATA_DIR / ".tmp"

SETTINGS_FILE = DATA_DIR / "settings.json"

SETTINGS_LOCK = threading.Lock()


def atomic_write_text(path: Path, content: str) -> None:
    """原子写：先写临时文件再 os.replace，进程崩溃不留半截文件。

    适用于所有元数据/缓存 JSON 与语料 txt（data/ 是产品本体）。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp~")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)

DEFAULT_SETTINGS = {
    "fish_api_key": "",
    "reference_id": "",     # 音色 A（独白用这一个；对话中扮演 A）
    "reference_id_b": "",   # 音色 B（可选：对话中扮演 B，留空则按单音色处理）
    "model": "s2.1-pro-free",
    "speed": 1.0,
    "segment_chars": 700,
    "gap_ms": 350,          # 条目内部段落之间的停顿
    "episode_gap_ms": 600,  # 剧集中条目之间的停顿
    "dry_run": False,       # 手动强制 dry-run；fish_api_key 为空时也会自动 dry-run
    "temperature": None,    # 表现力 0-1（None = 服务默认）；调高更生动多变，调低更稳定
}

# Fish Audio 开放模型头
FISH_MODELS = ["s2.1-pro-free", "s2.1-pro", "s2-pro", "s1"]
FISH_TTS_URL = "https://api.fish.audio/v1/tts"
FISH_MODELS_URL = "https://api.fish.audio/model"


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
            if p.name.startswith("silence-"):
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
        if SETTINGS_FILE.exists():
            try:
                stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    settings.update({k: v for k, v in stored.items() if k in settings})
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
        return settings


def save_settings(update: dict) -> dict:
    with SETTINGS_LOCK:
        current = dict(DEFAULT_SETTINGS)
        if SETTINGS_FILE.exists():
            try:
                stored = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    current.update({k: v for k, v in stored.items() if k in settings_keys()})
            except (json.JSONDecodeError, OSError):
                pass
        for k, v in update.items():
            if k in current:
                current[k] = v
        atomic_write_text(SETTINGS_FILE, json.dumps(current, ensure_ascii=False, indent=2))
        return current


def settings_keys():
    return DEFAULT_SETTINGS.keys()


# 占位符 key（settings.example.json 复制后未替换的情况）一律视为未配置
_PLACEHOLDER_KEYS = {"", "your_fish_api_key_here", "your-fish-api-key"}


def real_api_key(settings: dict | None = None) -> str:
    key = ((settings or {}).get("fish_api_key") or "").strip()
    return "" if key.lower() in _PLACEHOLDER_KEYS else key


def is_dry_run(settings: dict | None = None) -> bool:
    s = settings or load_settings()
    return bool(s.get("dry_run")) or not real_api_key(s)
