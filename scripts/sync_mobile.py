"""同步 web/ 到 mobile/www（B02 Android 壳资源）。

保持与服务端一致的 URL 布局：
  web/index.html            → www/index.html
  web/*.js / style.css / icons / sw.js / manifest
                            → www/static/* 与根路径（/sw.js、/manifest.webmanifest）
服务端把 web/ 挂在 /static 并为 /sw.js 提供根路由；壳内由 Capacitor 本地服务器
按相同路径提供，前端代码零改动。manifest 中的 start_url/ scope 在壳内无意义但无害。
"""
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
WEB = BASE / "web"
WWW = BASE / "mobile" / "www"

STATIC_FILES = ["app.js", "experience.js", "study.js", "oral_review.js", "packreader.js", "packmode.js",
                "style.css"]


def patch_java17() -> None:
    """Capacitor 7.6+ 生成/内置的 gradle 均要求 Java 21，本机 JDK17——统一改回 17。

    覆盖三处：node_modules 库模块、app/capacitor.build.gradle（cap sync 再生成）、
    capacitor-cordova-android-plugins。npm install 或 cap sync 后重跑本脚本即可。
    """
    targets = [
        BASE / "mobile" / "node_modules" / "@capacitor" / "android" / "capacitor" / "build.gradle",
        BASE / "mobile" / "android" / "app" / "capacitor.build.gradle",
        BASE / "mobile" / "android" / "capacitor-cordova-android-plugins" / "build.gradle",
    ]
    for gradle in targets:
        if not gradle.exists():
            continue
        text = gradle.read_text(encoding="utf-8")
        if "VERSION_21" in text:
            gradle.write_text(
                text.replace("JavaVersion.VERSION_21", "JavaVersion.VERSION_17"),
                encoding="utf-8",
            )
            print(f"patched -> Java 17: {gradle.relative_to(BASE)}")


def sync() -> None:
    if WWW.exists():
        shutil.rmtree(WWW)
    (WWW / "static").mkdir(parents=True)
    shutil.copy(WEB / "index.html", WWW / "index.html")
    for name in STATIC_FILES:
        shutil.copy(WEB / name, WWW / "static" / name)
    # 根路径资源（service worker 与 PWA manifest；壳内注册失败也不影响功能）
    shutil.copy(WEB / "sw.js", WWW / "sw.js")
    shutil.copy(WEB / "manifest.webmanifest", WWW / "manifest.webmanifest")
    if (WEB / "icons").exists():
        shutil.copytree(WEB / "icons", WWW / "static" / "icons")
    print(f"synced web/ -> mobile/www ({sum(1 for _ in WWW.rglob('*') if _.is_file())} files)")


if __name__ == "__main__":
    patch_java17()
    sync()
