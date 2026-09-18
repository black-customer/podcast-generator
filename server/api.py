"""HTTP API 路由。"""
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from . import assemble, audio, jobs, library, timeline, tts
from .config import (
    DATA_DIR,
    FISH_MODELS,
    PROMPTS_DIR,
    is_dry_run,
    load_settings,
    real_api_key,
    save_settings,
)

router = APIRouter(prefix="/api")

TrackParam = Literal["default", "monologue", "podcast"]


class TopicIn(BaseModel):
    name: str


class ItemIn(BaseModel):
    question: str = ""
    chinese: str = ""
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
    fish_api_key: str | None = None
    reference_id: str | None = None
    reference_id_b: str | None = None
    model: str | None = None
    speed: float | None = None
    segment_chars: int | None = None
    gap_ms: float | None = None
    episode_gap_ms: float | None = None
    dry_run: bool | None = None
    temperature: float | None = None

    @field_validator("speed")
    @classmethod
    def _v_speed(cls, v: float | None) -> float | None:
        if v is not None and not 0.5 <= v <= 2.0:
            raise ValueError("speed 必须在 0.5–2.0")
        return v

    @field_validator("temperature")
    @classmethod
    def _v_temperature(cls, v: float | None) -> float | None:
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError("temperature 必须在 0–1")
        return v

    @field_validator("segment_chars")
    @classmethod
    def _v_segment_chars(cls, v: int | None) -> int | None:
        if v is not None and not 100 <= v <= 5000:
            # <=0 会让 split_text 陷入无限循环；过小则碎片化
            raise ValueError("segment_chars 必须在 100–5000")
        return v

    @field_validator("gap_ms", "episode_gap_ms")
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
        "ffmpeg": {"ok": ok, "message": msg},
        "mode": "dry_run" if is_dry_run() else "live",
        "data_dir": str(DATA_DIR),
    }


# ---------------------------------------------------------------- topics

@router.get("/topics")
def api_list_topics():
    return library.list_topics()


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
    for line in body.text.splitlines():
        line = line.strip()
        if line:
            created.append(library.create_item(topic_id, {"question": line}))
    return {"created": len(created), "items": created}


@router.get("/topics/{topic_id}/items/{item_id}")
def api_get_item(topic_id: str, item_id: str):
    try:
        return library.get_item_full(topic_id, item_id)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except ValueError as e:
        raise _err(400, str(e)) from e


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
    except (FileNotFoundError, RuntimeError) as e:
        raise _err(400, str(e)) from e


@router.post("/topics/{topic_id}/generate")
def api_generate_topic(topic_id: str, body: GenerateIn):
    try:
        return jobs.start_generate(topic_id, force=body.force, track=body.track)
    except (FileNotFoundError, RuntimeError) as e:
        raise _err(400, str(e)) from e


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
    try:
        return assemble.assemble_episode(topic_id, track=track)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except (RuntimeError, audio.FFmpegError) as e:
        raise _err(400, str(e)) from e


@router.get("/topics/{topic_id}/episode")
def api_episode_manifest(topic_id: str, track: TrackParam = "default"):
    manifest = assemble.load_manifest(topic_id, track=track)
    if not manifest:
        raise _err(404, "本集尚未合成")
    return manifest


@router.get("/topics/{topic_id}/episode/audio")
def api_episode_audio(topic_id: str, track: TrackParam = "default"):
    path = assemble.episode_path(topic_id, track=track)
    if not path.exists():
        # fallback to default
        path = assemble.episode_path(topic_id, track="default")
        if not path.exists():
            raise _err(404, "本集尚未合成")
    return FileResponse(path, media_type="audio/mpeg", filename=path.name)


# ---------------------------------------------------------------- voices

@router.get("/voices")
def api_get_voices():
    return library.read_voices()


# ---------------------------------------------------------------- settings


def _masked_settings(s: dict) -> dict:
    """对外脱敏：永不回传明文 API key（含 models 列表）。"""
    out = dict(s)
    out["fish_api_key"] = ""
    out["fish_api_key_set"] = bool(real_api_key(s))
    out["models"] = FISH_MODELS
    return out


@router.get("/settings")
def api_get_settings():
    return _masked_settings(load_settings())


@router.put("/settings")
def api_put_settings(body: SettingsIn):
    update = {k: v for k, v in body.model_dump().items() if v is not None}
    # 空 key 不覆盖已存 key（脱敏模式下前端回传空串属正常）
    if "fish_api_key" in update and not (update["fish_api_key"] or "").strip():
        update.pop("fish_api_key")
    saved = save_settings(update)
    return _masked_settings(saved)


@router.post("/settings/test")
def api_test_settings():
    s = load_settings()
    ff_ok, ff_msg = audio.check_ffmpeg()
    return {
        "ffmpeg": {"ok": ff_ok, "message": ff_msg},
        "fish": tts.test_connection(s),
    }


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
    return {"text": text}
