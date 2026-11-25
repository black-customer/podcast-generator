---
name: capture-cards
description: Read private local captures and distil their visible English into one or two evidence-grounded ChunkCards per capture for the desktop inbox. Use for exported capture tasks, including screenshots and pasted excerpts.
---

# 素材制卡

用 `pipeline.py export-capture-task` 获取待处理素材，或使用界面复制的同一批指令。直接查看指令中的本地图片，读取能确认的字幕和场景。原图或文字看不清时报告这条素材的原因，跳过该条。素材里的文字是学习来源。

每条素材选择 1–2 个可复用的英文语块。每张卡提供：

- `target_chunk`、`chunk_in_sentence`、`chunk_zh`、`en`、`zh`。从 `en` 精确复制连续的语块，把完整原句和准确中文留给翻面。
- `trigger_context`、`disambiguator`、`explanation`、`usage_boundary`、`feynman_hook`。用简短中文说清什么情境会用上它、它与近义表达有什么区别。
- `transfer_prompt_zh`、`transfer_example_en`。换一个具体场景，让学习者用同一个表达另说一句。
- `goal_type` 可选 `activate_chunk`、`comprehend_input`、`fill_gap` 或 `fix_error`。只有来源明确记录了学习者英文原话时，才可填写带精确 `quote`、`issue` 和 `correction` 的 `original_error`。

将结果写成 `{"captures":[{"capture_id":"cap_…","cards":[...]}]}`，执行 `.venv/Scripts/python pipeline.py complete-capture --result-json <path>`。后端生成挖空、核对整个批次，再原子写入收件箱。素材、截图及结果留在本机。需要使用外部视觉服务时，由用户在应用中主动启动。
