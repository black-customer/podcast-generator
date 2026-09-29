# IELTS Pod · 你的雅思口语练习室

> 当前可用：选题 → 用你最自然的方式作答 → 母语者版本的可反复收听音频 → 网页精听 / Android 离线听。
> 本地优先：所有数据只存在你自己的电脑上，不上传任何服务器。

仓库地址：**https://github.com/black-customer/podcast-generator**

## 一条主流程（产品只有这一条链）

```
安装配置 → 选题 → 输入回答 → Agent 或 API 改写 → StepFun 生成音频 → 网页下载/精听 → 安卓导入收听
```

1. **选题**：首页「开始练习」从内置雅思题库（Part 1/2/3，开箱即用）选一道题，或自建日常话题；
2. **作答**：用中文或英文自由写下你想表达的意思——不需要像范文；
3. **改写 + 生成**（两种模式结果完全一致）：
   - **Agent 模式（默认，零 API 文本成本）**：提交后点「一键复制给 Agent」，把指令粘给
     Codex / ZCode / WorkBuddy 等任意编码 Agent，它改写完成并合成音频后，网页自动跳到完成页；
   - **API 模式（一键）**：用已配置的 StepFun Key 一次完成改写→校验→音频合成，三阶段进度可见；
4. **听**：完成页直接播放/下载 MP3；精听播放器支持点句跳转、逐词点亮、单句重播、A-B 循环、倍速；
5. **带走**：导出语料包给 Android APP 离线收听，或导出 M4B/SRT。

## 下一版设计：逐句学习与暖纸自习室

Bruce 于 2026-09-29 确定新方向。完成音频后，用户可主动进入学习模式：
学习前录音 → 根据中文逐句默写完整英文并阅读讲解 → 看完整中文口答 →
只看原题脱稿口答 → 比较录音并复习困难句。

这组功能和暖纸色桌面界面目前是**设计方案，尚未作为产品功能上线**。
完整页面概念图、交互说明与开发交接见
[「暖纸自习室」设计入口](docs/design/study-room-v2/README.md)。
当前 `pipeline.py complete` 仍只接受三份英文文本；逐句中文和讲解是下一阶段要实现的数据能力。

## 快速开始

依赖：**Python 3.11+** 与 **ffmpeg**（`winget install Gyan.FFmpeg`）。

双击 `start.bat`：首次自动创建虚拟环境、安装依赖、启动服务并打开网页
（`http://127.0.0.1:8765`）。之后按网页「设置」向导三步配置（连接语音服务 → 选提问者 →
选回答者）。没有 Key 也能以 dry-run 模式体验全流程（生成占位音频）。

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
# 1) 创建虚拟环境并安装依赖：python -m venv .venv；.venv/Scripts/python -m pip install -r requirements.txt
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

## 语音引擎与 Key

- **StepFun（默认）**：[platform.stepfun.com](https://platform.stepfun.com/) 注册后创建 API Key，
  TTS 模型固定 `stepaudio-2.5-tts`；API 模式改写额外需要文本模型权限（默认 `step-3.7-flash`）；
- **fish.audio（备选）**：[fish.audio](https://fish.audio) 创建 Key（国内直连不稳定，可能需代理），
  免费档模型 `s2.1-pro-free`；音色 A/B Reference ID 在「音色展台」试听后一键设定；
- 提问者与回答者的性别、音色都由你配置（设置页「提问的人 / 回答的人」两张角色卡，先选性别再
  试听选音色）；未配置 Key = dry-run 模式。

## 手机 APP（Android，离线收听）

独立 APK（Capacitor 壳，与网页同一套代码），导入语料包后**无需网络**：
语料库、播放页（音字同步高亮/逐词点亮/点句跳转）全部可用。

1. **局域网导入**（推荐）：电脑端 `python run.py --host 0.0.0.0`，手机与电脑同 Wi-Fi，
   APP「导入」页输入电脑地址（如 `http://192.168.1.5:8765`）和终端显示的临时配对码
   → 拉取语料包；服务重启会更新配对码；
2. **文件导入**：电脑端导出语料包 zip → 任意方式传到手机 → APP「导入」页选择文件。

自己构建 APK（需 Node 18+、JDK 17、Android SDK）：

```bash
npm --registry=https://registry.npmmirror.com install --prefix mobile
.venv/Scripts/python scripts/sync_mobile.py        # 同步 web → www 并打 Java17 补丁
cd mobile && npx cap sync android                  # 同步 www → android 资源
.venv/Scripts/python ../scripts/sync_mobile.py     # cap sync 会重置 Java 版本，必须重打补丁
cd android && ./gradlew assembleDebug
# 产物：mobile/android/app/build/outputs/apk/debug/app-debug.apk
# 注意：覆盖安装前先卸载旧版（WebView 缓存会导致白屏）
```

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
| API 模式提示无文本模型权限 | 在 StepFun 平台开通文本模型，或改用 Agent 模式（不消耗文本 API） |
| 超长笑声/异常段落 | QA 门禁应已自动重试；仍存在则去掉表演稿中笑声标签后重新生成 |
| 点击句子跳不准 | 看播放器对齐标志：estimated=估算（重生成该条目升级为实测） |
| 手机 APP 拉包失败 | 电脑端须以 `--host 0.0.0.0` 启动、地址含 `http://`、填写当次启动显示的配对码、同 Wi-Fi、防火墙放行；模拟器用 `http://10.0.2.2:8765` |
| APP 更新后白屏 | 先卸载旧版再安装（WebView 缓存旧资源） |
| gradle 报"无效的源发行版：21" | 重跑 `python scripts/sync_mobile.py`（cap sync 会重置 Java 版本补丁） |

## FAQ

**要花钱吗？** 软件零成本本地运行；外部服务只有你自己的 StepFun / fish.audio 配额（真实生成时消耗）。
**数据隐私？** 全部数据在本地 `data/`；`settings.json`（含 key）永不入库、API 永不回传。
**旧语料会动吗？** 更新永不触碰 `data/`；旧条目不迁移，原始回答缺失时自动回退读取。
**iOS 支持？** 未做；手机浏览器访问电脑端网页可作过渡。

## 开发

```bash
bash scripts/check.sh              # 质量门禁（ruff + 测试 + 冒烟）
bash scripts/check.sh --with-e2e   # 额外跑 Playwright e2e（自起服务）
```

代码约定见 `AGENTS.md`；产品原则见 `docs/CONSTITUTION.md`；音频规范
`docs/AUDIO_ENGINEERING_STANDARDS.md`。API 文档：运行时 `/api/docs`。
