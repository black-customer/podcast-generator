"""HTTP API 路由。"""
import hashlib
import json
import secrets
import threading
import uuid
from contextlib import nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, field_validator
from starlette.background import BackgroundTask

from . import (
    arcade,
    assemble,
    audio,
    bank,
    capture_distill,
    captures,
    exports,
    exports_media,
    jobs,
    library,
    oral_review,
    pack,
    production,
    rewrite,
    speech_bridge,
    study,
    study_progress,
    teaching_podcast,
    timeline,
)
from .config import (
    APP_VERSION,
    DATA_DIR,
    DEFAULT_SETTINGS,
    PROMPTS_DIR,
    TMP_DIR,
    atomic_replace,
    cleanup_voice_previews,
    is_dry_run,
    is_llm_configured,
    load_settings,
    real_llm_api_key,
    save_settings,
    speech_engine_available,
)

router = APIRouter(prefix="/api")

TrackParam = Literal["default", "monologue", "podcast"]
_PREVIEW_LOCK = threading.Lock()
_PAIRING_LOCK = threading.Lock()


class TopicIn(BaseModel):
    name: str


class ItemIn(BaseModel):
    question: str = ""
    chinese: str = ""
    original_answer: str = ""
    natural_english: str = ""
    fish_script: str = ""
    monologue_text: str = ""
    monologue_script: str = ""
    podcast_text: str = ""
    podcast_script: str = ""


class BulkIn(BaseModel):
    text: str


class GenerateIn(BaseModel):
    force: bool = False
    track: Literal["default", "monologue", "podcast", "all"] = "default"


class SettingsIn(BaseModel):
    tts_provider: Literal["kokoro_local"] | None = None
    speech_engine_dir: str | None = None
    kokoro_question_voice: Literal[
        "af_bella", "af_heart", "am_liam", "am_michael", "am_puck", "am_fenrir"
    ] | None = None
    kokoro_answer_voice: Literal[
        "af_bella", "af_heart", "am_liam", "am_michael", "am_puck", "am_fenrir", "golden_self"
    ] | None = None
    llm_provider: Literal["deepseek", "custom"] | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    vision_base_url: str | None = None
    vision_model: str | None = None
    vision_api_key: str | None = None
    daily_session_limit: Literal[5, 8, 12, 20] | None = None
    reaction_timer_enabled: bool | None = None
    episode_gap_ms: float | None = None
    dry_run: bool | None = None
    @field_validator("episode_gap_ms")
    @classmethod
    def _v_gap(cls, v: float | None) -> float | None:
        if v is not None and not 0 <= v <= 10000:
            raise ValueError("停顿毫秒必须在 0–10000")
        return v


def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail=message)


@router.get("/health")
def health():
    ok, msg = audio.check_ffmpeg()
    return {
        "ok": ok,
        "version": APP_VERSION,
        "ffmpeg": {"ok": ok, "message": msg},
        "mode": "dry_run" if is_dry_run() else "live",
        "data_dir": str(DATA_DIR),
    }


# ---------------------------------------------------------------- topics

@router.get("/topics")
def api_list_topics():
    topics = library.list_topics(include_titles=True)
    try:
        index = bank.category_index(bank.load_bank())
    except Exception:
        index = {"norms": set(), "names": set()}
    for t in topics:
        # 语料库用户概念只有「雅思口语 / 日常表达」两类（R04）；题库来源话题归前者
        t["category"] = bank.topic_category(t["name"], t.pop("titles"), index)
    return topics


@router.post("/topics")
def api_create_topic(body: TopicIn):
    return library.create_topic(body.name)


@router.get("/topics/{topic_id}")
def api_get_topic(topic_id: str):
    try:
        return library.get_topic(topic_id)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as e:
        raise _err(400, str(e)) from e


@router.patch("/topics/{topic_id}")
def api_rename_topic(topic_id: str, body: TopicIn):
    try:
        library.rename_topic(topic_id, body.name)
        return {"ok": True}
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as e:
        raise _err(400, str(e)) from e


@router.delete("/topics/{topic_id}")
def api_delete_topic(topic_id: str):
    try:
        library.delete_topic(topic_id)
        return {"ok": True}
    except ValueError as e:
        raise _err(400, str(e)) from e


# ---------------------------------------------------------------- items

@router.post("/topics/{topic_id}/items")
def api_create_item(topic_id: str, body: ItemIn):
    try:
        return library.create_item(topic_id, body.model_dump())
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as e:
        raise _err(400, str(e)) from e


@router.post("/topics/{topic_id}/items/bulk")
def api_bulk_items(topic_id: str, body: BulkIn):
    """每行一个题目，批量创建条目。"""
    created = []
    try:
        for line in body.text.splitlines():
            line = line.strip()
            if line:
                created.append(library.create_item(topic_id, {"question": line}))
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(400, str(exc)) from exc
    return {"created": len(created), "items": created}


@router.get("/topics/{topic_id}/items/{item_id}")
def api_get_item(topic_id: str, item_id: str):
    try:
        return library.get_item_full(topic_id, item_id)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as e:
        raise _err(400, str(e)) from e


@router.get("/topics/{topic_id}/items/{item_id}/study")
def api_get_study(topic_id: str, item_id: str):
    try:
        return study.get_material(topic_id, item_id)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as e:
        raise _err(400, str(e)) from e


@router.get("/speech/status")
def api_speech_status():
    return speech_bridge.status(load_settings())


async def _arcade_upload(request: Request) -> bytes:
    try:
        length = int(request.headers.get("content-length") or 0)
    except ValueError as exc:
        raise _err(400, "录音长度无效") from exc
    if length > arcade.MAX_RECORDING_BYTES:
        raise _err(413, "录音超过 30 MB")
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > arcade.MAX_RECORDING_BYTES:
            raise _err(413, "录音超过 30 MB")
        data.extend(chunk)
    return bytes(data)


@router.post("/arcade/transcribe-blind")
async def api_arcade_blind(request: Request, duration_sec: float,
                           language: Literal["en", "zh"] = "en"):
    data = await _arcade_upload(request)
    try:
        return await run_in_threadpool(
            arcade.transcribe_blind, data, request.headers.get("content-type", ""),
            duration_sec, language,
        )
    except ValueError as exc:
        raise _err(400, str(exc)) from exc
    except speech_bridge.SpeechError as exc:
        raise _err(503, str(exc)) from exc


