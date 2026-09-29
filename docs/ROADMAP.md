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

---

# 第二程：产品化主线（2026-09-19 PM 讨论定稿）

> 决策依据见 CONSTITUTION.md（2026-09-19 增补）。原 M 系列 20/20 完成，
> 视频字幕卡渲染器已按 Bruce 指示取消删除。本轮 = B01+B02+B03，B04 留下一轮。

### B01 PC 题库 — DONE (2026-09-19, tag b01；480 题/93 话题/2 题集已同步；17 单测 + e2e 全绿)
价值：选题→作答→音频闭环的入口（Bruce 优先级 1）。
数据源：`D:\project\RoastDuck\data\app.db` 只读直读 → 快照 `data/question_bank.json`
（questions: part 1-3 / text 含 Part2 cue card / textZh / normText 唯一；topics: 中英名/ieltsPart）。
快照制而非运行时依赖 RoastDuck；提供重同步命令。
WP：导入脚本；`GET /api/bank/questions?part=&topic=&q=&page=` + `GET /api/bank/topics`；
`#/bank` 视图（Part1/2/3 标签 + 话题筛选 + 搜索 + 分页，URL 参数驱动；Part2 cue card 全文；
已入库条目"已有音频"徽标按题干 norm 匹配）；作答提交 → 对应话题下建 item 进现有链路
（改写仍由 Agent 会话完成）。
AC：导入只读幂等（单测）；API 过滤/分页/搜索测试；e2e 浏览→筛选→提交→条目出现。tag b01。

### B02 手机 APP（Capacitor 独立 Android 应用）— DONE (2026-09-19, tag b02；APK 模拟器实测全流程通过)
价值：走路/通勤离线收听（Bruce 优先级 2）；形态=独立 APP，局域网网页只是过渡。
WP：语料包格式（zip：manifest 版本/指纹 + 条目文本 + timeline/alignment + 音频 + 题库快照）
与 `GET /api/pack/export`；前端 DataSource 抽象（server 模式=fetch API ↔ pack 模式=本地导入，
列表/播放视图复用，M13 移动布局复用）；`mobile/` Capacitor 工程 + 导入页（LAN 直传 /
文件选择器两种方式，数据存 APP 沙箱）；APP v1 = 题库浏览（随机来一题）+ 话题条目列表 +
播放页（音字同步高亮/点句跳转/逐词点亮/翻译层）+ 导入管理。
AC：pack 导出幂等与完整性单测；pack 模式渲染单测；APK 在模拟器实测播放页同步高亮（截图验收）。tag b02。

### B03 分享开源（交付"可推送状态"）— DONE (2026-09-19, tag b03；审计 0 泄漏，dist/ 就绪)
价值：让别人立马体验上（Bruce 优先级 3）；git push 由 Bruce 执行，Agent 只交付可推送状态。
WP：`git log -S` 全历史脱敏审计（API key 从未入库）；settings.example.json；
Bruce 真实语料与公开示例语料分离（代码公开/数据私有，RoastDuck 模式）；README 重写
（愿景 / 5 分钟上手 / fish.audio key 申请教程 + VPN 提示 / APK 安装与语料包导入指引 / FAQ）；
Release 附 APK + 可移植 zip（复用 M19 package.py 装配）。
AC：审计无泄漏（脚本验证）；干净检出按 README 跑通演练。tag b03。

## 质量重置（B04 暂停，完成 Q01–Q03 后恢复）

### Q01 Flash 开发质量护栏 [G1/G6] — DONE (2026-09-20, tag q01)
价值：让 ZCode/GLM 与 Qoder/Qwen 在不依赖强模型常驻的情况下少返工。
WP：精简强化根 AGENTS；按领域完成标准 playbook；Qoder 项目 Skill；纳入 `.zcodeignore`。
明确不做：自定义子 Agent、复杂 Hook、审查包或新任务系统。
AC：ZCode/Qoder 都能读取根规则；Skill 校验通过；全量门禁绿。tag q01。

