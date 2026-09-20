# AGENTS.md — 工程约定（ZCode / Qoder / Codex 会话必读）

本仓库是 Bruce 的个人英语学习播客生成器。先读 `docs/CONSTITUTION.md`、
`docs/ROADMAP.md`、`docs/PROGRESS.md`；冲突时宪法优先。音频、UI 或 data/ 改动再读
`docs/QUALITY_PLAYBOOK.md`。Qoder 可使用 `/podcast-quality` 自动加载这份质量约定。

## 常用命令

```bash
# 全量质量门禁（提交前必须绿）
bash scripts/check.sh

# 只跑测试
.venv/Scripts/python -m pytest tests/ -q --ignore=tests/e2e

# 启动/停止开发服务（127.0.0.1:8765）
.venv/Scripts/python run.py --no-open    # 前台
# e2e 需要先起服务：
.venv/Scripts/python -m pytest tests/e2e -q

# 音频探测
ffmpeg -i <file> -af volumedetect -f null -   # 响度
ffprobe -v error -show_entries format=duration -of csv=p=0 <file>
```

## 环境事实（不要重复踩坑）

- Windows + Git Bash；Python venv 在 `.venv/`（用 `.venv/Scripts/python`）
- ffmpeg 8.1 在 PATH；服务端口 8765
- `data/settings.json` 含真实 API key：**永不提交、永不打印完整值、API 永不回传**
  （`GET /api/settings` 必须脱敏——见 ROADMAP M04）
- Fish 免费档 `s2.1-pro-free`；真实 TTS 调用花钱（配额），测试默认 dry-run，
  真实生成只在明确需要验证听感时做
- ffmpeg concat 清单是 UTF-8 绝对路径：CJK 目录名是已知风险点（M04 验证）

## 代码风格

- 后端：Python 3.11，类型标注，模块级 docstring 中文；ruff line-length 100
- 前端：原生 ES modules，无构建、无 CDN、无框架；HTML 转义必须过 `esc()`
- 数据层改动必须先写回归测试（data/ 是产品本体，破坏 = 事故）
- 注释只写"代码本身说不出的约束"，不写"我改了什么"

## 完成定义

- 先调查现状，再给不超过 5 条的小计划；禁止顺手扩展任务范围或主动增加技术复杂度
- 缺陷修复和 data/ 改动必须先写能失败的回归测试，再实现修复
- “应该没问题”不是证据：代码任务交付时列出实际运行的命令与结果；UI/音频任务还要给截图或试听门结论
- `bash scripts/check.sh` 未绿，不得提交、标记里程碑 DONE 或打 tag
- 发现用户已有未提交改动时先识别归属，保留并绕开；禁止 reset、checkout 或覆盖

## 提交规范

- 一任务一提交：`feat|fix|refactor|test|docs|chore: <一句话>`
- 里程碑完成 → 更新 ROADMAP/PROGRESS → `git tag m<NN>`（如 m02）
- 禁止 `git push`（远端是 Bruce 的 GitHub，由他决定何时推送）
- 禁止 force push / history rewrite（main 有远端）

## 会话协议（长程自驱）

1. 读三份核心文档 → 选最高价值就绪里程碑 → 检查工作树
2. 探索现状（Read 优先）→ ≤5 条小计划 → TDD 实现 → 自查 diff
3. `bash scripts/check.sh` 绿 → 更新 PROGRESS/ROADMAP → 一任务一提交 → 里程碑 tag
4. 升级规则（只有这些情况找 Bruce）：宪法冲突、要花钱、破坏性操作、
   连续 3 次门禁红（停下写复盘到 PROGRESS）

## ielts-audio 任务路由（R03）

凡任务是「把用户的回答改写并生成播客音频」（或提到 natural_english /
podcast_text / podcast_script / pipeline.py complete），一律以
`skills/ielts-audio/SKILL.md` 为唯一规范：产出三份文本 JSON，执行
`pipeline.py complete --topic-id ... --item-id ... --result-json ...`。
禁止读取/打印任何 API Key；禁止绕过校验直改 data/。