@router.post("/arcade/transcribe-intent")
async def api_arcade_intent(request: Request, duration_sec: float):
    data = await _arcade_upload(request)
    try:
        return await run_in_threadpool(
            arcade.transcribe_intent, data, request.headers.get("content-type", ""), duration_sec,
        )
    except ValueError as exc:
        raise _err(400, str(exc)) from exc
    except speech_bridge.SpeechError as exc:
        raise _err(503, str(exc)) from exc


@router.get("/topics/{topic_id}/items/{item_id}/arcade")
def api_arcade_view(topic_id: str, item_id: str):
    try:
        return arcade.view(topic_id, item_id)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(400, str(exc)) from exc


@router.post("/topics/{topic_id}/items/{item_id}/arcade/recordings")
async def api_arcade_recordings(topic_id: str, item_id: str, request: Request,
                                stage: Literal["blind", "chunk", "final"], duration_sec: float,
                                sentence_index: int | None = None, upload_key: str | None = None,
                                source_fingerprint: str | None = None):
    data = await _arcade_upload(request)
    try:
        return await run_in_threadpool(
            arcade.record, topic_id, item_id, stage, data, request.headers.get("content-type", ""),
            duration_sec, sentence_index, upload_key, source_fingerprint,
        )
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(400, str(exc)) from exc


@router.get("/topics/{topic_id}/items/{item_id}/arcade/recordings/{recording_id}")
def api_arcade_recording(topic_id: str, item_id: str, recording_id: str):
    try:
        path, media = arcade.recording(topic_id, item_id, recording_id)
        return FileResponse(path, media_type=media, headers={"Cache-Control": "no-store"})
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(400, str(exc)) from exc


@router.post("/topics/{topic_id}/items/{item_id}/arcade/export-evolution")
def api_arcade_export(topic_id: str, item_id: str):
    try:
        path = arcade.export(topic_id, item_id)
        return FileResponse(path, media_type="audio/mpeg", filename="口语前后对比.mp3",
                            background=BackgroundTask(path.unlink, missing_ok=True),
                            headers={"Cache-Control": "no-store"})
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except (ValueError, audio.FFmpegError) as exc:
        raise _err(400, str(exc)) from exc


class ArcadeGradeIn(BaseModel):
    sentence_index: int
    source_fingerprint: str
    rating: Literal["good", "again", "easy", "suspend"]
    submission_id: str


@router.post("/topics/{topic_id}/items/{item_id}/arcade/grade")
def api_arcade_grade(topic_id: str, item_id: str, body: ArcadeGradeIn):
    try:
        return oral_review.grade_arcade(topic_id, item_id, body.sentence_index,
                                       body.source_fingerprint, body.rating, body.submission_id)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(400, str(exc)) from exc


@router.get("/arcade/blitz")
def api_arcade_blitz(summary: bool = False, include_pending: bool = False,
                     source: Literal["all", "ielts", "scene", "snippet"] = "all",
                     limit: int | None = None):
    if summary:
        return {"due_count": len(oral_review.unified_due_cards(source))}
    return arcade.home_cards(source, limit, include_pending)


@router.get("/topics/{topic_id}/items/{item_id}/arcade/sentences/{index}/voice/{voice}")
def api_arcade_sentence_voice(topic_id: str, item_id: str, index: int,
                              voice: Literal["am_puck", "golden_self"], source_fingerprint: str):
    try:
        found = study.get_material(topic_id, item_id)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(400, str(exc)) from exc
    material = found.get("material", {})
    if source_fingerprint != material.get("source_fingerprint"):
        raise _err(409, "材料已更新，请刷新后再试听")
    rows = material["sentences"]
    if not 0 <= index < len(rows):
        raise _err(404, "句子不存在")
    return _local_voice_preview(voice, rows[index]["en"])


@router.get("/arcade/error-board")
def api_arcade_error_board():
    return arcade.error_board()


class TeachingPodcastIn(BaseModel):
    language_mode: Literal["en", "bilingual"] = "en"
    partner_voice: Literal["am_puck", "golden_self"] = "am_puck"


@router.get("/teaching-podcasts")
def api_teaching_podcasts():
    return {"episodes": [teaching_podcast.public_episode(episode)
                         for episode in teaching_podcast.list_episodes()]}


@router.post("/teaching-podcasts/daily")
def api_daily_teaching_podcast(body: TeachingPodcastIn):
    return jobs.start_teaching_podcast("daily", body.language_mode, body.partner_voice)


@router.post("/topics/{topic_id}/items/{item_id}/teaching-podcast")
def api_item_teaching_podcast(topic_id: str, item_id: str, body: TeachingPodcastIn):
    try:
        if not library.item_path(topic_id, item_id).is_dir():
            raise FileNotFoundError
    except FileNotFoundError as exc:
        raise _err(404, "题目不存在") from exc
    except ValueError as exc:
        raise _err(422, str(exc)) from exc
    return jobs.start_teaching_podcast("item", body.language_mode, body.partner_voice,
                                      topic_id, item_id)


@router.post("/captures/{capture_id}/teaching-podcast")
def api_capture_teaching_podcast(capture_id: str, body: TeachingPodcastIn):
    try:
        captures.get_capture(capture_id)
    except FileNotFoundError as exc:
        raise _err(404, "素材不存在") from exc
    except ValueError as exc:
        raise _err(422, str(exc)) from exc
    return jobs.start_teaching_podcast("capture", body.language_mode, body.partner_voice,
                                      capture_id=capture_id)


@router.get("/teaching-podcasts/{episode_id}/audio")
def api_teaching_podcast_audio(episode_id: str, download: bool = False):
    try:
        path = teaching_podcast.audio_file(episode_id)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    return FileResponse(path, media_type="audio/mpeg",
                        filename=f"教学电台-{episode_id}.mp3" if download else None)


@router.post("/topics/{topic_id}/items/{item_id}/study/prepare")
def api_prepare_study(topic_id: str, item_id: str):
    try:
        current = study.get_material(topic_id, item_id)
        if current["status"] == "ready":
            return current
        if current["status"] == "needs_input" and "原始回答" in current["reason"]:
            raise _err(409, current["reason"])
        if not library.resolve_audio_file(library.item_path(topic_id, item_id), "podcast"):
            raise _err(409, "先生成播客音频，再准备逐句材料")
        started = study.prepare_async(topic_id, item_id)
        return {"status": "preparing", "started": started}
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except study.MaterialError as e:
        raise _err(409, str(e)) from e
    except ValueError as e:
        raise _err(400, str(e)) from e


