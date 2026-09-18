"""Agent 自动化管线调度脚本 (pipeline.py)。

用于由 Agent 或脚本直接将编写好的双轨文本存入本地系统，并调用 TTS 渲染音频。
"""
import argparse
import sys
from pathlib import Path

# 确保导入当前 server 包
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from server import library, tts


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
    parser.add_argument("--topic", required=True, help="Topic name")
    parser.add_argument("--question", required=True, help="Question or Title")
    parser.add_argument("--chinese-file", help="Path to Chinese text file")
    parser.add_argument("--monologue-file", help="Path to Monologue text file")
    parser.add_argument("--podcast-file", help="Path to Podcast dialogue text file")
    parser.add_argument(
        "--track", default="all", choices=["all", "monologue", "podcast", "default"]
    )
    parser.add_argument("--no-audio", action="store_true", help="Skip TTS synthesis")

    args = parser.parse_args()

    zh = Path(args.chinese_file).read_text(encoding="utf-8") if args.chinese_file else ""
    mono = Path(args.monologue_file).read_text(encoding="utf-8") if args.monologue_file else ""
    pod = Path(args.podcast_file).read_text(encoding="utf-8") if args.podcast_file else ""

    res = ingest_and_generate(
        topic_name=args.topic,
        question=args.question,
        chinese=zh,
        monologue_text=mono,
        monologue_script=mono,
        podcast_text=pod,
        podcast_script=pod,
        generate_audio=not args.no_audio,
        track=args.track,
    )
    print("Pipeline finished successfully:", res["item_id"])


if __name__ == "__main__":
    main()
