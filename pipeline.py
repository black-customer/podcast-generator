"""Agent 自动化管线调度脚本 (pipeline.py)。

用于由 Agent 或脚本直接将编写好的双轨文本存入本地系统，并调用 TTS 渲染音频。
R03 新增 `complete` 子命令：Agent 模式的固定完成入口（先校验，再原子写入，后合成）。
"""
import argparse
import json
import sys
from pathlib import Path

# 确保导入当前 server 包
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server import library, rewrite, study, tts

DEFAULT_BASE_URL = "http://127.0.0.1:8765"


class CompleteError(RuntimeError):
    pass


def complete_item(
    topic_id: str,
    item_id: str,
    result: dict,
    generate_audio: bool = True,
    base_url: str = DEFAULT_BASE_URL,
) -> dict:
    """Agent 三份文本的统一落盘入口：先校验再原子写入，最后按当前 provider 合成。

    校验失败抛 CompleteError，不产生任何部分写入，也不触碰音频。
    """
    texts = {
        field: str(result.get(field) or "").strip()
        for field in rewrite.REQUIRED_FIELDS
    }
    errors = rewrite.validate_texts(texts)
    if errors:
        raise CompleteError("改写结果校验未通过:\n- " + "\n- ".join(errors))
    try:
        library.item_path(topic_id, item_id)
        library.update_item_texts(topic_id, item_id, texts)
    except FileNotFoundError as exc:
        raise CompleteError(f"目标条目不存在: {exc}") from exc
    mp3_path = ""
    if generate_audio:
        tts.generate_item_audio(topic_id, item_id, track="podcast")
        mp3_path = str(library.item_path(topic_id, item_id) / "audio_podcast.mp3")
    return {
        "topic_id": topic_id,
        "item_id": item_id,
        "play_url": f"{base_url.rstrip('/')}/#/done/{topic_id}/{item_id}",
        "mp3_path": mp3_path,
    }


def ingest_and_generate(
    topic_name: str,
    question: str,
    chinese: str,
    monologue_text: str = "",
    monologue_script: str = "",
    podcast_text: str = "",
    podcast_script: str = "",
    generate_audio: bool = True,
    track: str = "all",
) -> dict:
    """Agent 一键存入并生成音频的主函数。"""
    # 查找或新建 topic
    topics = library.list_topics()
    target_topic_id = None
    for t in topics:
        if t["name"].strip().lower() == topic_name.strip().lower() or t["id"] == topic_name:
            target_topic_id = t["id"]
            break

    if not target_topic_id:
        t_info = library.create_topic(topic_name)
        target_topic_id = t_info["id"]

    # 查找是否已有同名 question 的 item，否则创建
    t_full = library.get_topic(target_topic_id)
    target_item_id = None
    for it in t_full.get("items", []):
        if it["title"].strip().lower() == question.strip().lower() or it["id"] == question:
            target_item_id = it["id"]
            break

    fields = {
        "question": question,
        "chinese": chinese,
        "natural_english": monologue_text or podcast_text,
        "fish_script": monologue_script or podcast_script,
        "monologue_text": monologue_text,
        "monologue_script": monologue_script,
        "podcast_text": podcast_text,
        "podcast_script": podcast_script,
    }

    if not target_item_id:
        it_info = library.create_item(target_topic_id, fields)
        target_item_id = it_info["id"]
    else:
        library.update_item_texts(target_topic_id, target_item_id, fields)

    gen_result = None
    if generate_audio:
        gen_result = tts.generate_item_audio(target_topic_id, target_item_id, track=track)

    item_full = library.get_item_full(target_topic_id, target_item_id)
    return {
        "topic_id": target_topic_id,
        "item_id": target_item_id,
        "tts_result": gen_result,
        "item": item_full,
    }


def main():
    parser = argparse.ArgumentParser(description="Podcast Pipeline Runner")
    sub = parser.add_subparsers(dest="command")

    # 旧入口：一次性 ingest + 生成
    legacy = sub.add_parser("ingest", help="一次性写入双轨文本并生成音频")
    legacy.add_argument("--topic", required=True, help="Topic name")
    legacy.add_argument("--question", required=True, help="Question or Title")
    legacy.add_argument("--chinese-file", help="Path to Chinese text file")
    legacy.add_argument("--monologue-file", help="Path to Monologue text file")
    legacy.add_argument("--podcast-file", help="Path to Podcast dialogue text file")
    legacy.add_argument(
        "--track", default="all", choices=["all", "monologue", "podcast", "default"]
    )
    legacy.add_argument("--no-audio", action="store_true", help="Skip TTS synthesis")

    # R03：Agent 模式固定完成入口
    comp = sub.add_parser("complete", help="写入 Agent 三份文本并合成音频（先校验）")
    comp.add_argument("--topic-id", required=True)
    comp.add_argument("--item-id", required=True)
    comp.add_argument("--result-json", required=True, help="三份文本 JSON 文件路径，- 表示 stdin")
    comp.add_argument("--base-url", default=DEFAULT_BASE_URL, help="播放页基础 URL")
    comp.add_argument("--no-audio", action="store_true", help="只写文本，不合成")

    mat = sub.add_parser("study", help="提交独立逐句学习材料（音频完成后）")
    mat.add_argument("--topic-id", required=True)
    mat.add_argument("--item-id", required=True)
    mat.add_argument("--result-json", required=True, help="逐句材料 JSON 文件路径，- 表示 stdin")

    args = parser.parse_args()
    if args.command == "study":
        raw = sys.stdin.read() if args.result_json == "-" else Path(args.result_json).read_text(
            encoding="utf-8"
        )
        try:
            result = json.loads(raw)
            saved = study.save_material(args.topic_id, args.item_id, result)
        except (json.JSONDecodeError, ValueError, FileNotFoundError) as exc:
            print(f"FAILED: {exc}", file=sys.stderr)
            return 2
        print(f"STUDY READY: {len(saved['sentences'])} sentences")
        return 0
    if args.command == "complete":
        raw = (
            sys.stdin.read()
            if args.result_json == "-"
            else Path(args.result_json).read_text(encoding="utf-8")
        )
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"result-json 不是合法 JSON: {exc}", file=sys.stderr)
            return 2
        if not isinstance(result, dict):
            print("result-json 顶层必须是 JSON 对象", file=sys.stderr)
            return 2
        try:
            done = complete_item(
                args.topic_id,
                args.item_id,
                result,
                generate_audio=not args.no_audio,
                base_url=args.base_url,
            )
        except CompleteError as exc:
            print(f"FAILED: {exc}", file=sys.stderr)
            return 2
        print("COMPLETE")
        print(f"play_url: {done['play_url']}")
        if done["mp3_path"]:
            print(f"mp3_path: {done['mp3_path']}")
        return 0
    if args.command == "ingest":
        def _read(name: str) -> str:
            path = getattr(args, name, None)
            return Path(path).read_text(encoding="utf-8") if path else ""

        mono = _read("monologue_file")
        pod = _read("podcast_file")
        res = ingest_and_generate(
            topic_name=args.topic,
            question=args.question,
            chinese=_read("chinese_file"),
            monologue_text=mono,
            monologue_script=mono,
            podcast_text=pod,
            podcast_script=pod,
            generate_audio=not args.no_audio,
            track=args.track,
        )
        print("Pipeline finished successfully:", res["item_id"])
        return 0

    if args.command is None:
        parser.error("请使用子命令：pipeline.py ingest ... 或 pipeline.py complete ...")
    return 2


if __name__ == "__main__":
    main()