@router.get("/topics/{topic_id}/items/{item_id}/study/audio/{index}")
def api_study_audio(topic_id: str, item_id: str, index: int):
    try:
        return study.sentence_audio(topic_id, item_id, index)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except study.MaterialError as e:
        # 材料未就绪=409（可重试准备）；句子序号越界=400
        code = 400 if "越界" in str(e) else 409
        raise _err(code, str(e)) from e
    except ValueError as exc:
        raise _err(400, str(exc)) from exc


@router.get("/topics/{topic_id}/items/{item_id}/study/progress")
def api_study_progress(topic_id: str, item_id: str):
    try:
        return study_progress.get_progress(topic_id, item_id)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as e:
        raise _err(400, str(e)) from e


@router.patch("/topics/{topic_id}/items/{item_id}/study/progress")
def api_save_study_progress(topic_id: str, item_id: str, body: dict):
    try:
        return study_progress.save_progress(topic_id, item_id, body)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as e:
        raise _err(400, str(e)) from e


@router.post("/topics/{topic_id}/items/{item_id}/study/recordings")
async def api_save_study_recording(
    topic_id: str, item_id: str, request: Request, stage: str, duration_sec: float,
    upload_key: str | None = None,
):
    data = await _arcade_upload(request)
    try:
        return await run_in_threadpool(
            study_progress.save_recording, topic_id, item_id, stage, data, duration_sec,
            request.headers.get("content-type") or "", upload_key=upload_key,
        )
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as e:
        raise _err(400, str(e)) from e


@router.get("/topics/{topic_id}/items/{item_id}/study/recordings/{recording_id}")
def api_get_study_recording(topic_id: str, item_id: str, recording_id: str):
    try:
        data, media_type = study_progress.read_recording(topic_id, item_id, recording_id)
        return Response(content=data, media_type=media_type)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as e:
        raise _err(400, str(e)) from e


@router.delete("/topics/{topic_id}/items/{item_id}/study/recordings/{recording_id}")
def api_delete_study_recording(topic_id: str, item_id: str, recording_id: str):
    try:
        study_progress.delete_recording(topic_id, item_id, recording_id)
        return {"ok": True}
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as e:
        raise _err(400, str(e)) from e


@router.get("/study/review")
def api_study_review():
    return study_progress.review_items()


class OralSessionIn(BaseModel):
    topic_id: str | None = None
    item_id: str | None = None
    sentence_index: int | None = None


class OralActionIn(BaseModel):
    action: str
    action_id: str


class OralAttemptIn(BaseModel):
    submission_id: str
    rating: str


class OralCardIn(BaseModel):
    paused: bool


@router.get("/study/today")
def api_study_today():
    return oral_review.today_overview()


@router.get("/study/training")
def api_training_overview():
    from . import training
    return training.overview()


@router.get("/topics/{topic_id}/items/{item_id}/study/training")
def api_training(topic_id: str, item_id: str):
    from . import training
    try:
        return training.get(topic_id, item_id)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(409, str(exc)) from exc


@router.post("/topics/{topic_id}/items/{item_id}/study/training/actions")
def api_training_action(topic_id: str, item_id: str, body: dict):
    from . import training
    try:
        return training.action(topic_id, item_id, body)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(409, str(exc)) from exc


@router.post("/study/review-sessions")
def api_start_oral_session(body: OralSessionIn):
    try:
        return oral_review.start_session(body.topic_id, body.item_id, body.sentence_index)
    except ValueError as exc:
        raise _err(409, str(exc)) from exc


@router.get("/study/review-sessions/{session_id}")
def api_get_oral_session(session_id: str):
    try:
        return oral_review.get_session(session_id)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(400, str(exc)) from exc


@router.post("/study/review-sessions/{session_id}/actions")
def api_oral_action(session_id: str, body: OralActionIn):
    try:
        return oral_review.session_action(session_id, body.action, body.action_id)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(409, str(exc)) from exc


@router.post("/study/review-sessions/{session_id}/attempts")
def api_oral_attempt(session_id: str, body: OralAttemptIn):
    try:
        return oral_review.submit_attempt(session_id, body.submission_id, body.rating)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(409, str(exc)) from exc


@router.post("/study/review-sessions/{session_id}/recording")
async def api_oral_recording(session_id: str, request: Request, duration_sec: float):
    data = await _arcade_upload(request)
    try:
        return await run_in_threadpool(
            oral_review.save_session_recording, session_id, data, duration_sec,
            request.headers.get("content-type") or "",
        )
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(409, str(exc)) from exc


@router.post("/topics/{topic_id}/items/{item_id}/study/oral-review")
def api_enroll_oral_card(topic_id: str, item_id: str, sentence_index: int = 0):
    try:
        return oral_review.enroll_card(topic_id, item_id, sentence_index)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(409, str(exc)) from exc


@router.get("/topics/{topic_id}/items/{item_id}/study/oral-review")
def api_oral_card_status(topic_id: str, item_id: str, sentence_index: int = 0):
    try:
        return oral_review.get_card_for_sentence(topic_id, item_id, sentence_index)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(400, str(exc)) from exc


@router.patch("/study/review-cards/{card_id}")
def api_pause_oral_card(card_id: str, body: OralCardIn):
    try:
        return oral_review.set_card_paused(card_id, body.paused)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(400, str(exc)) from exc


@router.get("/study/history")
def api_oral_history(day: str | None = None, topic_id: str | None = None,
                     item_id: str | None = None):
    try:
        return oral_review.get_history(day=day, topic_id=topic_id, item_id=item_id)
    except ValueError as exc:
        raise _err(400, str(exc)) from exc


@router.patch("/topics/{topic_id}/items/{item_id}")
def api_update_item(topic_id: str, item_id: str, body: ItemIn):
    """部分更新：只覆盖请求里显式给出的字段，其余文本保持不变。"""
    fields = {
        k: v for k, v in body.model_dump(exclude_unset=True).items()
        if k in library.TEXT_FIELDS
    }
    if not fields:
        raise _err(400, "没有需要更新的字段")
    try:
        return library.update_item_texts(topic_id, item_id, fields)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as e:
        raise _err(400, str(e)) from e


@router.delete("/topics/{topic_id}/items/{item_id}")
def api_delete_item(topic_id: str, item_id: str):
    try:
        library.delete_item(topic_id, item_id)
        return {"ok": True}
    except ValueError as e:
        raise _err(400, str(e)) from e


@router.get("/topics/{topic_id}/items/{item_id}/audio")
@router.get("/topics/{topic_id}/items/{item_id}/audio/{track}")
def api_item_audio(topic_id: str, item_id: str, track: TrackParam = "default"):
    try:
        ipath = library.item_path(topic_id, item_id)
    except ValueError as e:
        raise _err(400, str(e)) from e

    target = library.resolve_audio_file(ipath, track)
    if not target:
        raise _err(404, "音频尚未生成")
    return FileResponse(target, media_type="audio/mpeg")


