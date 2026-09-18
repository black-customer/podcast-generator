"""FastAPI 应用入口。"""
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import jobs
from .api import router
from .config import WEB_DIR, cleanup_stale_tmp, ensure_dirs

ensure_dirs()
cleanup_stale_tmp()
jobs.recover_from_disk()  # 上次未完成任务 → interrupted，前端轮询不再悬死

app = FastAPI(title="Bruce English Corpus 播客生成器", docs_url="/api/docs")
app.include_router(router)
app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")
