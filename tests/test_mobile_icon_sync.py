"""Android 壳静态图标同步回归测试。"""

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