@router.get("/topics/{topic_id}/items/{item_id}/timeline/{track}")
@router.get("/topics/{topic_id}/items/{item_id}/timeline")
def api_item_timeline(topic_id: str, item_id: str, track: TrackParam = "podcast"):
    try:
        tl = timeline.get_or_create_timeline(topic_id, item_id, track)
    except (FileNotFoundError, ValueError) as e:
        raise _err(404, str(e)) from e
    return tl


# ---------------------------------------------------------------- TTS / jobs

@router.post("/topics/{topic_id}/items/{item_id}/generate")
def api_generate_item(topic_id: str, item_id: str, body: GenerateIn):
    try:
        return jobs.start_generate(topic_id, force=body.force, item_ids=[item_id], track=body.track)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except jobs.JobConflict as e:
        raise _err(409, str(e)) from e
    except (RuntimeError, ValueError) as e:
        raise _err(400, str(e)) from e


@router.post("/topics/{topic_id}/generate")
def api_generate_topic(topic_id: str, body: GenerateIn):
    try:
        return jobs.start_generate(topic_id, force=body.force, track=body.track)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except jobs.JobConflict as e:
        raise _err(409, str(e)) from e
    except (RuntimeError, ValueError) as e:
        raise _err(400, str(e)) from e


@router.get("/jobs")
def api_list_jobs():
    return jobs.list_jobs()


@router.get("/jobs/{job_id}")
def api_get_job(job_id: str):
    job = jobs.get_job(job_id)
    if not job:
        raise _err(404, "任务不存在")
    return job


@router.post("/jobs/{job_id}/cancel")
def api_cancel_job(job_id: str):
    return {"cancelled": jobs.cancel_job(job_id)}


# ---------------------------------------------------------------- episode

@router.post("/topics/{topic_id}/episode")
def api_assemble_episode(topic_id: str, track: TrackParam = "default"):
    """合成改为后台任务（互斥防双击并发 ffmpeg，M05）。"""
    try:
        return jobs.start_assemble(topic_id, track=track)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except jobs.JobConflict as e:
        raise _err(409, str(e)) from e
    except ValueError as exc:
        raise _err(400, str(exc)) from exc


@router.get("/topics/{topic_id}/episode")
def api_episode_manifest(topic_id: str, track: TrackParam = "default"):
    try:
        manifest = assemble.load_manifest(topic_id, track=track)
    except ValueError as e:
        raise _err(400, str(e)) from e
    if not manifest:
        raise _err(404, "本集尚未合成")
    return manifest


@router.get("/topics/{topic_id}/episode/audio")
def api_episode_audio(topic_id: str, track: TrackParam = "default"):
    try:
        path = assemble.episode_path(topic_id, track=track)
    except ValueError as e:
        raise _err(400, str(e)) from e
    if not path.exists():
        raise _err(404, "本集尚未合成")
    return FileResponse(path, media_type="audio/mpeg", filename=path.name)


# ---------------------------------------------------------------- voices

def _local_voice_preview(voice_id: str, text: str, regen: bool = False, *,
                         fixed_sample: bool = False) -> FileResponse:
    settings = load_settings()
    profile_hash = None
    if voice_id == "golden_self":
        try:
            profile_hash = speech_bridge.request(
                settings, "profile_revision", timeout=15,
            ).get("profile_hash")
        except speech_bridge.SpeechError as exc:
            raise _err(503, str(exc)) from exc
        if not profile_hash:
            raise _err(503, "尚未配置母语分身，请先建立声纹")
    key = hashlib.sha256(
        f"v1|{settings.get('speech_engine_dir')}|{voice_id}|{profile_hash}|{text}".encode()
    ).hexdigest()[:24]
    folder = TMP_DIR / "voice_previews"
    folder.mkdir(parents=True, exist_ok=True)
    prefix = "sample-" if fixed_sample else ""
    path = folder / f"{prefix}{voice_id}-{key}.wav"
    if not regen and path.is_file():
        return FileResponse(path, media_type="audio/wav")
    try:
        with _PREVIEW_LOCK:
            if regen or not path.is_file():
                with TemporaryDirectory(prefix="kokoro-preview-", dir=TMP_DIR) as work:
                    output = Path(work) / "preview.wav"
                    speech_bridge.request(
                        settings, "preview_line", voice=voice_id, output=output,
                        profile_hash=profile_hash, text=text,
                    )
                    atomic_replace(output, path)
                    cleanup_voice_previews(folder)
    except speech_bridge.SpeechError as exc:
        raise _err(503, str(exc)) from exc
    except OSError as exc:
        raise _err(503, "本地试听文件写入失败，请重试") from exc
    return FileResponse(path, media_type="audio/wav")


@router.get("/voices")
def api_get_voices(provider: str | None = None, gender: str | None = None):
    voices = production.get_voice_catalog()
    if provider:
        voices = [voice for voice in voices if voice.get("provider") == provider]
    if gender:
        voices = [voice for voice in voices if voice.get("gender") == gender]
    return voices


@router.get("/voices/kokoro_local/{voice_id}/sample")
def api_provider_voice_sample(voice_id: str, regen: bool = False):
    if voice_id not in speech_bridge.VOICES:
        raise _err(404, "本地音色不存在")
    return _local_voice_preview(
        voice_id, "What I like most about it is that it helps me unwind.", regen, fixed_sample=True,
    )


# ---------------------------------------------------------------- settings


def _masked_settings(s: dict) -> dict:
    out = {key: value for key, value in s.items()
           if key in DEFAULT_SETTINGS and not key.endswith("_api_key")
           and key != "scene_sync_token"}
    out["llm_api_key"] = ""
    out["llm_api_key_set"] = bool(real_llm_api_key(s))
    out["vision_api_key_set"] = bool(s.get("vision_api_key"))
    out["scene_sync_configured"] = bool(s.get("scene_sync_token"))
    out["llm_configured"] = is_llm_configured(s)
    out["llm_available"] = out["llm_configured"]
    out["speech_engine_available"] = speech_engine_available(s)
    out["tts_ready"] = out["speech_engine_available"] and not s.get("dry_run", False)
    out["tts_description"] = "Kokoro / Seed-VC 本地离线语音"
    return out


@router.get("/settings")
def api_get_settings():
    return _masked_settings(load_settings())


