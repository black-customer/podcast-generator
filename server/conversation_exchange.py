"""手机与电脑 Agent 的个人任务交换：保留原文，严格核对引用，不触发收费请求。"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path


def _conversation(document: dict, conversation_id: str) -> dict:
    if (document.get("version") != 1
            or document.get("type") != "personal_learning_exchange"):
        raise ValueError("个人交换文件版本不受支持")
    conversation = document.get("conversations", {}).get(conversation_id)
    if not isinstance(conversation, dict):
        raise ValueError("交换文件中没有该聊天")
    messages = conversation.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("聊天缺少原始发言")
    for message in messages:
        if (not isinstance(message, dict)
                or message.get("role") not in ("user", "assistant")
                or not isinstance(message.get("text"), str)
                or not isinstance(message.get("id"), str)):
            raise ValueError("发言角色或原文无效")
    fingerprint = hashlib.sha256(json.dumps(
        messages, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    if conversation.get("source_fingerprint") != fingerprint:
        raise ValueError("原始聊天指纹变化，请重新导出任务")
    return conversation


def request(document: dict, conversation_id: str) -> str:
    conversation = _conversation(document, conversation_id)
    prompt = Path(__file__).resolve().parents[1] / "web" / "conversation-prompt.txt"
    return prompt.read_text(encoding="utf-8") + "\nSource messages:\n" + json.dumps(
        conversation["messages"], ensure_ascii=False, indent=2
    )


def complete(document: dict, conversation_id: str, result: dict) -> dict:
    conversation = _conversation(document, conversation_id)
    dialogue, notes = result.get("dialogue"), result.get("notes")
    if not isinstance(dialogue, list) or not dialogue or not isinstance(notes, list):
        raise ValueError("结果缺少对话或学习笔记")
    for line in dialogue:
        if (not isinstance(line, dict) or line.get("speaker") not in ("A", "B")
                or not all(isinstance(line.get(k), str) and line[k].strip() for k in ("en", "zh"))
                or re.search(r"\[[^\]]*\]|[\u4e00-\u9fff]", line["en"])):
            raise ValueError("自然对话的说话人或中英文无效")
    users = {m["id"]: m["text"] for m in conversation["messages"] if m["role"] == "user"
             and not re.match(r"\s*(Role:|You are (a|an)\b|Act as\b)", m["text"], re.I)}
    kinds = {"explicit_gap", "text_supported_error", "expression_refinement",
             "learned_chunk", "recommendation"}
    for note in notes:
        if (not isinstance(note, dict) or note.get("kind") not in kinds
                or not all(isinstance(note.get(k), str) and note[k].strip() for k in
                           ("target", "prompt_zh", "reference_en", "explanation"))
                or not isinstance(note.get("sources"), list) or not note["sources"]):
            raise ValueError("学习笔记缺少练习或来源")
        for source in note["sources"]:
            quote = source.get("quote", "")
            if not quote or quote not in users.get(source.get("message_id"), ""):
                raise ValueError("学习点引用不在原始用户发言中")
        if note["kind"] == "text_supported_error":
            error = note.get("original_error") or {}
            if (not all(error.get(k) for k in ("quote", "issue", "correction"))
                    or not any(error["quote"] in s["quote"] for s in note["sources"])
                    or re.search(r"发音|评分|pronunciation|accent|score", error["issue"], re.I)):
                raise ValueError("个人错误缺少证据或包含不可验证的诊断")
    updated = copy.deepcopy(document)
    target = updated["conversations"][conversation_id]
    target.update(dialogue=copy.deepcopy(dialogue), notes=copy.deepcopy(notes), status="text_ready")
    return updated


def _ielts_item(document: dict, topic_id: str, item_id: str) -> dict:
    if document.get("version") != 1 or document.get("type") != "personal_learning_exchange":
        raise ValueError("个人交换文件版本不受支持")
    item = document.get("topics", {}).get(topic_id, {}).get("items", {}).get(item_id)
    if not isinstance(item, dict) or not item.get("texts", {}).get("original_answer"):
        raise ValueError("交换文件缺少该题的原始回答")
    return item


def request_ielts(document: dict, topic_id: str, item_id: str) -> str:
    item = _ielts_item(document, topic_id, item_id)
    prompt = Path(__file__).resolve().parents[1] / "web" / "ielts-prompt.txt"
    return prompt.read_text(encoding="utf-8") + "\nOriginal texts:\n" + json.dumps(
        item["texts"], ensure_ascii=False, indent=2
    )


def complete_ielts(document: dict, topic_id: str, item_id: str, result: dict) -> dict:
    from . import rewrite, study

    _ielts_item(document, topic_id, item_id)
    errors = rewrite.validate_texts(result)
    if errors:
        raise ValueError("；".join(errors))
    clean = re.sub(r"\[(curious|relaxed|uncertain|emphasis|break)\]", "",
                   result["podcast_script"])
    clean = re.sub(r"[ \t]+", " ", clean).strip()
    if clean != result["podcast_text"].strip():
        raise ValueError("播报稿与可见对话词序不同")
    dialogue = result.get("dialogue")
    if not isinstance(dialogue, list) or not dialogue:
        raise ValueError("手机任务结果需要逐句 A/B 对话与中文")
    for line in dialogue:
        if (line.get("speaker") not in ("A", "B") or not line.get("en") or not line.get("zh")):
            raise ValueError("逐句对话格式错误")
    if "\n".join(f"{line['speaker']}: {line['en']}" for line in dialogue) != result["podcast_text"]:
        raise ValueError("逐句台词与可读播报稿不同")
    output = copy.deepcopy(document)
    current = output["topics"][topic_id]["items"][item_id]
    for field in ("natural_english", "podcast_text", "podcast_script"):
        current["texts"][field] = result[field]
    current["dialogue"] = copy.deepcopy(dialogue)
    if result.get("study_material"):
        current["material"] = study.validate_material(result["study_material"], current["texts"])
    return output
