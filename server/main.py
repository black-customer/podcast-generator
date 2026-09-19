"""FastAPI 应用入口。"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import jobs
from .api import router
from .config import WEB_DIR, cleanup_stale_tmp, ensure_dirs

ensure_dirs()
cleanup_stale_tmp()
jobs.recover_from_disk()  # 上次未完成任务 → interrupted，前端轮询不再悬死

app = FastAPI(title="Bruce English Corpus 播客生成器", docs_url="/api/docs")
# 手机 APP 壳内源为 https://localhost，局域网直传语料包属跨源——本地工具放开 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
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
