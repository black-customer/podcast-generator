# Bruce English Corpus · 播客生成器

> 把你脑中的想法，变成**高质量、可像日常播客一样消费的个性化英语输入材料**。
> 中文自由回答 → Agent 会话改写成地道口语英文 → 本工具批量 TTS → 双人对话/独白播客 →
> 网页播放（句级精准跳转 + 跟读高亮）或导出 M4B/SRT 到任意播放器。

产品原则见 `docs/CONSTITUTION.md`；路线图 `docs/ROADMAP.md`；进度 `docs/PROGRESS.md`；
音频工程规范 `docs/AUDIO_ENGINEERING_STANDARDS.md`。

## 快速开始

双击 `start.bat`（首次自动建 venv 装依赖），浏览器打开 `http://127.0.0.1:8765`。

手动：`python -m venv .venv && .venv\Scripts\pip install -r requirements.txt && .venv\Scripts\python run.py`

依赖：Python 3.11+、ffmpeg（PATH 中）。

## 配置（工作台 → 设置）

1. [fish.audio](https://fish.audio) API Key；
2. 音色 A（独白）与音色 B（对话第二人，可选）的 Reference ID——
   在音色展台可**试听**后一键设为 A/B；
3. 模型默认 `s2.1-pro-free`；点「测试连接」验证。
   未填 key = dry-run（生成占位音频，全流程照常可测）。

## 工作流（你 ↔ Agent ↔ 工具）

1. **建题**：工作台「批量粘贴题目」或 `POST /api/import-batch`（Markdown 任务包）；
2. **录中文**：每条目粘入你的中文自由回答（像跟朋友聊天一样说透）；
3. **改写**：点「复制改写请求」→ 粘给 AI 会话（ZCode 等）→ 得到 Natural English 粘回；
   （可选）「复制配音请求」得到 Fish Script 表演层；留空则直接合成 Natural English；
4. **生成**：条目级或话题级批量 TTS（双人对话自动用双音色单次生成，模型看完整上下文，
   接话节奏由模型演绎）；生成后自动过音频 QA 门禁（时长比/静音孤岛/削波/VAD），
   异常自动隔离并去标签重试一次，QA 结论写入条目 meta；
5. **合成整集**：按章节连成一个 MP3；条目重生成后剧集标记过期，支持一键重建；
6. **听**：播放器句级跳转 + A-B 循环 + 句间导航 + 键盘快捷键（空格/←→/R/A/B/L）+
   跟读高亮（实测/SSE 数据时含词级点亮）+ 中文参考面板 + 对齐模式诚实标志；
7. **带走**：导出 M4B（含章节，ffprobe 可验证）/ SRT / VTT / LRC；
   手机同局域网访问 `http://<电脑IP>:8765` 可安装 PWA 到主屏（锁屏可控播放）。

## Agent 接口（零 API 成本的关键设计）

改写环节由 AI 会话完成，工具与 Agent 之间是**纯文件接口**——
Agent 可直接读写 `data/topics/**`（纯文本），或用批量导入：

```bash
.venv/Scripts/python pipeline.py --topic "My studies" --question "Q..." \
  --chinese-file zh.txt --podcast-file en.txt --track all
```

提示词模板：`prompts/`（改写 Prompt A、配音 Prompt B、独白/双语脚本规范）。
生成类提示词禁止笑声标签（`[chuckle]` 等）——QA 门禁会拦截，表演层脚本可用但需谨慎。

## 数据结构

```
data/
  settings.json                 # API key（永不入库/回传）
  voices.json                   # 音色预设（唯一真源，含 speed/temperature）
  topics/01-xxx/
    topic.json
    items/001-题目slug/
      question.txt chinese.txt natural_english.txt fish_script.txt
      monologue_text.txt monologue_script.txt podcast_text.txt podcast_script.txt
      meta.json                 # 状态/时长/QA结论/tts_mode
      alignment_podcast.json    # 句级+词级对齐（mode: sse/measured/estimated）
      timeline_podcast.json     # 前端兼容时间轴
      qa_podcast.json           # 音频质检报告
      audio.mp3 / audio_podcast.mp3 / audio_monologue.mp3
  episodes/                     # 合成的整集（mp3 + manifest json）
  exports/                      # M4B / SRT / VTT / LRC 导出
```

## 排错（TROUBLESHOOTING）

| 症状 | 处理 |
|---|---|
| 音频生成失败 | 工作台看任务错误详情；确认 key/网络；失败条目可单独重试 |
| 超长笑声/异常段落 | QA 门禁应已自动重试；若仍存在，删掉脚本中笑声标签后重新生成 |
| 点击句子跳不准 | 看播放器对齐标志：estimated=估算（重生成该条目升级为实测/sse） |
| 声音小 | 已内置 -16 LUFS 归一；仍小则检查系统音量混合器中浏览器的音量 |
| 手机打不开 | 手机与电脑同 Wi-Fi、防火墙放行 8765、用 `--host 0.0.0.0` 启动 |
| 服务重启后任务消失 | 任务标记 interrupted（设计如此），重新点击生成 |

## 开发

```bash
bash scripts/check.sh              # 质量门禁（ruff + 53+ 测试 + 冒烟）
bash scripts/check.sh --with-e2e   # 额外跑 Playwright e2e（自起服务）
```

代码约定见 `AGENTS.md`。API 文档：运行时 `/api/docs`。
