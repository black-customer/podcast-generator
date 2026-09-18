"""后台批量任务：串行生成一个话题下所有待合成条目的音频。"""
import threading
import uuid

from . import library, tts

JOBS_LOCK = threading.Lock()
JOBS: dict[str, dict] = {}

# 已结束任务最多保留条数，防止 JOBS 无限增长
MAX_FINISHED_JOBS = 50


def get_job(job_id: str) -> dict | None:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def _prune_finished_locked() -> None:
    finished = sorted(
        (j for j in JOBS.values() if j["state"] != "running"),
        key=lambda j: j.get("started_at") or "",
    )
    excess = len(finished) - MAX_FINISHED_JOBS
    for j in finished[:max(0, excess)]:
        JOBS.pop(j["id"], None)


def _run_generate(job_id: str, topic_id: str, item_ids: list[str], force: bool, track: str = "default") -> None:
    job = JOBS[job_id]
    for idx, item_id in enumerate(item_ids):
        with JOBS_LOCK:
            if job.get("cancel"):
                job["state"] = "cancelled"
                break
            job["done"] = idx
            job["current"] = item_id
        try:
            if force:
                library.update_item_meta(topic_id, item_id, stale=False)
            tts.generate_item_audio(topic_id, item_id, track=track)
        except Exception as exc:  # 单条失败不阻断批次
            msg = str(exc)
            with JOBS_LOCK:
                job["errors"].append({"item_id": item_id, "message": msg[:300]})
            try:
                library.update_item_meta(topic_id, item_id, error=msg[:300])
            except Exception:
                pass
    with JOBS_LOCK:
        if job["state"] == "running":
            job["state"] = "done"
            job["done"] = len(item_ids)
        job["finished_at"] = library.now_iso()


def start_generate(
    topic_id: str,
    force: bool = False,
    item_ids: list[str] | None = None,
    track: str = "default",
) -> dict:
    """启动批量合成。item_ids 为空时：选取话题内所有待生成条目；force 全部重来。"""
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
    with JOBS_LOCK:
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
            "started_at": library.now_iso(),
            "finished_at": None,
        }
        _prune_finished_locked()
    t = threading.Thread(
        target=_run_generate, args=(job_id, topic_id, targets, force, track), daemon=True
    )
    t.start()
    return {"job_id": job_id, "total": len(targets)}


def cancel_job(job_id: str) -> bool:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job and job["state"] == "running":
            job["cancel"] = True
            return True
        return False
