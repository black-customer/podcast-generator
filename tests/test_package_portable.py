"""portable zip 打包范围：开发交接物不入便携包，体积保持路人可下载。"""
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import scripts.package as package  # noqa: E402


@pytest.fixture()
def built_zip(tmp_path, monkeypatch):
    out = tmp_path / "portable.zip"
    monkeypatch.setattr(package, "OUT", out)
    assert package.main() == 0
    return out


def test_design_handoff_images_are_excluded(built_zip):
    """docs/design/ 的概念图是开发交接物（约 40MB），不应进便携包。"""
    names = zipfile.ZipFile(built_zip).namelist()
    assert not [n for n in names if n.startswith("docs/design/")], "设计交接图被打进便携包"
    assert any(n.startswith("docs/") and n.endswith(".md") for n in names), "普通文档应保留"


def test_portable_zip_stays_downloadable(built_zip):
    """便携包压缩后应远小于设计图时代的 43MB（回归上限 8MB）。"""
    assert zipfile.ZipFile(built_zip).namelist().count("README.md") == 1
    assert built_zip.stat().st_size < 8 * 1024 * 1024, (
        f"便携包 {built_zip.stat().st_size // 1024} KB 超过 8MB 下载友好上限"
    )


def test_accidental_webm_recording_is_rejected(tmp_path, monkeypatch):
    web = tmp_path / "web"
    web.mkdir()
    (web / "accidental-recording.webm").write_bytes(b"private voice")
    out = tmp_path / "portable.zip"
    monkeypatch.setattr(package, "BASE", tmp_path)
    monkeypatch.setattr(package, "OUT", out)
    monkeypatch.setattr(package, "INCLUDE_DIRS", ["web"])
    monkeypatch.setattr(package, "INCLUDE_FILES", [])
    monkeypatch.setattr(package, "INCLUDE_DATA", [])
    assert package.main() == 1
    assert not out.exists()
