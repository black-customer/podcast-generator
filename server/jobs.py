"""后台任务系统：持久化 + 话题互斥 + 取消令牌 + 异步合成（M05）。"""
import json
import logging
import threading
import uuid

from . import assemble, library, rewrite, study, tts
from .config import DATA_DIR, atomic_write_text, load_settings

logger = logging.getLogger(__name__)

JOBS_LOCK = threading.Lock()
JOBS: dict[str, dict] = {}

# 持久化文件（测试可替换）
JOBS_FILE = DATA_DIR / "jobs.json"

# 已结束任务最多保留条数
MAX_FINISHED_JOBS = 50

# 运行中任务的 topic 互斥表
_ACTIVE_TOPICS: dict[str, str] = {}  # topic_id -> job_id


class JobConflict(RuntimeError):
    pass


def _now() -> str:
    return library.now_iso()


def _persist_locked() -> None:
    """把任务表原子落盘（去掉运行期内部字段）。"""
    serializable = {}
    for jid, j in JOBS.items():
        serializable[jid] = {k: v for k, v in j.items() if k not in ("cancel_event",)}
    try:
        atomic_write_text(JOBS_FILE, json.dumps(serializable, ensure_ascii=False, indent=2))
    except OSError:
        logger.warning("任务表落盘失败", exc_info=True)


def recover_from_disk() -> None:
    """服务启动时恢复任务表；上次仍在 running 的任务标记为 interrupted。"""
    if not JOBS_FILE.exists():
        return
    try:
        stored = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not isinstance(stored, dict):
        return
    with JOBS_LOCK:
        JOBS.clear()
        _ACTIVE_TOPICS.clear()
        for jid, j in stored.items():
            if not isinstance(j, dict):
                continue
            if j.get("state") == "running":
                j["state"] = "interrupted"
                j["finished_at"] = _now()
                j.setdefault("errors", []).append(
                    {"item_id": "", "message": "服务重启，任务中断"}
                )
            JOBS[jid] = j
        _prune_finished_locked()
        _persist_locked()


def get_job(job_id: str) -> dict | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return None
        out = dict(job)
        out.pop("cancel_event", None)
        return out


def list_jobs(limit: int = 50) -> list[dict]:
    with JOBS_LOCK:
        jobs = [dict(j) for j in JOBS.values()]
    for j in jobs:
        j.pop("cancel_event", None)
    jobs.sort(key=lambda j: j.get("started_at") or "", reverse=True)
    return jobs[:limit]


def _prune_finished_locked() -> None:
    finished = sorted(
        (j for j in JOBS.values() if j["state"] not in ("running",)),
        key=lambda j: j.get("started_at") or "",
    )
    excess = len(finished) - MAX_FINISHED_JOBS
    for j in finished[: max(0, excess)]:
        JOBS.pop(j["id"], None)
        topic_id = j.get("topic_id") or ""
        if _ACTIVE_TOPICS.get(topic_id) == j["id"]:
            _ACTIVE_TOPICS.pop(topic_id, None)


def _finish(job: dict, state: str) -> None:
    job["state"] = state
    job["finished_at"] = _now()
    topic_id = job.get("topic_id") or ""
    if _ACTIVE_TOPICS.get(topic_id) == job["id"]:
        _ACTIVE_TOPICS.pop(topic_id, None)
    _persist_locked()


def _running_topic_job_locked(topic_id: str) -> dict | None:
    active_id = _ACTIVE_TOPICS.get(topic_id)
    job = JOBS.get(active_id) if active_id else None
    return job if job and job["state"] == "running" else None


def _run_generate(
    job_id: str,
    topic_id: str,
    item_ids: list[str],
    force: bool,
    track: str = "default",
) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        cancel_event = (job or {}).get("cancel_event")
    if job is None:
        return
    for idx, item_id in enumerate(item_ids):
        if cancel_event is not None and cancel_event.is_set():
            with JOBS_LOCK:
                _finish(job, "cancelled")
            return
        with JOBS_LOCK:
            job["done"] = idx
            job["current"] = item_id
            _persist_locked()
        try:
            if force:
                library.update_item_meta(topic_id, item_id, stale=False)
            tts.generate_item_audio(topic_id, item_id, track=track, cancel=cancel_event)
        except tts.TTSCancelled:
            with JOBS_LOCK:
                _finish(job, "cancelled")
            return
        except Exception as exc:  # 单条失败不阻断批次
            msg = str(exc)
            with JOBS_LOCK:
                job["errors"].append({"item_id": item_id, "message": msg[:300]})
                _persist_locked()
            try:
                library.update_item_meta(topic_id, item_id, error=msg[:300])
            except Exception:
                pass
    with JOBS_LOCK:
        if job["state"] == "running":
            job["done"] = len(item_ids)
            _finish(job, "done")


