# Bruce English Corpus · 播客生成器

> 把你脑中的想法，变成**高质量、可像日常播客一样消费的个性化英语输入材料**。
> 选题（内置雅思题库）→ 中文或英文自由作答 → Agent 会话改写成地道口语英文 → 批量 TTS →
> 双人对话/独白播客 → 网页播放（句级精准跳转 + 逐词跟读高亮）→
> **导出语料包到 Android APP 离线收听**，或导出 M4B/SRT 到任意播放器。

核心不变量：输入你的回答/意图，直接得到母语者拟真表达的音频——对话进对话出、
独白进独出发，自动生成、永远优先。回答使用男声（便于模仿），提问使用女声。

产品原则见 `docs/CONSTITUTION.md`；路线图 `docs/ROADMAP.md`；进度 `docs/PROGRESS.md`；
音频工程规范 `docs/AUDIO_ENGINEERING_STANDARDS.md`。

## 快速开始

双击 `start.bat`（首次自动建 venv 装依赖），浏览器打开 `http://127.0.0.1:8765`。
日常使用建议装桌面快捷方式：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/make_shortcut.ps1`
（桌面出现「IELTS Pod」图标，双击=服务没起就后台拉起、起了直接开浏览器）。

手动：`python -m venv .venv && .venv\Scripts\pip install -r requirements.txt && .venv\Scripts\python run.py`

依赖：Python 3.11+、ffmpeg（PATH 中）。

## fish.audio Key 申请（可能需要科学上网）

1. 打开 [fish.audio](https://fish.audio)（国内直连不稳定，建议自备代理）；
2. 注册/登录后进入 **API 页 → 创建 API Key**；
3. 免费档模型 `s2.1-pro-free` 即可用全部功能；工作台粘贴 key →「测试连接」；
4. 音色 Reference ID：在 fish.audio 挑选/克隆音色后，从音色页 URL 复制 ID，
   或直接用本工具「音色展台」试听后一键设为 A/B。

未填 key = dry-run 模式（占位音频，全流程照常可测）。

## 雅思题库（选题 → 作答 → 音频闭环）

1. 侧栏「雅思题库」：Part 1/2/3 标签 + 话题筛选 + 中英搜索 + 分页（URL 可收藏）；
2. 点任意题 → 写下你的回答（中文或英文不限）→ 提交；
3. 条目自动进入对应话题 → 按下方工作流改写并生成音频；
4. 已在库中的题显示「已作答」徽标（按题干匹配）；
5. 🎲「随机来一题」从当前筛选中随机抽题练口语。

题库数据来自本地 RoastDuck 题库快照：`python -m server.bank --sync`
（需 `D:\project\RoastDuck\data\app.db`；他人使用可跳过，题库页会显示引导卡）。

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
   或导出**手机语料包**给 Android APP 离线收听（见下节）。

## 手机 APP（Android，离线全功能）

独立 APK（Capacitor 壳，内核与网页完全一致），导入语料包后**无需网络**：
媒体库、播放页（音字同步高亮/逐词点亮/点句跳转）、雅思题库浏览全部可用。

**装包两条路：**

1. **局域网直传**（推荐）：电脑端 `python run.py --host 0.0.0.0`，手机与电脑同 Wi-Fi，
   APP「语料包管理」→ 输入电脑地址 → 拉取语料包；
2. **文件导入**：电脑端工作台「📱 导出手机语料包」→ 把 `data/exports/corpus.pack.zip`
   通过 QQ/微信/USB 传到手机 → APP「语料包管理」→ 选择文件导入。

**自己构建 APK**（需 Node 18+、JDK 17、Android SDK）：

```bash
npm --registry=https://registry.npmmirror.com install --prefix mobile
.venv/Scripts/python scripts/sync_mobile.py   # 同步 web → www 并打 Java17 补丁
cd mobile && npx cap sync android             # 同步 www → android 资源
.venv/Scripts/python ../scripts/sync_mobile.py  # cap sync 会重置 Java 版本，必须重打补丁
cd android && ./gradlew assembleDebug
# 产物：mobile/android/app/build/outputs/apk/debug/app-debug.apk
```

## 分享包（zip）

`.venv/Scripts/python scripts/package.py` → `dist/bruce-corpus-share.zip`
（不含密钥、个人语料与音频；接收方解压后按「快速开始」跑通）。

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
| APP 拉包失败 | 确认电脑端以 `--host 0.0.0.0` 启动、地址含 `http://`、同 Wi-Fi；模拟器里电脑地址是 `http://10.0.2.2:8765` |
| APP 导入后列表为空 | 语料包里的话题需要已生成音频才会进播放列表；先在电脑端生成 |
| gradle 报"无效的源发行版：21" | 重跑 `python scripts/sync_mobile.py`（cap sync 会重置 Java 版本补丁） |

## FAQ

**要花钱吗？** 软件零成本本地运行；唯一外部服务是 fish.audio 免费档 TTS（真实生成消耗其免费配额）。
**改写用什么 AI？** 不集成任何 LLM API——改写由你的 AI 编码会话（如 ZCode）经文件接口完成，见「Agent 接口」。
**数据隐私？** 全部数据在本地 `data/`；`settings.json`（含 key）永不入库不回传；题库快照不入 git。
**iOS 支持？** 未做；网页 PWA（手机浏览器访问电脑）可作过渡。

## 开发

```bash
bash scripts/check.sh              # 质量门禁（ruff + 53+ 测试 + 冒烟）
bash scripts/check.sh --with-e2e   # 额外跑 Playwright e2e（自起服务）
```

代码约定见 `AGENTS.md`。API 文档：运行时 `/api/docs`。
