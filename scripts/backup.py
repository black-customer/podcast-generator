#!/usr/bin/env python
"""一键备份个人语料（data/ 语料文本与 meta；密钥与本机练习记录永不进包）。

用法：
  .venv/Scripts/python scripts/backup.py            # 全量（含音频）
  .venv/Scripts/python scripts/backup.py --no-audio # 仅文本/meta（小体积）
输出：backups/backup-<时间戳>.zip（backups/ 已被 git 忽略，永不提交）

排除规则：
  data/settings.json      —— 含 API key，备份即泄漏源；恢复后需手动重配 Key
  data/study_private/     —— 本机练习录音与进度，属设备私有数据
  data/.tmp/              —— 运行时临时目录

恢复步骤：
  1. 停止服务，把 zip 解压到仓库根目录（覆盖 data/topics 等）；
  2. settings.json 不在包内：新装机先复制 settings.example.json 再填入自己的 Key；
  3. 重启服务，`python -m server.doctor` 确认各项就绪。
"""
import sys
import time
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"

FORBIDDEN_PARTS = {"settings.json", "study_private", ".tmp"}


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
            if any(part in s for part in FORBIDDEN_PARTS):
                continue
            if not include_audio and s.endswith((".mp3", ".m4b")):
                continue
            zf.write(f, rel)
            count += 1
    print(f"备份完成: {out} ({out.stat().st_size // 1024} KB, {count} 个文件)")
    print("注意：settings.json 与 study_private 不在包内（密钥与练习录音永不备份）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
