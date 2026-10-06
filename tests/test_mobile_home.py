"""首页轻练读取与选句回归，只使用合成材料。"""
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("mode", ["read-only", "candidates"])
def test_mobile_home_domain(mode: str) -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["node", str(root / "tests/mobile_home.cjs"), mode],
        capture_output=True, text=True, encoding="utf-8", cwd=root,
    )
    assert result.returncode == 0, result.stdout + result.stderr
