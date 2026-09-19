#!/usr/bin/env python
"""M19：一键打包可分享的 zip（不含密钥/个人语料/大文件）。

用法：.venv/Scripts/python scripts/package.py
输出：dist/bruce-corpus-share.zip
"""
import sys
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "dist" / "bruce-corpus-share.zip"

INCLUDE_DIRS = ["server", "web", "prompts", "docs", "scripts", "tests", "mobile"]
INCLUDE_FILES = [
    "README.md", "AGENTS.md", "requirements.txt", "requirements-dev.txt",
    "run.py", "pipeline.py", "start.bat", "open_app.bat", "app.ico",
    "pyproject.toml", ".gitignore",
]
INCLUDE_DATA = ["data/voices.json", "data/settings.example.json"]

EXCLUDE_PARTS = {
    "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", "www", "build", ".gradle",
}


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()
    count = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in INCLUDE_DIRS:
            for f in sorted((BASE / d).rglob("*")):
                if not f.is_file():
                    continue
                rel = f.relative_to(BASE)
                if any(part in EXCLUDE_PARTS for part in rel.parts):
                    continue
                zf.write(f, rel)
                count += 1
        for name in INCLUDE_FILES + INCLUDE_DATA:
            f = BASE / name
            if f.exists():
                zf.write(f, name)
                count += 1
    print(f"打包完成: {OUT} ({OUT.stat().st_size // 1024} KB, {count} 个文件)")
    print("接收方解压后: python -m venv .venv")
    print("然后 .venv\\Scripts\\pip install -r requirements.txt 并填入 data/settings.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