def start_generate(
    topic_id: str,
    force: bool = False,
    item_ids: list[str] | None = None,
    track: str = "default",
) -> dict:
    """启动批量合成。同话题已有运行中任务时返回该任务（already_running=True）。"""
    with JOBS_LOCK:
        active = _running_topic_job_locked(topic_id)
        if active:
            if active["kind"] != "generate":
                raise JobConflict("该话题已有运行中的任务")
            return {
                "job_id": active["id"],
                "total": active["total"],
                "already_running": True,
            }

    topic = library.get_topic(topic_id)
    if item_ids is None:
        targets = []
        for it in topic["items"]:
            if force or it["status"] != "generated" or it.get("stale"):
                texts = library.get_item_full(topic_id, it["id"])
                src, _ = library.get_track_source_text(texts, track=track)
                if src:
                    targets.append(it["id"])
    else:
        targets = []
        for it in topic["items"]:
            if it["id"] in item_ids:
                texts = library.get_item_full(topic_id, it["id"])
                src, _ = library.get_track_source_text(texts, track=track)
                if src:
                    targets.append(it["id"])
                else:
                    raise RuntimeError(f"条目 {it['id']} 没有可合成的文本")

    if not targets:
        raise RuntimeError("没有需要生成的条目（请检查对应轨道文本是否已填写）")

    job_id = uuid.uuid4().hex[:12]
    cancel_event = threading.Event()
    with JOBS_LOCK:
        active = _running_topic_job_locked(topic_id)
        if active:
            if active["kind"] != "generate":
                raise JobConflict("该话题已有运行中的任务")
            return {
                "job_id": active["id"],
                "total": active["total"],
                "already_running": True,
            }
        JOBS[job_id] = {
            "id": job_id,
            "kind": "generate",
            "topic_id": topic_id,
            "track": track,
            "state": "running",
            "total": len(targets),
            "done": 0,
            "current": "",
            "errors": [],
            "cancel": False,
            "cancel_event": cancel_event,
            "started_at": _now(),
            "finished_at": None,
        }
        _ACTIVE_TOPICS[topic_id] = job_id
        _prune_finished_locked()
        _persist_locked()
    t = threading.Thread(
        target=_run_generate, args=(job_id, topic_id, targets, force, track), daemon=True
    )
    t.start()
    return {"job_id": job_id, "total": len(targets)}


def _run_api_generate(job_id: str, topic_id: str, item_id: str, question: str, answer: str) -> None:
    """API 模式：StepFun JSON Mode 改写 → 校验落盘 → 自动 TTS。

    改写失败保留原始回答，不产生或覆盖任何音频。
    """
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        cancel_event = (job or {}).get("cancel_event")
    if job is None:
        return

    def _set_phase(phase: str) -> None:
        with JOBS_LOCK:
            job["phase"] = phase
            _persist_locked()

    try:
        _set_phase("rewrite")
        texts, _repairs = rewrite.generate_texts(
            load_settings(), question, answer, cancel=cancel_event
        )
        _set_phase("save")
        texts["original_answer"] = answer
        library.update_item_texts(topic_id, item_id, texts)
        _set_phase("tts")
        tts.generate_item_audio(topic_id, item_id, track="podcast", cancel=cancel_event)
        try:
            study.prepare_async(topic_id, item_id)
        except Exception:
            logger.warning("音频已完成，逐句材料准备未启动", exc_info=True)
    except tts.TTSCancelled:
        with JOBS_LOCK:
            _finish(job, "cancelled")
        return
    except rewrite.TextPermissionError as exc:
        with JOBS_LOCK:
            job["errors"].append({"item_id": item_id, "message": str(exc)[:300]})
            _persist_locked()
            library_update_error(topic_id, item_id, str(exc))
            _finish(job, "error")
        return
    except Exception as exc:
        msg = str(exc)
        with JOBS_LOCK:
            job["errors"].append({"item_id": item_id, "message": msg[:300]})
            _persist_locked()
            library_update_error(topic_id, item_id, msg)
            _finish(job, "error")
        return
    with JOBS_LOCK:
        job["done"] = 1
        _finish(job, "done")


