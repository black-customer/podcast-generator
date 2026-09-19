"""HTTP API 路由。"""
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, field_validator

from . import (
    assemble,
    audio,
    bank,
    exports,
    exports_media,
    jobs,
    library,
    pack,
    production,
    timeline,
    tts,
)
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
    answer_voice_male: bool | None = None

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


@router.get("/voices/{ref_id}/sample")
def api_voice_sample(ref_id: str, regen: bool = False):
    """音色试听：现场合成优先（真实管线、所点音色）并缓存；官方样本仅作回退。

    克隆音色的官方 samples 常是基模型的声音，与实际合成听感不符（展台会误导）；
    因此默认用该 ref 现场合成一句（1 次免费调用，结果落缓存）。regen=1 强制重合成。
    """
    import logging

    import httpx

    from server.config import FISH_MODELS_URL, real_api_key

    logger = logging.getLogger(__name__)
    ref_id = ref_id.strip()
    if not re.fullmatch(r"[0-9a-f]{16,64}", ref_id):
        raise _err(400, "非法的音色 id")

    cache = DATA_DIR / "voice_samples" / f"{ref_id}.mp3"
    if not regen and cache.exists() and cache.stat().st_size > 1000:
        return FileResponse(cache, media_type="audio/mpeg")

    s = load_settings()
    key = real_api_key(s)

    # 1) 现场合成一句（与真实生成同管线——听感即所得）
    if key and not is_dry_run(s):
        try:
            audio_bytes = tts.fish_tts_segment(
                "Hi there! This is a short preview of my voice. Pretty natural, right?",
                s,
                reference_id=ref_id,
            )
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(audio_bytes)
            return FileResponse(cache, media_type="audio/mpeg")
        except tts.TTSError as e:
            logger.warning("现场合成试听失败，回退官方样本: %s", e)

    # 2) 官方样本回退（合成不可用：dry-run/无 key/失败）。不落缓存——
    #    克隆音色的官方样本可能并非本音色，缓存会永久遮蔽真实合成结果
    try:
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        detail = httpx.get(f"{FISH_MODELS_URL}/{ref_id}", headers=headers, timeout=30)
        if detail.status_code == 200:
            samples = detail.json().get("samples") or []
            if samples:
                url = samples[0].get("audio")
                if url:
                    up = httpx.get(url, timeout=60, follow_redirects=True)
                    if up.status_code == 200 and len(up.content) > 1000:
                        return Response(
                            content=up.content,
                            media_type="audio/mpeg",
                            headers={"Cache-Control": "no-store"},
                        )
    except httpx.HTTPError:
        logger.warning("拉取官方样本也失败", exc_info=True)
    raise _err(502, "试听生成失败（合成不可用且官方样本缺失）")


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


# ---------------------------------------------------------------- exports

@router.post("/topics/{topic_id}/export/m4b")
def api_export_m4b(topic_id: str, track: TrackParam = "podcast"):
    if track == "all":
        raise _err(400, "导出请指定 podcast 或 monologue 轨道")
    try:
        return exports.export_m4b(topic_id, track=track)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    except (RuntimeError, audio.FFmpegError) as e:
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
def api_search(q: str = ""):
    """全库搜索：标题/问题/中文/英文子串匹配。"""
    if not q.strip():
        return {"results": []}
    q_lower = q.strip().lower()
    results = []
    for t in library.list_topics():
        for it in (library.get_topic(t["id"]).get("items") or []):
            full = library.get_item_full(t["id"], it["id"])
            fields = ("title", "question", "chinese", "natural_english", "monologue_text")
            blob = " ".join((full.get(f, "") or "") for f in fields).lower()
            if q_lower in blob:
                results.append({
                    "topic_id": t["id"], "topic_name": t["name"],
                    "item_id": it["id"], "title": it["title"], "status": it["status"],
                })
    return {"results": results}


@router.get("/topics/{topic_id}/drafts")
def api_content_drafts(topic_id: str):
    try:
        return production.content_drafts(topic_id)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e


# ---------------------------------------------------------------- bank（B01 题库）


class BankAnswerIn(BaseModel):
    question_id: str
    answer: str


@router.get("/bank/questions")
def api_bank_questions(
    part: int | None = None,
    topic: str | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = bank.PAGE_SIZE,
    random_pick: bool = False,
    set_filter: str | None = None,
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
    result = bank.query_questions(
        snapshot,
        part=part,
        topic_id=topic,
        q=q,
        page=page,
        page_size=page_size,
        answered_map=bank.answered_items(),
        random_pick=random_pick,
        set_filter=set_filter,
    )
    result["available"] = True
    result["topics"] = bank.bank_topics(snapshot, part=part)
    # 考季筛选器数据：每个题集在当前 part 下的题数 + 必考题（固定五话题）计数
    part_questions = [
        r for r in snapshot.get("questions", []) if part is None or r["part"] == part
    ]
    core_tids = bank._core_topic_ids(snapshot)
    sets_out = []
    for s in snapshot.get("sets", []):
        s_ids = set(s.get("question_ids", []))
        n = sum(1 for r in part_questions if r["id"] in s_ids)
        if n:
            sets_out.append(
                {"id": s["id"], "name_zh": s["name_zh"], "short": s["short"], "count": n}
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
    target = next(
        (t for t in library.list_topics() if t["name"].strip().casefold() == topic_name.casefold()),
        None,
    )
    if target is None:
        target = library.create_topic(topic_name)
    created = library.create_item(target["id"], {"question": question["text"], **fields})
    return {
        "topic_id": target["id"],
        "item_id": created["id"],
        "topic_name": target["name"],
        "question": question["text"],
    }


# ---------------------------------------------------------------- pack（B02 手机语料包）


@router.get("/pack/export")
def api_pack_export(topics: str | None = None):
    """导出语料包 zip：topics=all 或逗号分隔话题 id。"""
    topic_ids: list[str] | None = None
    if topics and topics != "all":
        topic_ids = [s.strip() for s in topics.split(",") if s.strip()]
    try:
        result = pack.build_pack(topic_ids=topic_ids)
    except FileNotFoundError as e:
        raise _err(404, str(e)) from e
    return FileResponse(
        result["path"], media_type="application/zip", filename="corpus.pack.zip"
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
    except (FileNotFoundError, RuntimeError) as e:
        raise _err(400, str(e)) from e


@router.post("/topics/{topic_id}/items/{item_id}/export/lrc")
def api_export_lrc(topic_id: str, item_id: str, track: TrackParam = "podcast"):
    try:
        return exports_media.export_lrc(topic_id, item_id, track=track)
    except (FileNotFoundError, RuntimeError) as e:
        raise _err(400, str(e)) from e


@router.post("/topics/{topic_id}/items/{item_id}/export/srt")
def api_export_srt(topic_id: str, item_id: str, track: TrackParam = "podcast"):
    try:
        return exports_media.export_srt(topic_id, item_id, track=track)
    except (FileNotFoundError, RuntimeError) as e:
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
    return {"text": text}
