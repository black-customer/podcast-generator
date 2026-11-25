"""后台任务系统：持久化 + 话题互斥 + 取消令牌 + 异步合成（M05）。"""
import json
import logging
import threading
import uuid

from . import assemble, library, rewrite, speech_bridge, study, teaching_podcast, tts
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


def active_item_job(topic_id: str, item_id: str) -> dict | None:
    """单题的最近一次 API/audio-only 任务，包含终态供恢复使用。"""
    with JOBS_LOCK:
        matches = (job for job in JOBS.values()
                   if job.get("kind") in {"api_generate", "retry_audio"}
                   and job.get("topic_id") == topic_id and job.get("current") == item_id)
        job = max(matches, key=lambda row: (row["started_at"], row["state"] == "running",
                                            row.get("finished_at") or ""), default=None)
        if job is None:
            return None
        data = {key: job.get(key) for key in (
            "id", "state", "phase", "tts_done", "tts_total", "tts_label", "tts_voice",
            "progress_pct", "started_at",
        )}
        data["error"] = "；".join(row["message"] for row in job.get("errors", []))
        return data


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


def _run_api_generate(job_id: str, topic_id: str, item_id: str,
                      question: str | None, answer: str | None) -> None:
    """API 模式合并改写与逐句材料，校验后自动合成音频。

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

    def progress(done: int, total: int, label: str, voice: str) -> None:
        with JOBS_LOCK:
            job.update(tts_done=done, tts_total=total, tts_label=label, tts_voice=voice,
                       progress_pct=round(100 * done / total) if total else 0)

    try:
        can_prepare = False
        fingerprint = None
        if question is not None and answer is not None:
            _set_phase("rewrite")
            from . import study_progress
            extra = study_progress.get_progress(topic_id, item_id).get("training_inputs") or {}
            options = {"supplement": extra} if extra.get("intent") or extra.get("feedback") else {}
            settings = load_settings()
            material = None
            texts = None
            if rewrite.text_available(settings):
                try:
                    texts = rewrite.generate_complete_bundle(
                        settings, question, answer, cancel=cancel_event, **options
                    )
                    material = texts.pop("study_material")
                except rewrite.BundleFormatError:
                    logger.info("合并响应格式不完整，重新生成音频文本")
            if texts is None:
                texts, _repairs = rewrite.generate_texts(
                    settings, question, answer, cancel=cancel_event, **options
                )
            if cancel_event and cancel_event.is_set():
                raise tts.TTSCancelled("已取消")
            _set_phase("save")
            with library.LIB_LOCK:
                current = library.get_item_full(topic_id, item_id)
                if (rewrite.original_answer_of(current) != answer
                        or current.get("question") != question):
                    raise rewrite.RewriteError("生成时原始回答或题目有改动，请从当前回答重新生成")
                library.update_item_texts(topic_id, item_id, {"original_answer": answer, **texts})
                fingerprint = study.source_fingerprint(library.get_item_full(topic_id, item_id))
                if material is not None:
                    study.save_material(topic_id, item_id, material, require_audio=False)
            with JOBS_LOCK:
                job["coaching_ready"] = material is not None
            can_prepare = (material is None and not settings.get("dry_run")
                           and rewrite.text_available(settings))
        _set_phase("tts")
        tts.generate_item_audio(topic_id, item_id, track="podcast", cancel=cancel_event,
                                on_progress=progress)
        if can_prepare:
            _set_phase("study")
            try:
                with library.LIB_LOCK:
                    current = library.get_item_full(topic_id, item_id)
                    if fingerprint != study.source_fingerprint(current):
                        raise study.MaterialError("回答已更新，请重新准备逐句材料")
                study.generate_material(topic_id, item_id, cancel=cancel_event, require_chunks=True)
            except (study.MaterialError, rewrite.RewriteError) as exc:
                if cancel_event and cancel_event.is_set():
                    raise tts.TTSCancelled("已取消") from exc
                study.set_status(topic_id, item_id, "failed", str(exc), fingerprint)
    except tts.TTSCancelled:
        with JOBS_LOCK:
            _finish(job, "cancelled")
        return
    except Exception as exc:
        msg = str(exc)
        library_update_error(topic_id, item_id, msg)
        with JOBS_LOCK:
            job["errors"].append({"item_id": item_id, "message": msg[:300]})
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


def start_api_generation(topic_id: str, item_id: str, question: str | None,
                         answer: str | None) -> dict:
    """API 模式生成任务；同话题互斥。"""
    with JOBS_LOCK:
        if _running_topic_job_locked(topic_id):
            raise JobConflict("该话题已有运行中的生成任务")
        job_id = uuid.uuid4().hex[:12]
        audio_only = question is None
        JOBS[job_id] = {
            "id": job_id,
            "kind": "retry_audio" if audio_only else "api_generate",
            "topic_id": topic_id,
            "track": "podcast",
            "phase": "tts" if audio_only else "rewrite",
            "coaching_ready": audio_only,
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


def start_teaching_podcast(kind: str, mode: str, partner: str, topic_id: str | None = None,
                           item_id: str | None = None) -> dict:
    scope = [kind, mode, partner, topic_id, item_id]
    with JOBS_LOCK:
        for existing in JOBS.values():
            if existing.get("radio_scope") == scope and existing["state"] == "running":
                return {"job_id": existing["id"], "state": "running"}
        job_id = uuid.uuid4().hex[:12]
        cancel = threading.Event()
        job = JOBS[job_id] = {
            "id": job_id, "kind": "teaching_podcast", "radio_scope": scope,
            "topic_id": topic_id or "", "current": item_id or "",
            "phase": "script", "state": "running", "done": 0, "total": 0,
            "label": "正在编排双人播客", "errors": [], "cancel": False,
            "cancel_event": cancel, "started_at": _now(), "finished_at": None,
        }
        _prune_finished_locked()
        _persist_locked()

    def progress(phase: str, done: int, total: int, label: str) -> None:
        with JOBS_LOCK:
            job.update(phase=phase, done=done, total=total, label=label)

    def run() -> None:
        try:
            if topic_id is not None and item_id is not None:
                episode = teaching_podcast.for_item(
                    topic_id, item_id, mode, partner, cancel=cancel, on_progress=progress,
                )
            else:
                episode = teaching_podcast.for_today(mode, partner, cancel=cancel,
                                                     on_progress=progress)
        except (tts.TTSCancelled, speech_bridge.SpeechCancelled):
            with JOBS_LOCK:
                _finish(job, "cancelled")
        except Exception as exc:
            with JOBS_LOCK:
                if not cancel.is_set():
                    job["errors"].append({"item_id": item_id or "", "message": str(exc)[:300]})
                _finish(job, "cancelled" if cancel.is_set() else "error")
        else:
            with JOBS_LOCK:
                job["episode"] = teaching_podcast.public_episode(episode)
                _finish(job, "done")

    threading.Thread(target=run, name="teaching-podcast", daemon=True).start()
    return {"job_id": job_id, "state": "running"}


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
