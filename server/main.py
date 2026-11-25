"""FastAPI 应用入口。"""
import ipaddress
import os
import secrets

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import experience, jobs
from .api import router
from .config import WEB_DIR, cleanup_stale_tmp, ensure_dirs, load_settings

ensure_dirs()
cleanup_stale_tmp()
jobs.recover_from_disk()  # 上次未完成任务 → interrupted，前端轮询不再悬死

app = FastAPI(title="Bruce English Corpus 播客生成器", docs_url="/api/docs")
# 手机 APP 壳内源为 https://localhost；仅它可跨源拉取语料包。
SCENE_SYNC_ROUTES = {
    ("GET", "/api/captures/scenes/ping"),
    ("POST", "/api/captures/scenes/inbox"),
}
SCENE_LOCAL_ROUTES = {"/api/settings/scene-sync-token", "/api/captures/scenes/import-json"}
MOBILE_ORIGINS = ("https://localhost", "capacitor://localhost")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(MOBILE_ORIGINS),
    allow_methods=["GET"],
    allow_headers=["X-Lan-Token"],
)


@app.middleware("http")
async def protect_local_api(request: Request, call_next):
    """拒绝恶意网页跨源请求；非本机设备仅能凭临时令牌下载语料包。"""
    client_host = request.client.host if request.client else ""
    try:
        local_client = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        local_client = client_host == "testclient"
    path = request.url.path
    scene_sync = (request.method, path) in SCENE_SYNC_ROUTES
    origin = request.headers.get("origin", "")
    same_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
    if scene_sync or path in SCENE_LOCAL_ROUTES:
        local_host = (request.url.hostname in {"127.0.0.1", "localhost", "::1"}
                      or (client_host == "testclient" and request.url.hostname == "testserver"))
        if not local_client or not local_host:
            return Response(status_code=403)
    if scene_sync:
        token = load_settings()["scene_sync_token"]
        supplied = request.headers.get("X-Scene-Sync-Token", "")
        if (not isinstance(token, str) or not token
                or not secrets.compare_digest(supplied.encode(), token.encode())):
            return Response(status_code=403)
        return await call_next(request)
    desktop_private = path in SCENE_LOCAL_ROUTES or path.startswith(("/api/captures", "/api/cards"))
    if desktop_private and origin and origin != same_origin:
        return Response(status_code=403)
    if origin and origin not in MOBILE_ORIGINS and origin != same_origin:
        return Response(status_code=403)
    if request.headers.get("sec-fetch-site") == "cross-site" and origin not in MOBILE_ORIGINS:
        return Response(status_code=403)

    if not local_client:
        if request.url.path != "/api/pack/export":
            return Response(status_code=403)
        if request.method == "OPTIONS":
            return await call_next(request)
        token = os.environ.get("IELTS_POD_LAN_TOKEN", "")
        supplied = request.headers.get("X-Lan-Token", "")
        if request.method != "GET" or not token or not secrets.compare_digest(supplied, token):
            return Response(status_code=403)
    return await call_next(request)


app.include_router(router)
app.include_router(experience.router)
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/sw.js")
def service_worker():
    # SW 必须部署在根作用域才能控制全站请求
    return FileResponse(WEB_DIR / "sw.js", media_type="application/javascript")


@app.get("/manifest.webmanifest")
def webmanifest():
    return FileResponse(
        WEB_DIR / "manifest.webmanifest", media_type="application/manifest+json"
    )
