# 项目文档审计与冲突处理

本审计记录 L01 设计交接时的文档状态；L02/L03 已实现桌面逐句学习，当前能力以
根目录 README、ROADMAP 与 PROGRESS 为准。

审计日期：2026-09-29。范围：执行前受版本控制的 Markdown 文档，以及实际被设计工具读取的本地上下文。审计目的是区分现行产品要求、待开发设计和历史记录；没有把过去的交付重写成新版本。

| 文档 | 处理 | 原因 |
| --- | --- | --- |
| `.qoder/skills/ielts-audio/SKILL.md` | 更新 | 强调现行三英文文本接口，规划字段尚未实现 |
| `.qoder/skills/podcast-quality/SKILL.md` | 保持薄包装 | 指向仓库现行质量约定或 canonical Skill，不另造学习接口。 |
| `AGENTS.md` | 更新 | 增加当前功能与目标设计的清晰入口和质量要求 |
| `DESIGN.md` | 更新 | 旧蓝白／只收听定位与新方向冲突 |
| `PRODUCT.md` | 更新 | 旧蓝白／只收听定位与新方向冲突 |
| `README.md` | 更新 | 增加当前功能与目标设计的清晰入口和质量要求 |
| `bruce_kit/00_START_HERE_诊断与使用指南.md` | 保留历史 | 当时版本或私人材料的记录，不能事后改写为新功能 |
| `bruce_study_suite/STUDY_GUIDE.md` | 保留历史 | 先前个人学习套件的内容与说明，并非新主产品操作流程。 |
| `docs/AUDIO_ENGINEERING_STANDARDS.md` | 保留有效约束 | 音频工程、诊断或既有产品质量记录，对本轮概念图没有冲突。 |
| `docs/BASELINE.md` | 保留历史 | 当时版本或私人材料的记录，不能事后改写为新功能 |
| `docs/CONSTITUTION.md` | 更新 | Bruce 明确授权将主动学习纳入现行方向 |
| `docs/LEARNING_MODE_RESEARCH.md` | 更新 | 旧少量目标、局部练习需标为历史方案 |
| `docs/PROGRESS.md` | 追加本轮记录 | 保留旧会话的原样事实，追加新的设计交付结果 |
| `docs/QUALITY_PLAYBOOK.md` | 更新 | 增加当前功能与目标设计的清晰入口和质量要求 |
| `docs/RELEASE_NOTES.md` | 保留历史 | 当时版本或私人材料的记录，不能事后改写为新功能 |
| `docs/ROADMAP.md` | 更新 | 增加当前功能与目标设计的清晰入口和质量要求 |
| `docs/design/learning-mode-v1/PROMPTS.md` | 更新 | 旧少量目标、局部练习需标为历史方案 |
| `docs/design/learning-mode-v1/README.md` | 更新 | 旧少量目标、局部练习需标为历史方案 |
| `glm-workflow/README.md` | 独立工作流，保留 | 各自脚本与上限仍属独立实验或发布流程；不作为现行主产品学习规范 |
| `prompts/promptA_zh_to_natural_english.md` | 保留当前模板 | 部分模板被现有 API 读取；本轮不修改生成运行时行为。未来逐句接口另行开发。 |
| `prompts/promptB_voice_direct.md` | 保留当前模板 | 部分模板被现有 API 读取；本轮不修改生成运行时行为。未来逐句接口另行开发。 |
| `prompts/prompt_monologue_native.md` | 保留当前模板 | 部分模板被现有 API 读取；本轮不修改生成运行时行为。未来逐句接口另行开发。 |
| `prompts/prompt_podcast_bilingual.md` | 保留当前模板 | 部分模板被现有 API 读取；本轮不修改生成运行时行为。未来逐句接口另行开发。 |
| `prompts/prompt_podcast_immersion.md` | 保留当前模板 | 部分模板被现有 API 读取；本轮不修改生成运行时行为。未来逐句接口另行开发。 |
| `skills/ielts-audio/SKILL.md` | 更新 | 强调现行三英文文本接口，规划字段尚未实现 |
| `workflows/qoder-one-question/ACCEPTANCE.md` | 独立工作流，保留 | 各自脚本与上限仍属独立实验或发布流程；不作为现行主产品学习规范 |
| `workflows/qoder-one-question/README.md` | 独立工作流，保留 | 各自脚本与上限仍属独立实验或发布流程；不作为现行主产品学习规范 |
| `workflows/qoder-one-question/lessons/01-favourite-teacher/publish.md` | 独立工作流，保留 | 各自脚本与上限仍属独立实验或发布流程；不作为现行主产品学习规范 |
| `workflows/qoder-one-question/skills/one-question-creator/SKILL.md` | 独立工作流，保留 | 各自脚本与上限仍属独立实验或发布流程；不作为现行主产品学习规范 |
| `workflows/qoder-one-question/skills/one-question/SKILL.md` | 独立工作流，保留 | 各自脚本与上限仍属独立实验或发布流程；不作为现行主产品学习规范 |

## 额外上下文

- 本地 `.impeccable/surfaces/web-app-js.md` 是被工具读取的忽略文件，仍描述早期 Reading Notes 蓝色边线；不入库作为新交接依据。新设计以根 `DESIGN.md` 和本目录为准。
- 旧版 `docs/design/v1/` 与 `docs/design/learning-mode-v1/` 的图片保留，旧学习图的 README 和 PROMPTS 已标注历史。它们不指导新实现。
- 根 `README.md` 明确当前产品仍是音频生成链；新学习模式与暖纸界面属于待开发能力。
- `prompts/promptA_zh_to_natural_english.md` 和 `prompts/promptB_voice_direct.md` 在现有 API 路径有调用点。本轮不把学习讲解附加到这些文件，避免误改生产生成质量。
- `.qoder/skills/podcast-quality/SKILL.md` 保持对根质量文档的薄引用；canonical 的 `skills/ielts-audio/SKILL.md` 只说明未来接口尚未加入。

## 用于搜索的旧说法

完成后检查「无学习模式」「软件引导式学习功能」「只听音频」「可选局部填空」「只练两个重点」「蓝白／cobalt」等词。它们可以存在于标明历史的研究、进度、旧图或早期实验工作流中；现行产品、路线图和新版设计规范不得继续把它们写成下一版要求。
