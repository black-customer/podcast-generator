#!/usr/bin/env python
"""R05/M19：一键打包 Windows 可移植 zip（不含密钥/个人语料/试听缓存/生成音频）。

用法：.venv/Scripts/python scripts/package.py
输出：dist/ielts-pod-portable.zip
打包完成后自动审计：zip 内绝不出现 settings.json、个人语料、voice_samples、.tmp、
question_bank.json（私有快照）、任何 audio 文件。
"""
import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "dist" / "ielts-pod-portable.zip"

INCLUDE_DIRS = [
    "server", "web", "prompts", "docs", "scripts", "tests", "mobile", "skills", ".qoder",
]
INCLUDE_FILES = [
    "README.md", "AGENTS.md", "requirements.txt", "requirements-dev.txt",
    "run.py", "pipeline.py", "start.bat", "open_app.bat", "update_app.bat",
    "app.ico", "VERSION", "pyproject.toml", ".gitignore",
]
INCLUDE_DATA = [
    "data/voices.json",
    "data/settings.example.json",
    "data/question_bank_public.json",
]

EXCLUDE_PARTS = {
    "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", "www", "build", ".gradle",
}

# 前缀排除：docs/design/ 是给开发会话的概念图与提示词交接物（约 40MB），不进便携包
EXCLUDE_PREFIXES = ("docs/design/",)

# 审计：zip 内任何路径命中这些规则即为打包事故
FORBIDDEN_PARTS = {
    "settings.json", "voice_samples", ".tmp", "episodes", "topics",
    "question_bank.json", "question_bank_extra.json", "jobs.json", "exports",
    "study_private", "backups",
    "keystore.properties", "debug.keystore", "release.keystore",
}
# 任何媒体/签名产物后缀都不得入便携包
FORBIDDEN_SUFFIXES = (
    ".mp3", ".m4b", ".wav", ".apk", ".m4a", ".flac", ".ogg", ".opus", ".aac",
    ".wma", ".keystore", ".jks",
)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    count = 0
    violations: list[str] = []
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in INCLUDE_DIRS:
            src = BASE / d
            if not src.exists():
                continue
            for f in sorted(src.rglob("*")):
                if not f.is_file():
                    continue
                rel = f.relative_to(BASE)
                if any(part in EXCLUDE_PARTS for part in rel.parts):
                    continue
                if rel.as_posix().startswith(EXCLUDE_PREFIXES):
                    continue
                zf.write(f, rel)
                count += 1
        for name in INCLUDE_FILES + INCLUDE_DATA:
            f = BASE / name
            if f.exists():
                zf.write(f, name)
                count += 1

        # 审计（打包事故 = 泄漏）：逐条检查 zip 内路径
        for info in zf.infolist():
            parts = set(Path(info.filename).parts)
            hit = parts & FORBIDDEN_PARTS
            if hit:
                violations.append(f"{info.filename}（命中 {hit}）")
            if info.filename.endswith(FORBIDDEN_SUFFIXES):
                violations.append(f"{info.filename}（音频/签名产物不应入包）")

    if violations:
        print("审计失败：分享包包含禁止内容！", file=sys.stderr)
        for v in violations[:20]:
            print(f"  ✗ {v}", file=sys.stderr)
        OUT.unlink()
        return 1

    print(f"打包完成: {OUT} ({OUT.stat().st_size // 1024} KB, {count} 个文件)")
    print("审计通过：无 settings.json / 个人语料 / 试听缓存 / .tmp / 音频文件")
    print("接收方：解压 → 双击 start.bat（自动建 venv 装依赖并启动）→ 浏览器自动打开")
    return 0


if __name__ == "__main__":
    sys.exit(main())
