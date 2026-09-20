# Release Notes

## v0.5.0 (beta) — 可分享版重构 R01–R05（2026-09-21）

面向公开分享的第一版：一条主链（选题 → 作答 → Agent/API → StepFun 音频 → 精听 → 安卓离线）。

### 新引擎
- StepFun StepAudio 2.5 TTS 成为默认语音引擎（模型固定 `stepaudio-2.5-tts`），fish.audio 降为备选；
  旧安装已配 Fish Key 的保持不变，不自动迁移密钥。
- 逐行对话合成（提问者/回答者独立音色，默认 280ms 间隔），24kHz 输出统一重编码 44.1kHz 后拼接；
  429 遵循 Retry-After 有限退避；复用既有 QA 门禁与 -16 LUFS 母带链。
- 真实验收：5 条代表语料 QA 全 pass、时长比 1.02–1.19（无变速/截断/异常停顿）。

### Agent/API 双模式
- 提交回答时可选：Agent 模式（默认）一键复制指令给任意编码 Agent，完成后网页自动跳转；
  API 模式用同一 StepFun Key 一次完成改写→校验→合成（step-3.7-flash JSON Mode，
  结构失败自动修复重试一次；无文本权限时明确提示改用 Agent 模式，不静默降级）。
- `original_answer.txt` 永远保存原始回答；改写失败不覆盖、不产生音频。
- Agent 执行入口：`skills/ielts-audio/SKILL.md` + `pipeline.py complete`（先校验后原子写入）。

### 已批准 UI（docs/design/v1）
- 品牌 IELTS Pod；导航收敛为 开始练习 / 我的语料 / 正在播放 / 设置；默认入口「开始练习」。
- 我的语料只有 雅思口语 / 日常表达 两个分类；普通界面移除独白/整集/多轨术语。
- 设置页 = 双引擎卡 + 提问的人/回答的人角色卡（性别→音色联动→试听）；首配向导三步完成。
- Android：ZIP 文件 + 手动局域网两种导入；模拟器实测导入与逐词点亮播放通过。

### 分享与运维
- `scripts/doctor.py`：只读环境诊断（Python/ffmpeg/依赖/配置/题库/端口），绝不输出密钥。
- `run.py` 启动前置检查：端口占用显式报错（不静默连旧服务）、ffmpeg 缺失给安装提示。
- `scripts/package.py` → `dist/ielts-pod-portable.zip`（内置审计：零密钥/零个人语料/零音频）。
- README 重写：真实仓库地址、一条主流程、可直接发给 Agent 的安装指令。

### 已知边界
- R02 的「5 条中至少 4 条更愿意反复听 StepFun」听感门待 Bruce 确认（A/B 清单在
  `data/.tmp/r02_acceptance/MANIFEST.md`）。
- Android APK 为 beta；更新安装前建议先卸载旧版（WebView 缓存）。
