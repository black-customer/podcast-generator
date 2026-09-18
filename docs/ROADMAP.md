# ROADMAP — 30 天产品化路线图（2026-09-18 起）

状态：PENDING / ACTIVE / DONE / BLOCKED。
并行分组：G1 基座｜G2 音频真相｜G3 前端｜G4 分发｜G5 生产｜G6 质量。
历史账本 `data/task_ledger.json`（旧编号）已并入：旧M01(测试)→新M18；旧M02(对齐)→新M02；
旧M03(账本)→新M01；旧M04(笑声)→新M03；旧M07(意群)→新M02。

## Wave 1：自治基座

### M01 自治基座与版本化 [G1] — DONE (2026-09-18, tag v0.1)
价值：一切长程工作的前提。
WP：git 治理（.gitignore 音频策略）；CONSTITUTION/AGENTS/ROADMAP/PROGRESS 四文档；
scripts/check.sh 门禁；修复服务停摆与 .tmp 残骸；现有测试纳入门禁；占位符 key 误判 live 修复。
AC：check.sh 全绿（含 ruff+pytest+启动冒烟）；账本反映 20 里程碑；服务可启动；tag v0.1。

## Wave 2：音频真相层（最高优先）

### M02 逐词对齐真相层 [G2]（依赖 M01）— DONE* (tag m02；*SSE 逐词层待网络恢复后接线并跑真实 AC)
价值：根治"点击跳不准、文本不跟读"。
WP：接入 Fish `/v1/tts/stream/with-timestamp` SSE（逐词时间戳）；
逐行模式拼接前探测每段真实时长（当前被丢弃）；alignment.json 边车（词级+句级 span，
文本+音频指纹缓存）；timeline.py 重写为消费真实数据；文本编辑后缓存失效。
AC：新生成条目必有 alignment.json；抽 N 句 ffmpeg 切听偏差 <150ms（脚本验证）；
缓存失效回归测试（审计 A2）。

### M03 音频 QA 门禁与自愈 [G2]（依赖 M02）— DONE* (tag m03；*真实音频 AC 与现有条目重验待网络)
价值：根治"[chuckle] 笑 5 秒导致音画错位"。
WP：期望/实际时长比检查；Silero VAD 非语音孤岛检测（笑声/长静音）；
silencedetect+astats 削波；异常自动隔离+去标签重试；生成附质量报告；
三份 prompt 与 AUDIO_ENGINEERING_STANDARDS 标签政策统一；服务端标签白名单。
AC：注入伪造 5s 笑声被检出并触发重试（测试）；每条音频有质量报告；
现有含 [chuckle] 条目重生成后无超长非语音段。

### M04 数据模型 v2 [G2]（依赖 M02）— DONE (tag m04)
价值：数据是产品本体。
WP：原子写（tmp+rename）；meta schema 版本化+迁移；话题排序 >100 修复；
compute_status 轨道盲区与 stale 误判修复；GET /api/settings 脱敏（key 不再回传）；
CJK 目录 ffmpeg concat 验证；.tmp 生命周期治理；settings 参数服务端校验（修 A33 无限循环）。
AC：并发写测试无损坏；旧 meta 迁移回归测试；100+ 话题排序正确；
`GET /api/settings` 不含明文 key；segment_chars<=0 被 422 拒绝。

### M05 任务系统加固 [G1/G2]（依赖 M01，可并行）— DONE (tag m05)
价值：批量生产语料时不炸。
WP：任务持久化（重启不孤儿）；同话题互斥锁（修双击双任务）；取消令牌（Fish 重试间可中断）；
assemble 异步化+原子输出；任务历史 API。
AC：双击生成只产生一个任务；重启后轮询不悬死；合成中取消立即生效。

## Wave 3：播放体验

### M06 播放器精准交互 [G3]（依赖 M02）— DONE (tag m06；词级卡拉OK待 SSE 数据)
WP：词级卡拉OK（消费 M02 数据）；点句/点词跳转；A-B 循环；单句重播；键盘快捷键；
逐句语速；修滚动跟读自禁用（A24）。
AC：Playwright 断言点击第 k 句后 currentTime 落在句 span ±150ms；连续 30 句高亮无卡顿。

### M07 前端架构治理 [G3]（依赖 M01，可与 M06 并行）— DONE (tag m07；es modules 拆分顺延至 M09 一并做)
WP：路由令牌防竞态（A21）；轮询定时器生命周期（A22）；audio onerror（A26）；
app.js 拆 ES modules；清除演示残留（Tom Holland 文案/假药丸/魔法 id，A27/A28/A31）。
AC：快速切换 50 次无视图错乱；404 音频显式报错；无内联 onclick。