@router.put("/settings")
def api_put_settings(body: SettingsIn):
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    # 空 key 不覆盖已存 key（脱敏模式下前端回传空串属正常）
    for field in ("llm_api_key", "vision_api_key"):
        if not (update.get(field) or "").strip():
            update.pop(field, None)
    previous_path = load_settings()["speech_engine_dir"] if "speech_engine_dir" in update else None
    saved = save_settings(update)
    if previous_path is not None and saved["speech_engine_dir"] != previous_path:
        speech_bridge.close_workers()
    return _masked_settings(saved)


@router.post("/settings/test")
def api_test_settings(
    provider: Literal["kokoro_local", "llm"] | None = None,
    capability: Literal["tts", "text"] = "tts",
):
    s = load_settings()
    ff_ok, ff_msg = audio.check_ffmpeg()
    selected = provider or ("llm" if capability == "text" else s.get("tts_provider"))
    if selected == "llm":
        try:
            content = rewrite._chat(s, [{"role": "user", "content": 'Reply in JSON: {"ok":true}'}],
                                    None)
            ok = rewrite._extract_json(content).get("ok") is True
            result = {"ok": ok, "message": "文本改写连接成功" if ok else "模型未返回预期的 JSON"}
        except rewrite.RewriteError as exc:
            result = {"ok": False, "message": str(exc)}
        return {"ffmpeg": {"ok": ff_ok, "message": ff_msg}, "llm": result}


    current = speech_bridge.status(s)
    ok = current["available"] and current.get("kokoro", False)
    return {"ffmpeg": {"ok": ff_ok, "message": ff_msg}, "kokoro_local": {
        "ok": ok,
        "message": "本地语音已就绪" if ok else current.get("reason", "缺少 Kokoro 模型"),
    }}


# ---------------------------------------------------------------- exports

@router.post("/topics/{topic_id}/export/m4b")
def api_export_m4b(topic_id: str, track: TrackParam = "podcast"):
    if track == "all":
        raise _err(400, "导出请指定 podcast 或 monologue 轨道")
    try:
        return exports.export_m4b(topic_id, track=track)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except (RuntimeError, audio.FFmpegError, ValueError) as e:
        raise _err(400, str(e)) from e


@router.post("/import-batch")
def api_import_batch(body: dict):
    """批量导入任务包（Markdown），返回 lint 报告。"""
    text = (body or {}).get("text", "")
    try:
        return production.import_batch((body or {}).get("topic", "未命名话题"), text)
    except (FileNotFoundError, RuntimeError) as e:
        raise _err(400, str(e)) from e


@router.post("/lint-script")
def api_lint_script(body: dict):
    text = (body or {}).get("text", "")
    return production.lint_script(text)


@router.get("/stats")
def api_stats():
    topics = library.list_topics()
    total_items = sum(t["stats"]["total"] for t in topics)
    generated = sum(t["stats"]["generated"] for t in topics)
    return {
        "topics": len(topics),
        "items": total_items,
        "generated": generated,
        "ready": sum(t["stats"]["ready"] for t in topics),
        "empty": sum(t["stats"]["empty"] for t in topics),
        "error": sum(t["stats"]["error"] for t in topics),
        "audio_sec": round(sum(t["total_sec"] for t in topics), 1),
    }


@router.get("/search")
def api_search(q: str = "", page: int | None = None, page_size: int = 20):
    """全库搜索：标题/问题/中文/英文子串匹配。"""
    if not q.strip():
        return {"results": []}
    q_lower = q.strip().lower()
    results = []
    fields = ("title", "question", "original_answer", "chinese", "natural_english",
              "monologue_text", "podcast_text", "podcast_script")
    with library.LIB_LOCK:
        for topic in library.topic_dirs():
            name = library.load_topic_name(topic)
            for path in library.item_dirs(topic):
                texts = library.read_item_texts(path)
                texts["title"] = library.item_title(texts, path.name)
                values = [texts.get(field) or "" for field in fields]
                if q_lower not in " ".join(values).lower() or not path.is_dir():
                    continue
                summary = library.item_summary(path)
                matched = next((value for value in values if q_lower in value.lower()), "")
                offset = max(0, matched.lower().find(q_lower) - 45)
                results.append({
                    "topic_id": topic.name, "topic_name": name,
                    "item_id": path.name, "title": summary["title"], "status": summary["status"],
                    "snippet": matched[offset:offset + 180],
                    "has_audio": summary["has_audio"], "study_status": summary.get("study_status"),
                })
    if page is None:
        return {"results": results}
    size = min(100, max(1, page_size))
    total = len(results)
    pages = (total + size - 1) // size
    page = min(max(1, page), max(1, pages))
    return {"results": results[(page - 1) * size:page * size], "total": total,
            "page": page, "pageCount": pages}


@router.get("/topics/{topic_id}/drafts")
def api_content_drafts(topic_id: str):
    try:
        return production.content_drafts(topic_id)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as exc:
        raise _err(400, str(exc)) from exc


# ---------------------------------------------------------------- bank（B01 题库）


class BankAnswerIn(BaseModel):
    question_id: str
    answer: str


@router.get("/bank/questions/{question_id}/answers")
def api_bank_answers(question_id: str):
    try:
        question = bank.find_question(bank.load_bank(), question_id)
    except FileNotFoundError:
        question = None
    if question is None:
        raise _err(404, "题目不存在；已有回答仍在我的语料中。")
    return {"answers": bank.answer_versions().get(bank.norm_title(question["text"]), [])}


@router.get("/bank/questions")
def api_bank_questions(
    part: Literal["all", "1", "2", "3"] | None = None,
    topic: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = bank.PAGE_SIZE,
    random_pick: bool = False,
    random: bool = False,
    set_filter: str | None = None,
    answer_status: Literal["all", "answered", "unanswered"] | None = None,
    training_status: Literal["all", "unstarted", "training", "awaiting_review", "mastered"] = "all",
    exclude_id: str | None = None,
):
    try:
        snapshot = bank.load_bank()
    except FileNotFoundError:
        return {
            "available": False,
            "items": [],
            "total": 0,
            "page": 1,
            "pageCount": 0,
            "topics": [],
            "sets": [],
        }
    part_number = int(part) if part and part != "all" else None
    result = bank.query_questions(
        snapshot,
        answer_status=answer_status,
        training_status=training_status,
        part=part_number,
        topic_id=topic,
        q=q,
        page=page,
        page_size=page_size,
        answered_map=bank.answered_items(),
        random_pick=random_pick or random,
        set_filter=set_filter,
        exclude_id=exclude_id,
    )
    result["available"] = True
    result["topics"] = bank.bank_topics(snapshot, part=part_number)
    # 考季筛选器数据：每个题集在当前 part 下的题数 + 必考题（固定五话题）计数
    part_questions = [
        r for r in snapshot.get("questions", [])
        if (part_number is None or r["part"] == part_number)
        and "原问句缺失" not in (r.get("text") or "")
    ]
    core_tids = bank._core_topic_ids(snapshot)
    sets_out = []
    for s in snapshot.get("sets", []):
        s_ids = set(s.get("question_ids", []))
        n = sum(1 for r in part_questions if r["id"] in s_ids)
        if n:
            sets_out.append(
                {"id": s["id"], "name_zh": s["name_zh"], "short": bank.short_set_label(s),
                 "count": n}
            )
    core_n = sum(1 for r in part_questions if r["topic_id"] in core_tids)
    sets_out.append({"id": "core", "name_zh": "必考题", "short": "必考", "count": core_n})
    result["sets"] = sets_out
    return result


