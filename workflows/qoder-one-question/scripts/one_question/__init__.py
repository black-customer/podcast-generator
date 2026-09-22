"""单题雅思口语教学包工作流（Stage 1）。

这个包刻意做成自包含：整个 workflows/qoder-one-question 目录可以单独拷走。
唯一的外部依赖是宿主项目的 server.tts / server.audio，所以在这里把仓库根
挂进 sys.path——否则从 scripts/ 目录用 -m 运行时会找不到 server。
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
if str(_REPO_ROOT) not in sys.path and _REPO_ROOT.exists():
    sys.path.insert(0, str(_REPO_ROOT))
