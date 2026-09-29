"""备份治理：密钥与私密数据永不进备份 zip。"""
import importlib.util
import zipfile
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture()
def backup_mod(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "backup_mod", BASE_DIR / "scripts" / "backup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    data = tmp_path / "data"
    (data / "topics" / "01-t" / "items" / "001-a").mkdir(parents=True)
    (data / "topics" / "01-t" / "items" / "001-a" / "chinese.txt").write_text(
        "回答", encoding="utf-8")
    (data / "settings.json").write_text(
        '{"fish_api_key": "sk-real-secret"}', encoding="utf-8")
    (data / "study_private" / "01-t" / "001-a").mkdir(parents=True)
    (data / "study_private" / "01-t" / "001-a" / "rec.webm").write_bytes(b"voice")
    monkeypatch.setattr(mod, "DATA", data)
    monkeypatch.setattr(mod, "BASE", tmp_path)
    return mod, tmp_path


def test_backup_never_contains_secrets_or_private_recordings(backup_mod):
    mod, tmp = backup_mod
    mod.main()
    zips = list((tmp / "backups").glob("backup-*.zip"))
    assert len(zips) == 1
    names = zipfile.ZipFile(zips[0]).namelist()
    assert "data/settings.json" not in names, "密钥文件不得进备份"
    assert not [n for n in names if "study_private" in n], "本机练习录音不得进备份"
    assert any("chinese.txt" in n for n in names), "语料文本应正常备份"
    blob = zipfile.ZipFile(zips[0]).read(
        next(n for n in names if "chinese.txt" in n))
    assert blob.decode("utf-8") == "回答"
