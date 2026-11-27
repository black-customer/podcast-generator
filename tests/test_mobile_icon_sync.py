"""Android 壳静态资源同步回归测试。"""

import re

from scripts import sync_mobile


def test_sync_places_icons_at_web_static_url(tmp_path, monkeypatch) -> None:
    web = tmp_path / "web"
    www = tmp_path / "www"
    web.mkdir()
    for name in ["index.html", "sw.js", "manifest.webmanifest", *sync_mobile.STATIC_FILES]:
        (web / name).write_text("fixture", encoding="utf-8")
    (web / "icons").mkdir()
    (web / "icons" / "icon-32.png").write_bytes(b"icon")
    monkeypatch.setattr(sync_mobile, "WEB", web)
    monkeypatch.setattr(sync_mobile, "WWW", www)

    sync_mobile.sync()

    assert (www / "static" / "icons" / "icon-32.png").read_bytes() == b"icon"


def test_shared_web_entry_points_are_available_in_mobile_sync(tmp_path, monkeypatch):
    www = tmp_path / "www"
    monkeypatch.setattr(sync_mobile, "WWW", www)
    sync_mobile.sync()
    for name in ("index.html", "sw.js"):
        entry = (www / name).read_text(encoding="utf-8")
        for asset in re.findall(r'/static/[^"\s]+', entry):
            assert (www / asset.lstrip("/")).read_bytes() == (
                sync_mobile.WEB / asset.removeprefix("/static/")).read_bytes(), asset