### Q02 学习音频质量 2.0 [G2/G5] — ACTIVE（工程门禁已绿，待 Bruce 听感门）
价值：以最低复杂度改善母语口语自然度、青年男声和长期收听意愿。
WP：自然英文与轻量表演 prompt；统一 TTS payload 并修 SSE speed；候选男声盲选；
近讲清晰母带；播放页单条安全重制。旧语料不批量重生。
AC：参数/回退/母带/原子重制回归测试；5 条真实语料 A/B 中至少 4 条由 Bruce 偏好新版。tag q02。

### Q03 UI 3.0「安静编辑部」[G3] — DONE (2026-09-21, tag q03)
价值：让题库、文稿和播放成为主角，而不是仿流媒体的装饰封面。
WP：视觉稿选型定稿为「阅读札记 · Reading Notes」；题库/列表/播放/设置四视图重构；
文稿居中高可读札记流；底部精听控制栏重塑；移动端导航与迷你播放器避让；
无框架、无 CDN、不做全站模块化重写。
AC：桌面与移动截图走查通过；相关 Playwright e2e 4/4 全绿；check.sh 全量门禁绿。tag q03。

> 2026-09-21 复验发现移动播放器溢出且公开用户主链仍过于复杂。历史 tag 保留，
> 后续由 R01/R04 接续，不移动或重写 q03。

## 可分享版重构 R01–R05（2026-09-21 Bruce 定稿）

### R01 验收修复与产品契约 — DONE (2026-09-21, tag r01)
移动完整播放页隐藏底栏并增加双视口边界回归；check.sh E2E 独立端口与可靠清理；
更新产品契约、DESIGN 和受版本控制的十张概念图。AC：全量门禁绿。tag r01。

### R02 StepFun 正式语音引擎 — DONE* (2026-09-21, tag r02；*工程+技术验收绿：5/5 QA pass、时长比 1.02–1.19 无变速截断；4/5 听感门待 Bruce，A/B 清单在 data/.tmp/r02_acceptance/MANIFEST.md)
StepAudio 2.5 TTS 默认、Fish 兼容；角色化音色、provider-aware 设置/试听；真实 5 条听感门。
tag r02。

### R03 Agent/API 双模式生成 — DONE (2026-09-21, tag r03)
original_answer 永存与回退；POST /api/generation-requests 统一入口（Agent 默认不调文本 API、
API 模式 StepFun JSON Mode step-3.7-flash 一次三文本+修复重试一次+权限显式降级提示）；
agent-task 可重取；pipeline.py complete 先校验后原子写入；canonical skills/ielts-audio +
AGENTS 路由 + Qoder 薄包装；#/done 统一完成页。18 单测 + e2e 全绿。tag r03。

### R04 已批准 Web/Android UI — DONE (2026-09-21, tag r04)
按 docs/design/v1 概念图实现：IELTS Pod 品牌、导航收敛为开始练习/我的语料/正在播放/设置
（#/bank 保留别名、默认入口 #/practice）、今天想聊什么选题页、我的语料双分类
（雅思口语/日常表达，题干命中题库自动归类）、设置页双引擎卡+提问者/回答者角色卡
（性别→音色联动→试听，fish 模式映射 A/B reference）、首配向导 #/setup、普通界面删除
独白/女问男答/整集/章节术语；Android = ZIP+手动 LAN 导入、模拟器实测导入与逐词点亮播放。
tag r04。

### R05 公开分享闭环 — DONE (2026-09-21, tag r05; v0.5.0 beta；发布前复验补丁见 PROGRESS 会话 11)
README 重写（真实仓库地址 black-customer/podcast-generator、一条主流程、Agent 安装指令）；
scripts/doctor.py 只读诊断（密钥零明文，回归测试）；run.py 启动前置检查（端口占用显式报错/
ffmpeg 缺失提示）；package.py → dist/ielts-pod-portable.zip（内置审计：零密钥/个人语料/音频，
含 canonical Skill+Qoder 适配+公开题库+start.bat）；干净安装冒烟通过（临时目录解压→venv→
依赖→服务健康→诊断）；dist/ielts-pod-beta.apk；版本 0.5.0 + docs/RELEASE_NOTES.md。
Agent 不执行 git push，交付可推送状态。tag r05。

