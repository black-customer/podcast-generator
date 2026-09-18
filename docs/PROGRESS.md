# PROGRESS — 工作会话账本（每次会话重写本文件）

更新：2026-09-18 会话 1（长程自治批次 1）

## 当前状态

- 已完成：M01(v0.1) M02*(m02) M03*(m03) M04(m04) M05(m05) M06(m06) M07(m07) —— 20 里的 7 个
- 门禁：check.sh 全绿；52 单元/API 测试 + 2 Playwright e2e 全过
- *网络尾项（api.fish.audio 本机不可达，恢复后依次执行）：
  1. `scripts/probe_fish_sse.py` → 校准 `alignment.parse_sse_events` → 接线单次合成轨逐词层
  2. `scripts/verify_alignment_ac.py 02-sleep-healthy-eating <item> podcast` 真实 AC
  3. 重生成含 [chuckle] 条目，验证 QA 门禁在真实音频上工作
- silero-vad pip 装了但 import 失败（装到了错误位置？）→ VAD 自动跳过中；M03 其余检查已覆盖

## 各里程碑落地内容

- M01：四治理文档 + check.sh + 占位符 key 修复 + ruff 治理 + git 策略（音频不入库）
- M02：alignment.py（实测段跨度/块内分配/线性重标定/指纹失效/SSE 解析器骨架）；
  tts 逐段 ffprobe；timeline 消费 alignment 优先；编辑失效缓存；AC 脚本
- M03：audioqa.py（时长比/静音孤岛/削波/VAD 可选）；隔离 .rejected.mp3 +
  剥全标签重试一次；qa_*.json + meta 结论；三 prompt 与标准文档标签政策统一
- M04：atomic_write_text 全落地；/api/settings 脱敏（key 永不回传 + 空值不覆盖）；
  SettingsIn 校验（segment_chars 100-5000 修无限循环 A33）；数字序排序修 A11
- M05：jobs 重写——持久化 + 启动恢复 interrupted；话题互斥 already_running；
  取消令牌贯穿 _post_tts 重试与逐段循环；assemble 异步任务 + 原子输出；GET /api/jobs
- M06：A-B 循环（含进度条金色标记）；句间导航 seekLine；键盘快捷键
  （空格/←→/A/B/L/R）；A24 程序性滚动判别；A32 跳转排队；A23 深链播放列表；
  对齐模式诚实 chip；A29 唱片状态修正
- M07：路由令牌 viewStale（修 A21 竞态；null=程序性重渲染语义）；轮询
  离开清理+连续失败熔断+interrupted 状态（修 A22）；audio onerror（A26）；
  去 Tom Holland/荷兰弟/硬编码语块高亮（A27/A28）；e2e 自清理+改用真实主语料条目

## 已验证（浏览器实测 + e2e）

- 点击句子跳转、A-B 循环回跳（采样确认环绕）、金色标记渲染、模式 chip
- 双 e2e：播放器全工作流 + 工作台管理流（含失败自清理）
- 修过的回归：e2e 遗留空话题污染首卡（已清 3 个 + 测试加 try/finally 清理）
- viewStale null 语义：程序性重渲染不受路由令牌约束（修 e2e 暴露的回退 bug）

## 下一步（按序）

1. M08 双语与多轨统一（chinese 层显示、轨道回退语义 A9/A19）
2. M09 UI 质感 2.0（设计令牌、空/错态、截图审查）；含 es modules 拆分（从 M07 顺延）
3. M10 整集体验（manifest 偏移、应用内整集播放、剧集过期检测 A18）
4. 网络恢复后清三个尾项（见上）
5. M11-M20 见 ROADMAP

## 给下一个会话的自己

- 先读 ROADMAP/PROGRESS/AGENTS；以磁盘为准
- `set -o pipefail; bash scripts/check.sh` 提交前必跑
- e2e 依赖真实主语料条目 02-sleep-healthy-eating/001（不要删它）
- MCP 浏览器 evaluate 只接受表达式（IIFE 可用）；含 "ArrowRight" 字样的 js 调用有工具层
  解析 bug，用 dispatchEvent + 字符串拼接绕过或直接用 Playwright 测试
- 网络恢复：三个尾项是 M02/M03 的收尾，先做再继续 M08+
