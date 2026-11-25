# 英语说说说 · 多开口，说自己的英语

Windows 源码版提供语块微练、看剧素材联动、雅思口语训练和双人教学电台。
公开安装包的版本以 GitHub Releases 为准。

> 2026-10-06 确定新名称与定位：面向中国用户的英语口语学习工具，支持雅思口语与日常
> 表达、聊天复用。2026-10-15源码升级为雅思单题优先首页与完整训练闭环，原图标及双主题保留。
> 当前公开下载版本可能仍显示旧名称 IELTS Pod；源码更新与 GitHub 安装包发布分别进行。

> 当前可用：选题 → 用你最自然的方式作答 → 母语者版本的可反复收听音频 →
> 网页精听／逐句学习／Android 聊天整理、离线听与间隔口答。
> 本地优先：原文、材料和学习记录保存在你的电脑或手机；生成时仅将所需内容交给你配置的 API 服务。

仓库地址：**https://github.com/black-customer/podcast-generator**

## 直接下载最新版（免装 Python 仓库）

到 **[GitHub Releases](https://github.com/black-customer/podcast-generator/releases/latest)** 页面：

| 下载物 | 适合 | 用法 |
| --- | --- | --- |
| `ielts-pod-portable.zip` | Windows 电脑 | 解压 → 双击 `start.bat`（自动装依赖并启动） |
| `ielts-pod-*-debug.apk` | Android 手机 | 配置自己的 StepFun 服务后独立生成、学习；也可导入电脑语料包 |

更新：Windows 用户直接下载新 ZIP 解压覆盖（`data/` 个人数据在同目录时会被保留），
或继续用下方源码安装方式运行 `update_app.bat`。

## 桌面今日练习与素材收集

「今日练习」默认每局 8 张，可切换看剧表达、雅思口语、随手摘录或全部混练。
按 `Space` 揭晓并播放本机示范，`P` 切换发音标，`R` 录音，`O` 回到 B 站原片。
按 `1` 记为顺畅，`2` 把卡片放到本局末尾重考，`3` 拉长复习间隔，`X` 归档。
卡数和反应计时可在设置中调整。

- 在「素材收集 → 导入新素材」粘贴摘录、截图，或拖入 CaptionNoChinese 3.1.0 导出的 JSON。
- 若要从看剧脚本直推，在桌面「设置 → 看剧脚本配对」查看配对码，填入脚本设置并测试连接。
  记录库可手动发送当前范围，在脚本设置中也可主动开启记录后发送。
- 在收件箱选择视觉 API 或复制 Agent 批量制卡指令。视觉 API 只在主动确认后接收所选素材。
  提炼出的卡片可编辑。按 `Enter` 确认后才进入复习，按 `Backspace` 归档。
- 素材与截图保存在 `data/captures/`，便携包和公开语料包排除该目录。

## 雅思学习主流程

首页直接呈现到期或未练的闪卡。没有待练材料时，可按 Part、考季、话题和作答状态随机开题。
可以打字，也可以用 Faster-Whisper 在本机转写英文盲答并保留原声。可选的中文意图只保留
文字，用于补出想说却没说出来的表达。提交 API 生成前先检查文本服务配置。补好 Key 后可在
失败结果、题库已有回答或语料列表点击「重新用 AI 生成」。

1. 先看当场老师指导，查看有原话依据的纠错、中文意图和词汇缺口。示范音频在后台逐句合成。
   就绪后可直接听完整问答，也可开口重说并进入逐句练习。
2. 看中文逐句开口。`Space` 揭晓并播放本句，按住 `R` 录音、松手听示范和自己的声音。
   `1` 顺畅、`2` 卡壳，句子自动按 FSRS-4.5 安排复习。揭晓后可开「发音标」，也可切换母语示范与个人分身。
3. 只看原题脱稿录一遍，回听前后原声和示范。有录音可比时，查看英语语速、长停顿和语块命中，
   也可将三段导出成一条 MP3。

首页也可查看口语病历榜和复制今日 AI 陪练指令。原有训练可从
「历史训练与复验」进入。语料库提供独立播放器、语料包与 M4B/SRT 导出。

### 教学电台

从训练进入本题播客，从已入库的看剧语块进入剧集复盘，或从「今日练习」生成今日电台。
今日电台混合近期入库、到期或当天练过的看剧、摘录和雅思语块。配置的文本模型负责编排双人对话。中文由本地晓晓和云希朗读，英文使用 Bella 和 Puck，男搭档的英文可切到个人分身。
生成后可直接播放、调速或下载 MP3，成品保存在 `data/teaching_podcasts/`。

## 历史逐句学习与 Android

Bruce 于 2026-09-29 确定新方向。完成音频后，用户可主动进入学习模式：
学习前录音 → 根据中文逐句默写完整英文并阅读讲解 → 看完整中文口答 →
只看原题脱稿口答 → 比较录音并复习困难句。

桌面与 Android 共用学习规则和前端；桌面保留暖纸界面，手机支持清透白/午夜蓝一键切换。
手机练习首页直接显示中文，先口头尝试再查看或听答案；该轻练不推进正式学习和复习日程。
手机支持本地学习记录、录音与 API 生成。最终交接见 docs/design/mobile-implementation-u01/。
完整页面概念图、交互说明与开发交接见
[「暖纸自习室」设计入口](docs/design/study-room-v2/README.md)。
`pipeline.py complete` 同时接收三份英文文本和 `study_material`。用 `pipeline.py study` 可给
已有音频单独补齐材料。配置好的 API 可一次请求准备两者。

### 历史练习与跨天口答（L04）

从「历史训练与复验」可以进入旧版今日页，继续未完成的题、口答到期困难句或开始新题。
写错过、用过提示或收藏的句子在默写通过后进入日程；每轮最多 10 句，先看中文说英文，
再看示范并选择“独立说出／需要提示／暂时说不出”。自然的替代表达也可以独立说出。

口答默认可录音，也可注明“未录音／本人自评”。日期按实际练习结果安排，记录和录音都在
本机私有目录，默认不随公开语料包分享；手机记录保存在应用私有目录。交互和生产截图见
[L04 页面说明](docs/design/daily-practice-v1/README.md)。

## 快速开始

依赖：**Python 3.11+** 与 **ffmpeg**（`winget install Gyan.FFmpeg`）。

首次双击 `start.bat`：检查 Python、创建虚拟环境并安装依赖，等待服务就绪后打开网页
（`http://127.0.0.1:8765`）。日常打开可双击 `open_app.bat`，已有服务时直接进入网页。
在设置中配置 DeepSeek Key 并测试连接，或在高级设置中切换兼容接口。可用 Agent 模式
准备同一套材料。默认复用 `D:/project/ChineseAccent/.venv` 合成、对齐和分析录音，网页可选
Bella、Heart、Puck、Liam、Michael、Fenrir 或已录入的个人分身。声纹录制和微调在 ChineseAccent 管理。
默认 Bella 提问、Puck 回答。已经保存的本地音色选择会保留。找不到本地语音环境时，问答仅生成
试运行占位，设置页会提示检查 ChineseAccent 目录。旧桌面云语音配置自动忽略，历史成品可继续播放。

源码安装用户可运行 `update_app.bat` 更新；依赖安装失败时会停止更新，保留正在运行的
服务。ZIP 用户下载新版后覆盖代码文件，保留原目录的个人 `data/` 和录音。
启动失败时终端会保留错误与处理提示，请修复后重试，不需要删除个人数据。

环境有问题时跑诊断（只读、不输出密钥）：

```bash
.venv\Scripts\python scripts\doctor.py
```

## 让 AI Agent 帮你装 / 帮你更新（推荐）

你不需要懂技术。对任意 AI 编码助手（ZCode / Codex / WorkBuddy / Claude Code 等）说：

**首次安装**：

```text
帮我从 GitHub 克隆 https://github.com/black-customer/podcast-generator 到本机，
按它 README 的 "AI Agent 安装指令" 完成安装并启动，启动成功后打开 http://127.0.0.1:8765 告诉我。
```

**AI Agent 安装指令**（Agent 按此执行，全程无需人工介入）：

```bash
git clone https://github.com/black-customer/podcast-generator && cd podcastGenerate
# ffmpeg 缺失时：winget install Gyan.FFmpeg （装后重开终端）
# 1) 创建虚拟环境并装依赖：python -m venv .venv；.venv/Scripts/python -m pip install -r requirements-dev.txt
#    （requirements-dev 含运行依赖 + pytest/ruff/playwright；纯使用不开发装 requirements.txt 即可）
# 2) 环境诊断（可选，只读）：.venv/Scripts/python scripts/doctor.py
# 3) 后台启动服务（脚本会阻塞，务必后台运行）：start "IELTS Pod Server" /min start.bat
#    或 .venv/Scripts/python run.py --no-open &
# 4) 验证：GET http://127.0.0.1:8765/api/health 返回 200 即成功（version 字段为当前版本）
# 题库已内置（公开子集）；数据全部保存在 data/，更新永不动它
```

**以后更新**：

```text
帮我更新 IELTS Pod：在项目目录运行 update_app.bat，完成后告诉我新版本号。
```

## 桌面语音与文本服务

语音环境在「设置 → 本地语音与分身」检查。可直接为考官、回答者选音色并试听。
一键改写、老师讲评和电台编剧共用「文本改写引擎」，支持 DeepSeek 和自定义兼容接口。

## 手机 APP（Android，独立学习与聊天整理）

独立 APK（Capacitor 壳，与网页同一套代码）。首次在「我的」配置 StepFun Key、文本入口和
两个角色声音；标准入口按量计费，订阅入口需使用自己已获授权的地址，失败不会自动切换。
手机可独立完成题库作答生成、完整逐句学习、录音和今日口答，电脑无需开机。
四个入口为「今日／材料／题库／我的」。建议首次只生成一段短聊天或一道回答，确认声音
和材料符合预期后再导入长记录。提醒默认关闭，口答使用本人自评，不提供自动发音或雅思评分。

聊天结束后，通过系统分享交给 APP，或在「今日 → 整理一次英语聊天」粘贴 ChatGPT／豆包
分享链接、保留角色的文字，或选择 TXT／Markdown／JSON 文件。先核对原始记录，点击
「开始整理」才调用 API。链接读取依赖当前网络与分享页格式，失败时保留输入并提供文件兜底。
音频、自然对话、来源笔记和口答队列分别准备；后台处理有通知，可取消和手动恢复。
请求结果未知时暂停，页面会提示继续可能再次计费；已保存的有效阶段和音频片段会复用。

已保存材料**无需网络**即可收听、学习、录音和记录自评。播放器支持后台媒体控制；
逐词点亮仍只对有真实词表的语料启用。手机生成采用实测片段边界，句内估算会明确标注。
每日晚间提醒可选，默认关闭。旧电脑语料包也可继续导入：

1. **局域网导入**：电脑端 `python run.py --host 0.0.0.0`，手机与电脑同 Wi-Fi，
   APP「导入」页输入电脑地址（如 `http://192.168.1.5:8765`）和终端显示的临时配对码
   → 拉取语料包；服务重启会更新配对码；
2. **文件导入**：电脑端导出语料包 zip → 任意方式传到手机 → APP「导入」页选择文件。

自己构建 APK（需 Node 20+、JDK 17、Android SDK）：

```bash
npm --registry=https://registry.npmmirror.com install --prefix mobile
.venv/Scripts/python scripts/sync_mobile.py        # 同步 web → www 并打 Java17 补丁
cd mobile && npx cap sync android                  # 同步 www → android 资源
.venv/Scripts/python ../scripts/sync_mobile.py     # cap sync 会重置 Java 版本，必须重打补丁
cd android && ./gradlew assembleDebug
# 产物：mobile/android/app/build/outputs/apk/debug/app-debug.apk
# 更新须使用相同签名覆盖安装；不要为更新卸载 APP，卸载会清除手机私有学习记录。
# 旧 IndexedDB 包会校验后迁移；未成功前保留旧副本。
```

### 手机任务交给电脑 Agent

在「我的」导出个人任务交换 JSON，只交给自己的 Agent。此文件包含私人原文，不包含
密钥、练习历史或录音；这是手动交接。Agent 根据文件中的聊天 ID 或话题／条目 ID
读取指令、产出 JSON，再通过以下校验入口写出另一份交换文件：

```bash
# 聊天：结果格式由 conversation-request 输出的指令确定
.venv/Scripts/python pipeline.py conversation-request --exchange-json <手机导出.json> --conversation-id <id>
.venv/Scripts/python pipeline.py conversation-complete --exchange-json <手机导出.json> --conversation-id <id> --result-json <结果.json> --output-json <手机导回.json>
# 雅思：沿用三份英文文本，另需逐句 A/B 台词及中文，格式由 mobile-request 确定
.venv/Scripts/python pipeline.py mobile-request --exchange-json <手机导出.json> --topic-id <tid> --item-id <iid>
.venv/Scripts/python pipeline.py mobile-complete --exchange-json <手机导出.json> --topic-id <tid> --item-id <iid> --result-json <结果.json> --output-json <手机导回.json>
```

手机「我的 → 导入处理结果」读取校验后的文件，按 ID 与原文指纹更新，保留手机学习历史。
这些电脑命令只整理文本，不触发收费请求；导回后点击生成，手机继续制作音频和缺少的学习材料。

开发验收需 Node（共享领域规则测试）、Android SDK 和可运行的模拟器：
`bash scripts/check.sh --release`、`gradlew :app:testDebugUnitTest :app:connectedDebugAndroidTest`。
真实分享页验收通过仪器参数提供 URL，不把真实记录写进测试或 APK；实机锁屏／录音和
真实语音听感须另行抽查，模拟器通过不代替这两项。

## 给 Agent 的执行接口（ielts-audio）

Agent 模式的规范入口：`skills/ielts-audio/SKILL.md`（canonical，Qoder 有薄包装）。
Agent 产出三份文本 JSON（natural_english / podcast_text / podcast_script）后执行：

```bash
.venv/Scripts/python pipeline.py complete --topic-id <tid> --item-id <iid> --result-json <json路径>
```

命令先校验后原子写入，再按当前引擎合成，成功输出播放页 URL 与 MP3 路径。
禁止读取/打印任何 API Key；禁止绕过校验直改 data/。

## 分享包（zip）

`.venv/Scripts/python scripts/package.py` → `dist/ielts-pod-portable.zip`
（自动审计：不含密钥、个人语料、试听缓存、临时文件与任何音频；接收方解压后双击 `start.bat`）。

## 排错（TROUBLESHOOTING）

先跑 `.venv\Scripts\python scripts\doctor.py`，大部分安装问题会直接给出下一步提示。

| 症状 | 处理 |
|---|---|
| 启动报"端口 8765 已被占用" | 服务可能已在运行，直接开网页；或 `python run.py --port 8766` 换端口 |
| 音频生成失败 | 看任务错误详情；确认 Key/网络；失败条目可单独重试；`scripts/doctor.py` 查 ffmpeg |
| API 模式提示无文本模型权限 | 检查所配置的文本服务 Key 和模型权限，或使用 Agent 模式 |
| 超长笑声/异常段落 | QA 门禁应已自动重试；仍存在则去掉表演稿中笑声标签后重新生成 |
| 点击句子跳不准 | 看播放器对齐标志：estimated=估算（重生成该条目升级为实测） |
| 手机 APP 拉包失败 | 电脑端须以 `--host 0.0.0.0` 启动、地址含 `http://`、填写当次启动显示的配对码、同 Wi-Fi、防火墙放行；模拟器用 `http://10.0.2.2:8765` |
| APP 更新后白屏 | 保留应用数据，先关闭再打开；确认安装包签名、版本与资源。不要直接卸载 |
| gradle 报"无效的源发行版：21" | 重跑 `python scripts/sync_mobile.py`（cap sync 会重置 Java 版本补丁） |

## FAQ

**要花钱吗？** 桌面语音在本机运行。使用文本 API 时消耗你配置的服务额度。
**数据隐私？** 电脑数据在本地 `data/`，手机数据在应用私有目录；手机 Key 使用 Keystore
加密保存，不随交换文件或语料包导出。用户点击 API 处理后，所需文本会发给其配置的服务。
**旧语料会动吗？** 更新永不触碰 `data/`；旧条目不迁移，原始回答缺失时自动回退读取。
**iOS 支持？** 未做；手机浏览器访问电脑端网页可作过渡。

## 开发

```bash
bash scripts/check.sh              # 质量门禁（ruff + 测试 + 冒烟）
bash scripts/check.sh --with-e2e   # 额外跑 Playwright e2e（自起服务）
```

代码约定见 `AGENTS.md`；产品原则见 `docs/CONSTITUTION.md`；音频规范
`docs/AUDIO_ENGINEERING_STANDARDS.md`。API 文档：运行时 `/api/docs`。
