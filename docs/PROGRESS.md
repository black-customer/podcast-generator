# PROGRESS — 工作会话账本（每次会话重写本文件）

更新：2026-09-18 会话 1（自治基座启动）

## 当前状态

- 里程碑：M01 ACTIVE（其余 PENDING，见 ROADMAP）
- 门禁基线：pytest 14 passed / 1 skipped（修复占位符 key 误判 live 后全绿）
- 服务：停摆中（M01 内恢复）

## 本会话做了什么

1. 三路调研：全库审计（40 项确认缺陷）、长程工作流最佳实践（Anthropic/SpecKit/Ralph/Manus/METR）、
   技术选型（Fish 时间戳端点/Silero VAD/FSRS→已按新愿景裁剪/导出方案）
2. 与 Bruce 对齐愿景并定稿宪法（砍掉学习模式/复习/shadowing，专注输入材料+自媒体）
3. M01 进行中：修复 `settings.example.json` 占位符 key 被当真 key 的 bug
   （config.real_api_key() + tts.py 6 处调用点统一）；.gitignore 音频策略；
   建立 CONSTITUTION/AGENTS/ROADMAP/PROGRESS

## 发现的新事实

- git 仓库已存在（main + origin=black-customer/podcast-generator，已推送过 1 提交）；
  settings.json 未入库，无泄密；example 只含占位符
- 代码库比预期进化：已有 timeline.py/mastering.py/pipeline.py/tests/docs，
  双轨（podcast/monologue）数据模型已存在；旧任务账本 data/task_ledger.json 已并入 ROADMAP
- 审计确认根因：时间轴=字符估算（A1）；QA 缺失（A4）；学习模式已在改版中移除（符合新宪法，无需恢复）

## 下一步（按序）

1. 完成 M01：scripts/check.sh（装 ruff）；恢复服务；清 .tmp 残骸；commit + tag v0.1
2. M02：先写 Fish SSE 时间戳端点的真实响应探针（一次真实调用），再动 tts.py
3. M03/M04 并行推进

## 给下一个会话的自己

- 先读 ROADMAP/PROGRESS/AGENTS，别信记忆里的旧代码结构——以磁盘为准
- M02 是最高价值：所有"跳不准"问题的根因都在估算时间轴
- 真实 Fish 调用要节制（免费配额）；dry-run 覆盖流程，真实调用只验听感与对齐