@router.post("/bank/answer")
def api_bank_answer(body: BankAnswerIn):
    try:
        snapshot = bank.load_bank()
    except FileNotFoundError as e:
        raise _err(404, "题库未导入：先运行 python -m server.bank --sync") from e
    question = bank.find_question(snapshot, body.question_id)
    if question is None:
        raise _err(404, "题目不存在")
    if not (question.get("text") or "").strip():
        raise _err(422, "该题目题干缺失，无法入库")
    fields = bank.answer_fields(body.answer)
    if not fields:
        raise _err(422, "回答不能为空")
    # 话题映射：题库话题英文名 == 库内话题名（忽略大小写）→ 复用；否则新建
    topic_name = bank.answer_topic_name(snapshot, question)
    target = library.get_or_create_topic(topic_name)
    created = library.create_item(target["id"], {"question": question["text"], **fields})
    return {
        "topic_id": target["id"],
        "item_id": created["id"],
        "topic_name": target["name"],
        "question": question["text"],
    }


# ------------------------------------------------- generation-requests（R03 统一入口)


class GenerationRequestIn(BaseModel):
    question_id: str | None = None
    question: str | None = None
    topic: str | None = None
    answer: str
    mode: Literal["agent", "api"] = "agent"
    intent: str = ""
    chinese_intent: str = ""
    feedback: str = ""
    blind_token: str | None = None


@router.post("/generation-requests")
def api_generation_requests(body: GenerationRequestIn):
    """统一创建条目：Agent 模式返回可复制指令（绝不调用文本 API），API 模式返回 job。"""
    answer = (body.answer or "").strip()
    if not answer:
        raise _err(422, "回答不能为空")
    if body.mode == "api":
        _require_llm_configured()
    intent = (body.chinese_intent or body.intent).strip()
    if len(intent) > 30000 or len(body.feedback) > 30000:
        raise _err(422, "补充内容过长")
    if body.question_id:
        try:
            snapshot = bank.load_bank()
        except FileNotFoundError as e:
            raise _err(404, "题库未导入：先运行 python -m server.bank --sync") from e
        question = bank.find_question(snapshot, body.question_id)
        if question is None:
            raise _err(404, "题目不存在")
        question_text = (question.get("text") or "").strip()
        if not question_text:
            raise _err(422, "该题目题干缺失，无法入库")
        topic_name = bank.answer_topic_name(snapshot, question)
    elif (body.question or "").strip():
        question_text = body.question.strip()
        topic_name = (body.topic or "").strip()
        if not topic_name:
            raise _err(422, "自定义题目需要同时提供 topic 话题名")
    else:
        raise _err(422, "需要 question_id 或 question")

    target = library.get_or_create_topic(topic_name)
    fields = {"question": question_text, "original_answer": answer, **bank.answer_fields(answer)}
    try:
        with arcade._LOCK if body.blind_token else nullcontext():
            if body.blind_token:
                arcade.check_blind(body.blind_token)
            created = library.create_item(target["id"], fields)
            if body.blind_token:
                arcade.attach_blind(body.blind_token, target["id"], created["id"])
    except ValueError as exc:
        raise _err(400, str(exc)) from exc
    if intent or body.feedback:
        private = study_progress.get_progress(target["id"], created["id"])
        private["training_inputs"] = {"answer": answer, "intent": intent,
                                      "feedback": body.feedback}
        study_progress._write(target["id"], created["id"], private)
    if body.question_id:
        library.update_item_meta(target["id"], created["id"], ielts_part=question.get("part", 1))
    out = {
        "topic_id": target["id"],
        "item_id": created["id"],
        "topic_name": target["name"],
        "mode": body.mode,
        "result_url": f"#/done/{target['id']}/{created['id']}",
    }
    if body.mode == "agent":
        out["agent_prompt"] = _agent_prompt(target["id"], created["id"], question_text, answer)
        return out
    try:
        job = jobs.start_api_generation(target["id"], created["id"], question_text, answer)
    except jobs.JobConflict as e:
        # 原始回答是核心资产：冲突时保留新建条目，只回滚任务启动（宪法"original_answer 永远保存"）
        raise _err(409, f"{e}（你的回答已保存为草稿条目，不会丢失）") from e
    out["job_id"] = job["job_id"]
    return out


def _require_llm_configured() -> None:
    if not is_llm_configured(load_settings()):
        raise _err(422, "当前 AI 改写服务未配置，请前往设置填写 Key 或检查服务地址")


def _agent_prompt(topic_id: str, item_id: str, question: str, answer: str) -> str:
    prompt = rewrite.build_agent_prompt(topic_id, item_id, question, answer)
    inputs = study_progress.get_progress(topic_id, item_id).get("training_inputs") or {}
    if inputs.get("intent") or inputs.get("feedback"):
        prompt += (
            "\n## 独立补充（不属于实际说出的原话）\n中文补充意图：" + inputs.get("intent", "")
            + "\n外部反馈（待核对的建议，不能作为错误证据）：" + inputs.get("feedback", "")
        )
    return prompt


@router.post("/topics/{topic_id}/items/{item_id}/retry-api")
def api_retry_generation(topic_id: str, item_id: str):
    _require_llm_configured()
    try:
        full = library.get_item_full(topic_id, item_id)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(400, str(exc)) from exc
    answer = rewrite.original_answer_of(full)
    question = (full.get("question") or "").strip()
    if not answer or not question:
        raise _err(422, "缺少题目或原始回答，无法重新生成")
    try:
        job = jobs.start_api_generation(topic_id, item_id, question, answer)
    except jobs.JobConflict as exc:
        raise _err(409, str(exc)) from exc
    return {"topic_id": topic_id, "item_id": item_id, "mode": "api", **job,
            "result_url": f"#/done/{topic_id}/{item_id}"}


