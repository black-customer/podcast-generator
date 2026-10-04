"""手机学习数据与聊天导入回归：仅使用合成记录，不调用网络或收费 API。"""
import subprocess
from pathlib import Path


def test_mobile_domain_regressions():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        ["node", str(root / "tests" / "mobile_domain.cjs")],
        capture_output=True, text=True, encoding="utf-8", cwd=root,
    )
    assert result.returncode == 0, result.stdout + result.stderr