def library_update_error(topic_id: str, item_id: str, message: str) -> None:
    try:
        library.update_item_meta(topic_id, item_id, error=message[:300])
    except Exception:
        pass


def start_api_generation(topic_id: str, item_id: str, question: str, answer: str) -> dict:
    """API 模式生成任务；同话题互斥。"""
    with JOBS_LOCK:
        if _running_topic_job_locked(topic_id):
            raise JobConflict("该话题已有运行中的生成任务")
        job_id = uuid.uuid4().hex[:12]
        JOBS[job_id] = {
            "id": job_id,
            "kind": "api_generate",
            "topic_id": topic_id,
            "track": "podcast",
            "phase": "rewrite",
            "state": "running",
            "total": 1,
            "done": 0,
            "current": item_id,
            "errors": [],
            "cancel": False,
            "cancel_event": threading.Event(),
            "started_at": _now(),
            "finished_at": None,
        }
        _ACTIVE_TOPICS[topic_id] = job_id
        _prune_finished_locked()
        _persist_locked()
    threading.Thread(
        target=_run_api_generate, args=(job_id, topic_id, item_id, question, answer), daemon=True
    ).start()
    return {"job_id": job_id, "total": 1}


def _run_assemble(job_id: str, topic_id: str, track: str) -> None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        return
    cancel_event = job.get("cancel_event")
    try:
        if cancel_event is not None and cancel_event.is_set():
            with JOBS_LOCK:
                _finish(job, "cancelled")
            return
        manifest = assemble.assemble_episode(topic_id, track=track)
        with JOBS_LOCK:
            if cancel_event is not None and cancel_event.is_set():
                # ffmpeg 拼接无法中途打断：取消在当前步骤后生效，终态如实标注
                _finish(job, "cancelled")
                return
            job["result"] = manifest
            _finish(job, "done")
    except Exception as exc:
        with JOBS_LOCK:
            if cancel_event is not None and cancel_event.is_set():
                _finish(job, "cancelled")
                return
            job["errors"].append({"item_id": "", "message": str(exc)[:300]})
            _finish(job, "error")


def start_assemble(topic_id: str, track: str = "default") -> dict:
    """整集合成改为后台任务（不再阻塞 HTTP 请求，避免双击并发 ffmpeg）。"""
    with JOBS_LOCK:
        active = _running_topic_job_locked(topic_id)
        if active:
            if active["kind"] == "assemble":
                return {"job_id": active["id"], "already_running": True}
            raise JobConflict("该话题已有运行中的生成任务")

    library.get_topic(topic_id)  # 校验存在性，404 由上层转译
    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        active = _running_topic_job_locked(topic_id)
        if active:
            if active["kind"] == "assemble":
                return {"job_id": active["id"], "already_running": True}
            raise JobConflict("该话题已有运行中的生成任务")
        JOBS[job_id] = {
            "id": job_id,
            "kind": "assemble",
            "topic_id": topic_id,
            "track": track,
            "state": "running",
            "total": 1,
            "done": 0,
            "current": "",
            "errors": [],
            "cancel": False,
            "cancel_event": threading.Event(),
            "started_at": _now(),
            "finished_at": None,
        }
        _ACTIVE_TOPICS[topic_id] = job_id
        _prune_finished_locked()
        _persist_locked()
    threading.Thread(target=_run_assemble, args=(job_id, topic_id, track), daemon=True).start()
    return {"job_id": job_id, "total": 1}


def cancel_job(job_id: str) -> bool:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job and job["state"] == "running":
            job["cancel"] = True
            event = job.get("cancel_event")
            if event is not None:
                event.set()
            return True
        return False