@router.post("/topics/{topic_id}/items/{item_id}/retry-audio")
def api_retry_audio(topic_id: str, item_id: str):
    try:
        found = study.get_material(topic_id, item_id, allow_pending_audio=True)
        if not found.get("material"):
            raise _err(422, "先准备本题的讲评和问答文本")
        return jobs.start_api_generation(topic_id, item_id, None, None)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(422, str(exc)) from exc
    except jobs.JobConflict as exc:
        raise _err(409, str(exc)) from exc


@router.get("/topics/{topic_id}/items/{item_id}/agent-task")
def api_agent_task(topic_id: str, item_id: str):
    """Agent 任务指令可随时重新获取（刷新/换机器后仍可复制）。"""
    try:
        full = library.get_item_full(topic_id, item_id)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as exc:
        raise _err(400, str(exc)) from exc
    answer = rewrite.original_answer_of(full)
    question = (full.get("question") or "").strip()
    return {
        "topic_id": topic_id,
        "item_id": item_id,
        "question": question,
        "answer": answer,
        "agent_prompt": _agent_prompt(topic_id, item_id, question, answer),
    }


# ---------------------------------------------------------------- pack（B02 手机语料包）


@router.get("/pack/export")
def api_pack_export(topics: str | None = None):
    """导出语料包 zip：topics=all 或逗号分隔话题 id。"""
    topic_ids: list[str] | None = None
    if topics and topics != "all":
        topic_ids = [s.strip() for s in topics.split(",") if s.strip()]
    out = DATA_DIR / "exports" / f"corpus-{uuid.uuid4().hex}.pack.zip"
    try:
        for topic_id in topic_ids or []:
            library.topic_dir(topic_id)
        result = pack.build_pack(out_path=out, topic_ids=topic_ids)
    except FileNotFoundError as e:
        out.unlink(missing_ok=True)
        raise _err(404, str(e)) from e
    except ValueError as exc:
        out.unlink(missing_ok=True)
        raise _err(400, str(exc)) from exc
    except Exception:
        out.unlink(missing_ok=True)
        raise
    return FileResponse(
        result["path"], media_type="application/zip", filename="corpus.pack.zip",
        background=BackgroundTask(out.unlink, missing_ok=True),
    )


