# PROGRESS — 工作会话账本（每次会话重写本文件）

更新：2026-09-18 会话 1（长程自治批次 1，进行中）

## 当前状态

- 已完成：M01（v0.1）/ M02*（m02）/ M03*（m03）/ M04（m04）/ M05（m05）
- 门禁：`bash scripts/check.sh` 全绿（ruff + 52 测试 + 导入/启动冒烟）
- *号 = 待网络恢复的尾项（api.fish.audio 当前从本机不可达，PyPI 正常）：
  1. 跑 `scripts/probe_fish_sse.py` 实测 SSE 格式 → 校准 `alignment.parse_sse_events` →
     接线到单次合成轨（现在单次合成用 estimated 时间轴）
  2. `scripts/verify_alignment_ac.py <topic> <item> podcast` 跑真实音频 AC（<150ms）
  3. 重生成 02-sleep-healthy-eating 验证 [chuckle] 不再失控
- silero-vad 安装异常（exit 0 但 import 失败）→ VAD 检查自动跳过中，非阻塞

## 本会话做了什么（按序）

1. M01：git 治理、四份治理文档、check.sh 门禁、占位符 key 误判 live 修复
   （config.real_api_key + tts 6 调用点）、ruff 全量治理（45→0）、tmp 残骸清理、v0.1
2. M02：alignment.py（段级实测跨度/块内比例分配/线性重标定/指纹失效/SSE 容错解析器）；
   tts 逐段 ffprobe 实测；timeline 消费 alignment 优先；编辑文本双保险失效（修 A2）；
   AC 脚本 scripts/verify_alignment_ac.py（dry-run 条件下已 PASS）
3. M03：audioqa.py（时长比 0.45–2.3 / 静音孤岛 ≥2.5s / 削波 / VAD 可选）；
   隔离 .rejected.mp3 + 剥全部标签重试一次；qa_*.json 报告 + meta 结论；
   三 prompt 与标准文档标签政策统一（chuckle 高危，QA 兜底）；AC e2e 测试过
4. M04：atomic_write_text 全面落地（meta/settings/timeline/alignment/qa/manifest/topic.json）；
   GET /api/settings 脱敏（key 永不回传，fish_api_key_set 标志）；
   SettingsIn 校验（segment_chars 100–5000 等，修 A33 无限循环）；
   话题/条目按前导数字排序（修 A11 >100 断裂）；前端设置页适配脱敏
5. M05：jobs 重写——持久化 data/jobs.json + 启动恢复 interrupted；
   话题互斥（双击返回 already_running）；取消令牌 threading.Event 贯穿
   _post_tts 重试睡眠/逐段循环；assemble 异步任务 + 按钮禁用状态 + 原子输出；
   GET /api/jobs 历史；6 项新测试

## 发现与决策记录

- 管道退出码陷阱：`bash x | tail` 会吃掉非零退出 → 提交前用 `set -o pipefail`（已执行）
- dry-run 正弦音不是语音 → VAD 检查在 dry-run 跳过（skip_vad）
- 单次合成的对齐估算模式已在 alignment.json 标记 mode=estimated，前端可据此降级提示
- 旧 M 编号并入说明见 ROADMAP 头部

## 下一步（按优先级）

1. M06 播放器精准交互：消费 timeline 的 mode 标志；词级卡拉OK 骨架（数据就绪时）；
   A-B 循环、单句重播、键盘、修滚动跟读自禁用（A24：scrollIntoView 触发 onscroll
   → userIsScrolling 抑制下一帧，用 sentinel/超时判别程序性滚动）
2. M07 前端架构治理：路由令牌（每视图闭包携带 token，过期即弃写）；
   ManageState.pollTimer 路由离开清理；app.js 拆 ES modules；去 Tom Holland/魔法 id
3. M08-M20 见 ROADMAP

## 给下一个会话的自己

- 先读 ROADMAP/PROGRESS/AGENTS；以磁盘为准，别信记忆
- 提交前 `set -o pipefail; bash scripts/check.sh`
- 网络恢复后优先清三个尾项（见上）
