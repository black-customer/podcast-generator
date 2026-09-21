---
name: ielts-audio
description: Canonical workflow for completing an IELTS answer → native-English audio task in PodcastGenerate. Use when a user asks an agent (Codex / ZCode / WorkBuddy 等) to rewrite their answer and generate the podcast audio, or whenever a task mentions natural_english / podcast_text / podcast_script or pipeline.py complete.
---

# ielts-audio：回答改写 + 音频生成（canonical 规范）

本文件是 Agent 模式的唯一规范来源（R03）。Qoder 侧只是薄包装，不要另立标准。

## 数据契约（三份文本 + 一份原始回答）

| 文件 | 用途 | 硬性要求 |
|------|------|----------|
| `original_answer.txt` | 用户原始回答（中/英/混合） | 永远保留，改写失败也不得清除或覆盖 |
| `natural_english.txt` | 干净、可背诵的地道英文回答 | 第一人称口语；**不允许任何 `[tag]`** |
| `podcast_text.txt` | 用户可见的完整问答 | `A:` 提问行 + `B:` 回答行；**不允许任何 `[tag]`** |
| `podcast_script.txt` | TTS 表演稿（对普通用户隐藏） | 与 podcast_text 同一句子；A 可在开头使用一次 `[curious]`，B 可在开头使用一次 `[relaxed]`，B 全文最多再用两个 `[uncertain]`、`[emphasis]` 或 `[break]` |

- 三份英文文本的词句必须与用户原始回答语义一致：保留用户的真实经历、观点和细节，**不得虚构**。
- 对话进对话出：题目是问答，就输出 A/B 对话；B 行内容 = 用户回答的地道改写。
- 禁止笑声、呼吸、叹气和戏剧化标签；表演标签稀疏使用，主要依靠自然标点和分句。

## 完成命令（唯一入口）

1. 把三份文本写成 JSON（UTF-8，无注释）：

```json
{
  "natural_english": "…",
  "podcast_text": "A: …\nB: …",
  "podcast_script": "A: …\nB: …"
}
```

2. 在仓库根目录执行：

```bash
.venv/Scripts/python pipeline.py complete --topic-id <topic_id> --item-id <item_id> --result-json <json路径>
```

- 命令先校验后原子写入，最后按当前 TTS provider（默认 StepFun）合成 `audio_podcast.mp3`。
- 成功输出 `play_url`（网页完成页）与 `mp3_path`；**校验失败时按错误清单修正 JSON 重试**，
  不得手改 data/ 目录绕过校验。
- 目标条目的 `topic_id` / `item_id` 以任务指令（agent-task）给出的为准。

## 禁止事项

- 不读取、不打印、不传输任何 API Key（`data/settings.json` 与 agent 无关）。
- 不直接调用 StepFun/Fish API；文本改写由完成命令之外的环节不负责——Agent 只产出三份文本。
- 不修改 data/ 下其他用户的既有语料。