@router.get("/exports/{filename}")
def api_download_export(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise _err(400, "非法文件名")
    path = DATA_DIR / "exports" / filename
    if not path.exists():
        raise _err(404, "导出文件不存在")
    media = "audio/mp4" if filename.endswith(".m4b") else "application/octet-stream"
    return FileResponse(path, media_type=media, filename=filename)


@router.post("/topics/{topic_id}/items/{item_id}/export/vtt")
def api_export_vtt(topic_id: str, item_id: str, track: TrackParam = "podcast"):
    try:
        return exports_media.export_vtt(topic_id, item_id, track=track)
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        raise _err(400, str(e)) from e


@router.post("/topics/{topic_id}/items/{item_id}/export/lrc")
def api_export_lrc(topic_id: str, item_id: str, track: TrackParam = "podcast"):
    try:
        return exports_media.export_lrc(topic_id, item_id, track=track)
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        raise _err(400, str(e)) from e


@router.post("/topics/{topic_id}/items/{item_id}/export/srt")
def api_export_srt(topic_id: str, item_id: str, track: TrackParam = "podcast"):
    try:
        return exports_media.export_srt(topic_id, item_id, track=track)
    except (FileNotFoundError, RuntimeError, ValueError) as e:
        raise _err(400, str(e)) from e


@router.get("/rss.xml")
def api_rss(request: Request):
    base = str(request.base_url).rstrip("/")
    return Response(content=exports_media.build_rss(base), media_type="application/xml")


# ---------------------------------------------------------------- rewrite request

@router.get("/topics/{topic_id}/items/{item_id}/rewrite-request")
def api_rewrite_request(topic_id: str, item_id: str):
    try:
        item = library.get_item_full(topic_id, item_id)
    except (FileNotFoundError, ValueError) as e:
        raise _err(404, str(e)) from e
    template_file = PROMPTS_DIR / "promptA_zh_to_natural_english.md"
    if template_file.exists():
        template = template_file.read_text(encoding="utf-8")
    else:  # pragma: no cover
        template = "QUESTION:\n{{IELTS_QUESTION}}\n\nMY CHINESE ANSWER:\n{{CHINESE_ANSWER}}"
    text = template.replace("{{IELTS_QUESTION}}", item.get("question") or "(未填写问题)")
    text = text.replace("{{CHINESE_ANSWER}}", item.get("chinese") or "(未填写中文回答)")
    return {"text": text}


@router.get("/topics/{topic_id}/items/{item_id}/voice-direct-request")
def api_voice_direct_request(topic_id: str, item_id: str):
    """把 Prompt B 模板与 Natural English 拼好，供粘贴给 AI 生成 Fish Script。"""
    try:
        item = library.get_item_full(topic_id, item_id)
    except (FileNotFoundError, ValueError) as e:
        raise _err(404, str(e)) from e
    template_file = PROMPTS_DIR / "promptB_voice_direct.md"
    if not (item.get("natural_english") or "").strip():
        raise _err(400, "请先填写 Natural English")
    if template_file.exists():
        template = template_file.read_text(encoding="utf-8")
    else:  # pragma: no cover
        template = "TEXT:\n{{NATURAL_ENGLISH}}"
    text = template.replace("{{NATURAL_ENGLISH}}", item["natural_english"])
    text = text.replace("{{IELTS_QUESTION}}", item.get("question") or "(Question not provided)")
    return {"text": text}


# ---------------------------------------------------------------- 私有素材


class SnippetIn(BaseModel):
    text: str = ""
    images: list[str] | None = None
    title: str = ""
    source_url: str = ""
    note: str = ""


class ApproveCardIn(BaseModel):
    goal_type: Literal["activate_chunk", "comprehend_input", "fix_error", "fill_gap"] | None = None


class CaptureGradeIn(BaseModel):
    rating: Literal["good", "again", "easy", "suspend"]
    submission_id: str
    source_fingerprint: str | None = None


class ScenePairingIn(BaseModel):
    reset: bool = False


@router.post("/settings/scene-sync-token")
def api_scene_sync_token(body: ScenePairingIn):
    with _PAIRING_LOCK:
        token = load_settings()["scene_sync_token"]
        if body.reset or not isinstance(token, str) or not token:
            token = secrets.token_urlsafe(24)
            save_settings({"scene_sync_token": token})
    return JSONResponse({"token": token}, headers={"Cache-Control": "no-store"})


async def _scene_request(request: Request, *, backup: bool) -> dict:
    body = bytearray()
    try:
        if int(request.headers.get("content-length", "0")) > captures.BACKUP_MAX:
            raise HTTPException(413, "备份须小于等于 150 MiB")
        async for chunk in request.stream():
            if len(body) + len(chunk) > captures.BACKUP_MAX:
                raise HTTPException(413, "备份须小于等于 150 MiB")
            body.extend(chunk)
        payload = await run_in_threadpool(json.loads, body)
        if not isinstance(payload, dict):
            raise ValueError("备份格式无效")
        if backup and (payload.get("format") != "caption-study-backup"
                       or type(payload.get("schemaVersion")) is not int
                       or payload["schemaVersion"] != 1):
            raise ValueError("请选择看剧脚本导出的 v1 JSON 备份")
        return await run_in_threadpool(captures.ingest_scenes, payload.get("notes"))
    except (ValueError, RecursionError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/captures/scenes/ping")
def api_scene_ping():
    return {"ok": True}


@router.post("/captures/scenes/inbox")
async def api_scene_inbox(request: Request):
    return await _scene_request(request, backup=False)


@router.post("/captures/scenes/import-json")
async def api_scene_import(request: Request):
    return await _scene_request(request, backup=True)


@router.post("/captures/snippet")
def api_capture_snippet(body: SnippetIn):
    try:
        return captures.ingest_snippet(**body.model_dump())
    except ValueError as exc:
        raise _err(422, str(exc)) from exc


@router.get("/captures")
def api_list_captures():
    return {"captures": captures.list_captures()}


@router.post("/captures/distill-pending")
def api_distill_pending():
    try:
        return jobs.start_capture_job("capture_distill", capture_distill.pending_ids())
    except ValueError as exc:
        raise _err(422, str(exc)) from exc
    except jobs.JobConflict as exc:
        raise _err(409, str(exc)) from exc


@router.get("/captures/agent-task")
def api_capture_agent_task():
    return {"prompt": capture_distill.build_agent_prompt()}


@router.get("/captures/{capture_id}")
def api_get_capture(capture_id: str):
    try:
        return captures.get_capture(capture_id)
    except (FileNotFoundError, ValueError) as exc:
        raise _err(404, str(exc)) from exc


@router.delete("/captures/{capture_id}")
def api_delete_capture(capture_id: str):
    try:
        captures.delete_capture(capture_id)
    except (FileNotFoundError, ValueError) as exc:
        raise _err(404, str(exc)) from exc
    return {"deleted": True}


@router.get("/captures/{capture_id}/assets/{name}")
def api_capture_asset(capture_id: str, name: str):
    try:
        path, mime = captures.asset_file(capture_id, name)
    except (FileNotFoundError, ValueError) as exc:
        raise _err(404, str(exc)) from exc
    return FileResponse(path, media_type=mime, headers={"Cache-Control": "private, no-store",
                                                        "X-Content-Type-Options": "nosniff"})


@router.post("/captures/{capture_id}/distill")
def api_distill_capture(capture_id: str):
    api_get_capture(capture_id)
    try:
        return jobs.start_capture_job("capture_distill", [capture_id])
    except jobs.JobConflict as exc:
        raise _err(409, str(exc)) from exc


@router.get("/cards")
def api_list_cards(status: Literal["inbox", "active", "archived"] | None = None,
                   source_type: Literal["scene", "snippet", "chat"] | None = None,
                   capture_id: str | None = None, q: str = ""):
    try:
        return {"cards": captures.list_cards(status, source_type, capture_id, q)}
    except (FileNotFoundError, ValueError) as exc:
        raise _err(404, str(exc)) from exc


@router.patch("/cards/{card_id}")
def api_patch_card(card_id: str, patch: dict):
    allowed = {*captures.CARD_FIELDS, "disambiguator", "goal_type", "original_error"}
    try:
        return captures.update_card(card_id, {key: patch[key] for key in patch if key in allowed})
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(422, str(exc)) from exc


@router.post("/cards/{card_id}/approve")
def api_approve_card(card_id: str, body: ApproveCardIn | None = None):
    try:
        row = captures.approve_card(card_id, goal_type=body.goal_type if body else None)
        oral_review.enroll_capture_card(row["capture_id"], card_id)
        job = jobs.start_capture_job("capture_audio", [card_id])
        return {**row, **job}
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(422, str(exc)) from exc


@router.post("/cards/{card_id}/archive")
def api_archive_card(card_id: str):
    try:
        return oral_review.suspend_card(card_id)
    except (FileNotFoundError, ValueError) as exc:
        raise _err(404, str(exc)) from exc


@router.post("/cards/{card_id}/grade")
def api_grade_card(card_id: str, body: CaptureGradeIn):
    try:
        return oral_review.grade_capture_card(card_id, body.rating, body.submission_id,
                                              body.source_fingerprint)
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(422, str(exc)) from exc


@router.get("/cards/{card_id}/audio")
def api_capture_audio(card_id: str):
    try:
        row = captures.get_card(card_id)
        if row["status"] != "active":
            raise FileNotFoundError("卡片尚未确认入库")
        captures.synthesize_card_audio(row["capture_id"], card_id)
        return FileResponse(captures.audio_file(card_id), media_type="audio/mpeg",
                            headers={"Cache-Control": "private, no-cache"})
    except (FileNotFoundError, ValueError) as exc:
        raise _err(404, str(exc)) from exc
    except (OSError, RuntimeError) as exc:
        raise _err(503, str(exc)) from exc


@router.get("/cards/{card_id}/voice/{voice}")
def api_capture_voice(card_id: str, voice: Literal["am_puck", "af_bella", "golden_self"]):
    try:
        row = captures.get_card(card_id)
        if row["status"] != "active":
            raise FileNotFoundError("卡片尚未确认入库")
        return _local_voice_preview(voice, row["en"])
    except (FileNotFoundError, ValueError) as exc:
        raise _err(404, str(exc)) from exc


@router.post("/cards/{card_id}/check-transfer")
async def api_capture_transfer(card_id: str, request: Request, duration_sec: float):
    data = await _arcade_upload(request)
    try:
        return await run_in_threadpool(
            arcade.check_card_transfer, card_id, data,
            request.headers.get("content-type", ""), duration_sec,
        )
    except FileNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ValueError as exc:
        raise _err(422, str(exc)) from exc
    except speech_bridge.SpeechError as exc:
        raise _err(503, str(exc)) from exc