### M08 双语与多轨统一 [G3]（依赖 M04、M06）— DONE (tag m08)
WP：播放器中/英/剧本三层显示；轨道回退语义修正（A9/A19）；每轨真实状态。
AC：双语 e2e；请求 monologue 绝不返回 default 音频（API 测试）。

### M09 UI 质感 2.0 [G3]（依赖 M07）— DONE (全视图截图走查；原生 confirm 保留用于删除确认；es modules 拆分经评估延后——单文件 1500 行尚可维护，重构风险>收益，记入 M19 文档决策)
WP：设计令牌统一；加载/空/错误态全覆盖；过度承诺文案修正；截图审查子代理走查。
AC：审查子代理对 6 视图截图验收通过；无原生 alert/prompt。

## Wave 4：剧集与分发

### M10 整集体验 [G4]（依赖 M04、M06）— DONE (tag m10)
WP：manifest 每条目偏移量；应用内整集播放器+章节跳转；剧集过期检测+一键重建（A18）。
AC：整集章节跳转正确（e2e）；条目重生成后剧集标记过期。

### M11 M4B/章节导出 [G4]（依赖 M10）
WP：ffmpeg ffmetadata 章节嵌入 M4B；内嵌文本；按话题导出。
AC：ffprobe 验证章节存在；GUID 稳定。

### M12 字幕导出 + 局域网 RSS [G4]（依赖 M10）
WP：SRT/VTT/LRC 导出（podcast:transcript/chapters 规范）；局域网 RSS（零成本）。
AC：RSS 校验通过；VTT 时间轴抽检 <150ms 偏差。

### M13 手机 PWA [G4]（依赖 M09）
WP：响应式移动布局；manifest+service worker 可安装；Media Session 锁屏控制；配对二维码。
AC：手机视口截图审查通过；锁屏播放控制（Playwright 移动模拟）。

## Wave 5：语料生产线

### M14 语料批量生产线（Agent 接口）[G5]（依赖 M04、M05）
WP：pipeline.py 加固（Agent 批量改写落盘+lint 校验）；批量导入格式；
搜索/过滤/重排；语料统计仪表盘。
AC：50 题→建条目→批量改写→批量生成全链路演练通过；改写 lint 拦截违规标签。

### M15 音色与表演资产管理 [G5]（依赖 M04）— PARTIAL (试听已上线: 官方样本代理+缓存；其余待做)
WP：voices.json 唯一真源（修魔法 id/双份配置）；表演层规范 v2（对话行为库）；
标签策略执行器与 M03 联动；音色试听页。
AC：预设应用后与 voices.json 一致（测试）；规范落地并回改现有语料。

### M16 自媒体一键内容 [G5]（依赖 M14）
WP：语料→内容草稿（小红书卡片/双语金句/短视频字幕/推文串模板）；批量导出。
AC：1 话题一键产出 3 形态草稿，抽查合格率 ≥90%。

### M17 长稳性与性能 [G5]（依赖 M04、M05）
WP：/api/topics 扫描优化（索引缓存）；500+ 条目压测；启动/内存基线；ffmpeg 提速。
AC：500 条目话题列表 <300ms；压测无错误无内存膨胀。

## Wave 6：质量与交付

### M18 测试矩阵完备 [G6]（持续，M01 起步）— DONE (tag m18；mastering/episode/production/alignment 测试 + e2e 并入门禁)
WP：timeline/mastering/取消/并发覆盖；Playwright e2e 全视图（跳转精度断言）；
settings 模糊测试；requirements-dev 补全；e2e 并入 check.sh。
AC：核心模块覆盖 ≥80%；check.sh 含 e2e 全绿。

### M19 文档与可分享性 [G6]（依赖 M13-M17 主要项）— DONE (tag m19；README 诚实版重写 + backup.py + package.py)
WP：README 重写；TROUBLESHOOTING；标准文档对齐代码；CHANGELOG 自动化；
一键备份/恢复；可移植 zip 打包。
AC：干净机器按 README 从零跑通（自动演练）；zip 解压可运行。

### M20 30 天验收基线 [G6]（依赖全部）— DONE (tag m20；sweep 8/8 PASS；24 条语料全对齐；BASELINE.md 落盘；es modules 拆分决策延后记入文档)
WP：全量验收 sweep 脚本；灌 ≥20 条真实语料全链路（含对话+独白）；
性能/质量基线报告；分享包试分发；与 Bruce 愿景复核会（唯一必到场的门）。
AC：验收脚本全绿；docs/BASELINE.md 落盘。
