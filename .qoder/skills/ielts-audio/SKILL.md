---
name: ielts-audio
description: 完成用户的雅思回答改写并生成播客音频（canonical 规范在仓库根 skills/ielts-audio/SKILL.md）。用户要求"把我的回答改成英文并生成音频"或任务提到 pipeline.py complete / 三份文本时使用。
---

# ielts-audio（薄包装）

本 Skill 不含独立规范。执行时：

1. 读取仓库根目录 `skills/ielts-audio/SKILL.md`（canonical，唯一来源）。
2. 严格按其数据契约产出三份文本 JSON。
3. 执行 `pipeline.py complete --topic-id ... --item-id ... --result-json ...` 完成落盘与合成。