### B04 教学内容（下一轮）— PENDING（暂停至 R05 完成）
依据：CONSTITUTION「教学内容设计原则」。
WP：diff 机制（两种教学模式共用的原料库——我的表达 vs 母语者表达）；
纯英文双主持教学播客模板（锚定具体雅思题，主持人拓展同类表达变体）；
16:9 1-3 分钟视频模板；中英结合大众变体（后置）。
远期可选：中文主持音色；纠错式学员声（含 Bruce 原声方案）。

### B05 UI 2.0 重构 — PENDING（2026-09-20 Bruce 反馈：整体 UI 仍不满意）
 Bruce 仅给出方向性不满，待其给出具体不满意的页面/交互点（或截图）后开列细目。
 方向：对标成熟流媒体产品的视觉密度与交互一致性；首屏新手引导卡（key/音色角色）。
 关联：角色化音色选择 UI（提问者/回答者角色卡，性别→候选音色联动）已在 B06 一并考虑。

> 2026-09-29 新决定：视觉目标改为「暖纸自习室」，设计交接与后续实施按下方 L 系列执行；
> B05 保留历史描述，不用旧版流媒体方向指导新界面。

### B06 角色化音色选择 — PENDING（Bruce 理想用户旅程的唯一功能缺口）
现状：引擎已支持任意性别组合（answer_voice_male 方向规则 + A/B 音色），但 UI 是
"A 音色/B 音色/方向开关"三个离散概念，路人无法表达"男提问+女回答"。
WP：设置重构为「提问的人/回答的人」两张角色卡（性别选择 → 对应性别候选音色联动 →
试听选定）；音色候选库扩充（B05 前置已完成：voices.json candidate 层 9 个候选含真实合成试听）。
AC：女用户 3 次点击内完成"男提问+女回答"配置。

## 交付后维护

- 2026-09-26：Bruce 选定「对话成声」B 图案，统一 Web/PWA、Windows 快捷方式与 Android
  启动图标；同步修正 Android 壳的 `/static/icons/` 路径。此项为既有品牌资源维护，不新增里程碑。

## 下一程：单题逐句学习与暖纸桌面（2026-09-29 Bruce 定稿）

> 音频生成仍优先可听。历史 v1 学习概念图中的「选两个重点／可选局部填空／
> 强制换题挑战」已被以下流程替代；旧图留作历史。

### L01 暖纸自习室设计交接 — DONE (2026-09-29，设计交接；功能仍待 L02/L03)

交付 `docs/design/study-room-v2/`：33 个桌面主界面、8 个状态组图、1 张视觉规范图、
文字交互、准确示例、提示词与文档审计；更新 CONSTITUTION/PRODUCT/DESIGN 等现行约定。
AC：每页与状态都能从目录定位；同题完整流程无旧版步骤；图像与文字交互一致；
图片经查看，`git diff --check` 与 `bash scripts/check.sh` 全绿。此里程碑只验收设计，不代表功能已开发。

### L02 学习材料生成与数据层 — DONE (2026-09-29, tag l02)

用户中文／英文／混合回答 → 保留原话、忠实整理全意、英文示范与音频，并准备逐句对应的
中文意思、英文、文本讲解与有证据的错误分析。沿用 Agent/API 双模式和 data/ 人类可读接口。
先补校验、旧语料回退与回归测试，再改生成流程。音频一旦可用即能播放，材料状态独立。
AC：各句中文／英文／音频关系可追溯；没有原话证据时不虚构英文错误；改稿失效安全；
旧条目仍可播放，缺材料可补齐；既有三英文文本命令在扩展前仍可用。

### L03 桌面学习流程与复习 — DONE (2026-09-29, tag l03)

逐句整句默写为必经练习；提示 3／5／8 秒、反馈与讲解；学习前／看中文／脱稿三种
完整口答，保留已完成录音及重录；错句、用过提示和收藏句进入句子复习库。
AC：按设计图走通一题全部句子；提示不清空输入，检索前不泄漏答案；保存／退出／恢复、
录音权限与音频缺失均有可恢复状态；人工自评不伪装成自动雅思／发音评分。

手机端学习布局与跨设备记录同步留在后续设计；L01 不将桌面概念图当作移动验收。
