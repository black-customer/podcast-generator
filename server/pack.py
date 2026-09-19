"""语料包导出（B02 手机 APP）。

把话题条目（文本 + 时间轴 + 音频）与题库快照打成一个 ZIP_STORED 包，
手机 APP 导入后离线全功能。store 不压缩：mp3 本身不可压缩，且让前端
零依赖解析 zip（web/packreader.js 只读目录结构与原始字节）。

包结构：
  pack.json                                     # manifest（版本/导出时间/内容哈希/条目索引）
  bank.json                                     # 题库快照（存在才带）
  topics/<tid>/items/<iid>/item.json            # 文本 + meta + 预计算时间轴 {lines,words,mode}
  topics/<tid>/items/<iid>/audio_<track>.mp3    # 音频（存在才带）
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from . import library
from .config import DATA_DIR

PACK_VERSION = 1
AUDIO_TRACKS = ("default", "monologue", "podcast")


def _item_payload(d: Path, topic_id: str, item_id: str) -> dict:
    """单条目入包内容：文本、meta、双轨预计算时间轴。

    时间轴在导出时由服务端按 alignment→缓存→估算 的优先级预计算成
    {lines, words, mode} 响应体（指纹校验同样在服务端完成），
    手机端零逻辑直接消费，不丢逐词卡拉OK数据。
    """
    from . import timeline as timeline_mod

    payload: dict = {"texts": library.read_item_texts(d)}
    meta_file = d / "meta.json"
    if meta_file.exists():
        try:
            payload["meta"] = json.loads(meta_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload["meta"] = {}
    timelines: dict[str, dict] = {}
    for track in ("monologue", "podcast"):
        try:
            resp = timeline_mod.get_or_create_timeline(topic_id, item_id, track)
        except Exception:
            continue
        if resp and resp.get("lines"):
            timelines[track] = resp
    if timelines:
        payload["timelines"] = timelines
    return payload


def build_pack(out_path: Path | None = None, topic_ids: list[str] | None = None) -> dict:
    """导出语料包（整文件原子性由调用方临时文件保证；此处直接写目标）。

    topic_ids=None 导出全部话题。返回 manifest 与落盘路径；
    content_hash 覆盖条目与索引内容（同数据同哈希，幂等校验用）。
    """
    topics = library.list_topics()
    if topic_ids is not None:
        wanted = set(topic_ids)
        topics = [t for t in topics if t["id"] in wanted]
        missing = wanted - {t["id"] for t in topics}
        if missing:
            raise FileNotFoundError(f"话题不存在：{sorted(missing)}")

    exports_dir = DATA_DIR / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    out = Path(out_path) if out_path else exports_dir / "corpus.pack.zip"

    manifest: dict = {
        "pack_version": PACK_VERSION,
        "generator": "podcastGenerate",
        "topics": [],
    }
    hasher = hashlib.sha256()

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as zf:
        for t in topics:
            full = library.get_topic(t["id"])
            topic_entry = {"id": t["id"], "name": t["name"], "items": []}
            for it in full.get("items", []):
                d = library.item_path(t["id"], it["id"])
                payload = _item_payload(d, t["id"], it["id"])
                payload["id"] = it["id"]
                payload["title"] = it.get("title") or it["id"]
                audios: dict[str, str] = {}
                for track in AUDIO_TRACKS:
                    p = library.resolve_audio_file(d, track=track)
                    if p is not None:
                        zf.write(p, f"topics/{t['id']}/items/{it['id']}/audio_{track}.mp3")
                        audios[track] = f"audio_{track}.mp3"
                payload["audio"] = audios
                content = json.dumps(payload, ensure_ascii=False)
                zf.writestr(f"topics/{t['id']}/items/{it['id']}/item.json", content)
                hasher.update(content.encode("utf-8"))
                topic_entry["items"].append({"id": it["id"], "title": it.get("title") or it["id"]})
            manifest["topics"].append(topic_entry)
            hasher.update(json.dumps(topic_entry, ensure_ascii=False).encode("utf-8"))

        bank_path = DATA_DIR / "question_bank.json"
        if bank_path.exists():
            zf.write(bank_path, "bank.json")
            manifest["has_bank"] = True

        manifest["content_hash"] = hasher.hexdigest()[:16]
        manifest["counts"] = {
            "topics": len(manifest["topics"]),
            "items": sum(len(t["items"]) for t in manifest["topics"]),
        }
        zf.writestr("pack.json", json.dumps(manifest, ensure_ascii=False, indent=1))

    return {"manifest": manifest, "path": out, "size_bytes": out.stat().st_size}
