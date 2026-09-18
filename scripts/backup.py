#!/usr/bin/env python
"""一键备份个人语料（data/ 全量，可选排除音频）。

用法：
  .venv/Scripts/python scripts/backup.py            # 全量（含音频）
  .venv/Scripts/python scripts/backup.py --no-audio # 仅文本/meta（小体积）
输出：backups/backup-<时间戳>.zip
"""
import sys
import time
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"


def main() -> int:
    include_audio = "--no-audio" not in sys.argv
    ts = time.strftime("%Y%m%d-%H%M%S")
    out = BASE / "backups" / f"backup-{ts}.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(DATA.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(BASE)
            s = str(rel).replace("\\", "/")
            if ".tmp" in s:
                continue
            if not include_audio and s.endswith((".mp3", ".m4b")):
                continue
            zf.write(f, rel)
            count += 1
    print(f"备份完成: {out} ({out.stat().st_size // 1024} KB, {count} 个文件)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
