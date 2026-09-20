"""R05 只读环境诊断：python / ffmpeg / 依赖 / 配置 / 题库 / 服务状态。

供陌生用户或其 Agent 一条命令定位安装问题：
  .venv/Scripts/python scripts/doctor.py
规则：只读（不写任何文件、不改配置）；绝不输出任何 API Key 明文。
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

OK, WARN, FAIL = "OK", "WARN", "FAIL"


def _check_ffmpeg() -> tuple[str, str, str]:
    try:
        r = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0:
            return OK, "ffmpeg 可用", (r.stdout or "").splitlines()[0][:80]
        return FAIL, "ffmpeg 返回异常", "重新安装 ffmpeg 并加入 PATH"
    except FileNotFoundError:
        return (
            FAIL,
            "未找到 ffmpeg（音频合成必需）",
            "安装 ffmpeg 并加入 PATH：winget install Gyan.FFmpeg"
            "（或从 ffmpeg.org 下载）",
        )
    except Exception as e:  # noqa: BLE001
        return WARN, f"ffmpeg 检测失败: {e}", "重试或手动运行 ffmpeg -version"


def _check_port(port: int) -> tuple[str, str, str]:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        busy = s.connect_ex(("127.0.0.1", port)) == 0
    if busy:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=3) as r:
                body = json.loads(r.read().decode("utf-8"))
            return (
                WARN,
                f"端口 {port} 已有 IELTS Pod 服务在运行 (v{body.get('version', '?')})",
                "直接打开网页即可；重启请先停掉旧进程",
            )
        except Exception:
            return (
                FAIL,
                f"端口 {port} 被其他程序占用",
                "结束占用进程，或用 --port 换一个端口启动",
            )
    return OK, f"端口 {port} 空闲", ""


def collect() -> list[dict]:
    """汇总诊断项：{level, name, detail, hint}。只读，绝不包含密钥明文。"""
    from server import bank, library, production
    from server.config import load_settings, real_api_key, real_stepfun_api_key

    results: list[dict] = []

    v = sys.version_info
    results.append({
        "level": OK if v >= (3, 11) else FAIL,
        "name": "Python",
        "detail": f"{v.major}.{v.minor}.{v.micro}",
        "hint": "" if v >= (3, 11) else "需要 Python 3.11+：winget install Python.Python.3.11",
    })

    level, detail, hint = _check_ffmpeg()
    results.append({"level": level, "name": "ffmpeg", "detail": detail, "hint": hint})

    for mod in ("fastapi", "uvicorn", "httpx"):
        try:
            __import__(mod)
            results.append({"level": OK, "name": f"依赖 {mod}", "detail": "已安装", "hint": ""})
        except ImportError:
            results.append({
                "level": FAIL,
                "name": f"依赖 {mod}",
                "detail": "未安装",
                "hint": "在项目目录运行: .venv\\Scripts\\pip install -r requirements.txt",
            })

    settings = load_settings()
    provider = settings.get("tts_provider") or "stepfun"
    step_set = bool(real_stepfun_api_key(settings))
    fish_set = bool(real_api_key(settings))
    results.append({
        "level": OK if (step_set or fish_set) else WARN,
        "name": "语音引擎配置",
        "detail": (
            f"当前 provider={provider}；StepFun Key {'已配置' if step_set else '未配置'}；"
            f"Fish Key {'已配置' if fish_set else '未配置'}"
            + ("；dry-run 模式" if settings.get("dry_run") else "")
        ),
        "hint": (
            "" if (step_set or fish_set)
            else "在网页「设置」粘贴 StepFun API Key，或先用 dry-run 体验"
        ),
    })
    keys_check = (
        ("STEPFUN", real_stepfun_api_key(settings)),
        ("FISH", real_api_key(settings)),
    )
    for name, key in keys_check:
        if key:
            results.append({
                "level": OK,
                "name": f"{name} Key 脱敏校验",
                "detail": f"已配置（{key[:3]}***，共 {len(key)} 字符，诊断不输出明文）",
                "hint": "",
            })

    voices = production.get_voice_catalog()
    by_provider: dict[str, int] = {}
    for voice in voices:
        prov = voice.get("provider") or "fish"
        by_provider[prov] = by_provider.get(prov, 0) + 1
    results.append({
        "level": OK if voices else WARN,
        "name": "音色库",
        "detail": " / ".join(f"{k} {v} 个" for k, v in sorted(by_provider.items())) or "空",
        "hint": "" if voices else "data/voices.json 缺失或损坏",
    })

    try:
        snapshot = bank.load_bank()
        results.append({
            "level": OK,
            "name": "题库",
            "detail": (
                f"{len(snapshot.get('questions', []))} 题 / "
                f"{len(snapshot.get('topics', []))} 话题"
            ),
            "hint": "",
        })
    except FileNotFoundError:
        results.append({
            "level": WARN,
            "name": "题库",
            "detail": "使用公开题库回退或未导入",
            "hint": "完整题库：python -m server.bank --sync",
        })

    topics_dir = library.TOPICS_DIR
    results.append({
        "level": OK if topics_dir.exists() else WARN,
        "name": "语料目录",
        "detail": str(topics_dir),
        "hint": "" if topics_dir.exists() else "首次生成音频时自动创建",
    })

    level, detail, hint = _check_port(8765)
    results.append({"level": level, "name": "服务端口 8765", "detail": detail, "hint": hint})
    return results


def main() -> int:
    print("IELTS Pod 环境诊断（只读，不输出密钥）\n" + "=" * 46)
    failed = 0
    for item in collect():
        mark = {"OK": "✓", "WARN": "!", "FAIL": "✗"}[item["level"]]
        print(f"[{mark}] {item['name']}: {item['detail']}")
        if item["hint"]:
            print(f"    → {item['hint']}")
        if item["level"] == FAIL:
            failed += 1
    print("=" * 46)
    verdict = "存在待修复项，按 ↑ 提示处理即可" if failed else "环境就绪，可以开始练习"
    print("诊断结论：" + verdict)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
