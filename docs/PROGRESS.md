# PROGRESS — 工作会话账本

更新：2026-09-19 会话 3（产品方向 PM 讨论定稿 + 第二程 B 系列开工）

## 本会话定稿（全部已固化进 CONSTITUTION.md，此处只留索引）

- 核心不变量：输入我的回答 → 必须直接得到母语者拟真音频（形式匹配、自动、永远优先）
- 优先级：1.PC题库 → 2.手机APP（独立应用）→ 3.分享开源 → 4.教学内容
- 取消：字幕卡视频渲染器（代码删除）；中文主持音色、纠错式学员声 → 远期可选
- 教学内容原则：锚定具体雅思题；短语通用+主持人拓展变体；纯英文双主持优先、中英结合后置；
  标准是"用户觉得学到了"（每期一个 15 秒可复述的 chunk）
- 手机 APP：Capacitor 独立壳；必需 = 文稿+音字同步高亮；其余功能记"将来可选"
- 数据源确认：`D:\project\RoastDuck\data\app.db`（45MB）含完整雅思题库，
  questions 表 part 1-3 + cue card 全文 + normText 唯一

## 上一程遗留事实（持续有效）

- M01-M20 全部完成（tag v0.1, m02…m20）；真实语料 9 波 108 条 + 示例语料，
  208 句/7588 词逐词对齐（对话 mode=sse 逐词，独白 mode=measured）
- M13 的 LAN/二维码方案被"独立 APP"决策取代，相关未提交代码已删除（见下）

## 关键工程事实（持续有效）

- SSE：/v1/tts/stream/with-timestamp；alignment 为块内本地时间；按 chunk_seq 取每块末事件，
  全局 = chunk_audio_offset_sec + local；多说话人 reference_id 数组 + <|speaker:i|> 标记；
  女问男答方向规则在 _synthesize_source 强制（answer_voice_male）
- 词映射对话行：贪心 token 匹配（3 词容错窗口、>80% 阈值）
- 摘要缓存：TTL 2s + scandir 签名；写路径（update_item_texts/meta/create_item）必须失效
- check.sh 必须以 `set -o pipefail` 运行；MCP evaluate 只收表达式；页面 hash 导航不重载
  ——改前端后必须 reload 再测
- 原生 confirm 保留用于删除确认（决策记录）
- git 数据策略：文本/meta/timeline 入库，audio*.mp3 不入库（可再生）；voice_samples 试听缓存入库

## 本会话执行记录

1. ✅ 愿景固化：CONSTITUTION 增补（核心不变量/优先级/APP 形态/教学原则/取消项）+
   ROADMAP 开列 B01-B04 + 本账本重写 → commit
2. ✅ 工作树清理：删 mobile_video.py、render-video/lan-info 端点、jobs render 任务；
   run.py 保留 --host/--port 参数但默认收回 127.0.0.1（开源后他人安全默认，
   B02 手机导入时用 --host 0.0.0.0）；Wave9 timeline 副产物与试听缓存入库 → commit
3. ✅ B01 PC 题库（tag b01）：
   - server/bank.py：只读直读 RoastDuck app.db → data/question_bank.json 快照
     （480 题/93 话题/2 题集；快照 gitignore，可再生 `python -m server.bank --sync`）
   - API：GET /api/bank/questions（part/topic/q/page，含话题计数与"已作答"徽标数据）、
     POST /api/bank/answer（中文→chinese 字段、纯英→natural_english；话题名=题库话题英文名，
     同名复用否则新建）
   - 前端 #/bank：Part1/2/3 标签 + 话题下拉 + 搜索 + 分页，URL 参数驱动；Part2 cue card 全文；
     作答卡提交后跳转话题页
   - 测试：tests/test_bank.py 17 个（同步只读幂等/查询过滤分页搜索/徽标匹配/语言分派/API）
     + tests/e2e/test_bank_ui.py（浏览→Part 切换→搜索→作答→话题出现，含清理）
   - 已作答徽标在真实库验证有效：Bruce 的 Wave 语料题目与题库 norm 匹配命中
4. ✅ B02 手机 APP（tag b02）：
   - server/pack.py：语料包导出（ZIP_STORED；pack.json manifest + content_hash + bank.json +
     条目 item.json[文本/meta/预计算双轨时间轴{lines,words,mode}] + audio_<track>.mp3）；
     GET /api/pack/export（topics=all 或逗号分隔）
   - web/packreader.js：零依赖 ZIP 读取器（只支持 STORED）；web/packmode.js：packApi
     （模拟 /api 契约子集）+ mediaUrl（blob URL）+ IndexedDB 持久化（存原始 zip）+ packRestore
   - app.js：api() 在 pack 模式拦截转发；壳内（Capacitor）无包首屏落导入页；
     #/import 视图（LAN 直传 + zip 文件导入 + 清除存档）；随机来一题/随机播一题；
     导航降级（pack/app-shell 模式隐藏服务端专属入口）
   - mobile/：Capacitor 7 工程（appId com.bruce.ieltspod；usesCleartextTraffic 放行 http 直传）；
     scripts/sync_mobile.py（web→www 同步 + Java17 补丁）
   - server/main.py 加 CORSMiddleware（壳内源 https://localhost 跨源拉包必需）
   - APK 实测（emulator API36）：首屏引导→LAN 拉包→媒体库→播放页逐词卡拉OK（blob 音频+
     当前句高亮+词点亮）→杀进程重启 IndexedDB 恢复，全链路通过
   - 测试：tests/test_pack.py 4 个（结构/幂等哈希/缺失话题/API）；tests/e2e/test_pack_ui.py
     （文件导入→列表→播放页 blob+时间轴→题库随机→导航降级）
5. ⏳ B03 分享开源（进行中）

## B01 补充工程事实

- e2e 断言注意事项：新作答条目无音频 → 话题页 audio 资源 404 属预期，
  console 过滤需排除 "Failed to load resource"；话题页条目列表异步加载须 wait_for_selector
- 题库快照不入 git（.gitignore），公开仓库用户无 RoastDuck 时题库页显示导入引导卡——
  B03 时决定是否把快照附 Release 供下载

## B02 补充工程事实（持续有效）

- 构建顺序铁律：`npx cap sync android` 会重新生成 Java21 配置 → 必须再跑
  `python scripts/sync_mobile.py`（Java17 补丁 + www 同步）→ `gradlew assembleDebug`
- Capacitor 7.6.9 也要求 Java 21；本机 JDK17 → 三处 gradle 文件补丁回 17（sync_mobile.py 自动）
- npmmirror 可用（npm 官方源不通）；gradle 缓存在 D:/Apps/DevCaches/gradle
- 壳内 fetch 局域网 http 是跨源（页面源 https://localhost）→ 服务端 CORSMiddleware 必需
- Android 输入框自动首字母大写：URL 校验正则必须加 i 标志
- mini player 覆盖底部导航（z-index 更高），UI 自动化点导航前要先让播放器消失
- WebView 无可达性树，UI 自动化用坐标（截图比例 900x2000 → 设备 1080x2400，×1.2）

## B03 执行记录（tag b03）

- 脱敏审计：真实 key 全历史 0 次出现（-S 片段扫描）；settings.json 从未入库；
  question_bank.json 已 ignore（含 Bruce 私有 RoastDuck 数据）
- README：愿景与核心不变量重述、fish.audio key 申请教程（含科学上网提示）、
  雅思题库闭环、手机 APP 两条装包路径 + APK 构建步骤、排错表 + FAQ
- 分享包：scripts/package.py 收入 mobile 工程（排除 node_modules/www/build/.gradle）；
  dist/bruce-corpus-share.zip 445KB/150 文件；dist/ielts-pod-debug.apk 4.1MB
- 分享包审计：无 settings.json、无个人语料、无真实 key（脚本验证）
- git push 由 Bruce 决定时机（AGENTS.md 禁止 agent push）

## 下一程：B04 教学内容（待 Bruce 启动）

diff 机制（我的表达 vs 母语者表达）→ 纯英文双主持教学播客模板（锚定具体雅思题）
→ 16:9 1-3 分钟视频模板 → 中英结合大众变体。原则见 CONSTITUTION「教学内容设计原则」。

## 2026-09-19 会话 4：Bruce 反馈三项修复（ee2dc34）

1. 题库考季筛选：快照题集 2026年1–4月(192)/5–8月(64)+跨考季"必考"（15题，14 道 Part2）；
   工具栏考季下拉 + 每行考季标签 + ?set= URL 参数；pack 模式 packBankQuery 同步
2. 已作答徽标细化：answered_items() 索引 norm→{topic,item,has_audio}（同题优先有音频条目）；
   绿「▶ 已有音频」/灰「已作答·未生成」两种徽标；作答卡内「▶ 去听已有的音频」跳转按钮
3. 音色展台：官方样本是克隆基模型声音（3 男声同音误导）→ 试听改真实合成优先
   （所点 ref 现场合成、缓存；官方样本降为 dry-run 回退且不落缓存）；4 音色已全部重合成
4. 顺带修复：RoastDuck personal 题册 5 道空题干题（text 回退 text_zh；answer 端点拒空题干）；
   服务端 CORS 后 01-persist 孤儿测试话题与 jobs.json 运行态出库（.gitignore）
5. e2e 教训：hash 路由 hashchange 异步派发，点击行后须等 fetch 渲染完成再断言（wait 700ms）

## 2026-09-20 会话 5：9–12月新题入库 + 必考题定义修正

- data/question_bank_extra.json（入 git）：麦门雅思 9–12月 Part1 新题整理件，
  16 话题 74 题（只题目不回答）；bank.sync_from_db 合并之（话题/题干去重、
  重复题挂考季、稳定 id q_x26q3_*）→ 快照 546 题/107 话题/3 题集（9–12月 71 题）
- 必考题定义修正（Bruce 定稿）：必考 = 固定五话题（Work or studies / Home-accommodation /
  Hometown / The area you live in / The city you live in），共 70 题；
  撤销之前"跨考季重复=必考"的自作主张定义；CORE_TOPIC_NORMS 全等匹配，
  Part3 的 "Work, Career & Success" 不会误伤；packmode.js 同步
- 教训：merge_extra 原地修改传入列表，测试需 deepcopy 基线；fixture 须隔离 EXTRA_PATH

## 2026-09-20 会话 6：路人闭环三件套（733a014）

1. 公开题库包：data/question_bank_public.json 入 git（523 题/101 话题/3 册，
   剔除 book_personal_ielts_answers 全部个人数据，脚本断言零泄露）；
   load_bank 回落（私有快照缺失时用公开包）→ 路人 clone/zip 开箱即有题库
2. 音色候选层：从 fish.audio 公共市场 500 条筛英语 TTS，人工选定 9 候选
   （女 4：Sarah 官方/ALLE/Friendly Women/E-girl；男 5：Ethan 官方/ELITE/Slax/adam/美区克隆），
   全部真实合成试听缓存；voices.json 加 tier 字段（preset/candidate），展台分组显示。
   待 Bruce 试听定夺去留
3. 一句话更新：VERSION(0.4.0) + health 返回 version + update_app.bat
   （git pull --ff-only → pip 同步 → taskkill /T 杀进程树重启 → 健康检查 → 开浏览器）
   + README「让 AI Agent 帮你装/帮你更新」段（给 Agent 的可复制指令）
4. ROADMAP 新增 B05（UI 2.0，待 Bruce 具体不满点）与 B06（角色化音色选择——
   提问者/回答者角色卡，Bruce 理想旅程唯一功能缺口）
5. 坑：uvicorn 父子进程互拉，杀端口进程须 taskkill /F /T 杀树；
   git checkout -- data/ 会复活已 git rm 的目录（01-persist 二次删除）

## 2026-09-20 会话 7：质量重置启动（Q01–Q03）

- Bruce 定稿轻量质量重置：目标是“愿意反复听、适合模仿的个性化英语输入”，
  不把项目扩张为专业播客生产平台；B04 暂停至 Q03 完成。
- Q01：根 AGENTS 增加可验证完成定义；新增按音频/UI/data 分类的短 playbook；
  Qoder 增加 `podcast-quality` Skill；审核纳入 `.zcodeignore`。
- Q02/Q03 范围锁定：不做多模型审稿、ASR、自训练、旧语料批量重生、前端全面模块化。
- Q01 验收：Qoder Skill 校验通过；`scripts/check.sh` 全绿（94 passed, 1 skipped；
  ruff、导入、启动冒烟均通过）。
- 下一步：TDD 实现 Q02；真实 TTS 与最终音色选择留给 Bruce 听感门。

## 2026-09-20 会话 8：Q02 工程完成，等待听感门

- Prompt A/B 收敛为“自然但略经整理”的学习口语 + 稀疏 Fish 表演指令；
  `podcast_script` 优先、旧 `podcast_text` 回退语义保持兼容。
- TTS 三条路径统一 payload：speed/temperature/top_p/repetition penalty/上下文连续性；
  只允许 `s2.1-pro-free`，quality-guard 不可用时仅移除该 feature 重试。
- 男声收敛为 Alex/Ethan/ELITE/Adam 四个美式青年候选；旧 Peter 设置读取时迁移到 Ethan；
  试听改用候选独立参数与固定长试听稿，未调用真实 TTS。
- 母带改为单声道近讲清晰链；播放页增加单条安全重制，QA 通过前不覆盖旧成品。
- 修复 `test_jobs_v2` daemon 线程跨 fixture 污染真实 data/；完整门禁后确认 `ORPHAN_CLEAN`。
- 工程验收：`scripts/check.sh` 全绿（108 passed, 1 skipped），播放器 E2E 1 passed。
- 待 Bruce：在音色展台生成/试听新版四男声，选定一个并完成 5 条真实语料 A/B；
  通过后将 Q02 标记 DONE 并打 tag q02。

## 2026-09-20 会话 7：StepFun TTS 2.5 A/B 对比基线

- scripts/ab_stepfun.py：控制变量对比（同文本/同性别角色/同 -16 LUFS 母带链），
  key 存 data/.tmp/stepfun_api_key.txt（gitignored，不进 git/日志/回显）
- StepFun API：POST api.stepfun.com/v1/audio/speech，model=stepaudio-2.5-tts，
  Bearer 认证；voice 官方音色名；instruction 全局情绪指令（≤200字）；
  SSE + 词级 timestamp（未来集成对齐层的路径）；免费档限流 10 RPM（脚本 6.5s 节流+429退避）
- 对照产物 data/.tmp/ab_stepfun/：独白×2 男声变体（vibrant-youth/soft-spoken-gentleman）
  + 对话×2（A=lively-girl）——对话源必须用 fish_script.txt（fish 生成对话轨的真实源，
  首跑误用 natural_english 导致文本不同已修正）
- 待 Bruce 试听裁决：引擎去留 + StepFun 男声变体偏好

## 2026-09-21 会话 8：Q03 UI 3.0「安静编辑部」收敛与交付（tag q03）

- 视觉定稿与设计契约：明确「阅读札记 · Reading Notes」风格，更新 PRODUCT.md；
  删除巨大黑胶唱片、装饰封面与未播放文本的低透明度淡出；默认入口收敛为题库 `#/bank`；
  导航收敛为题库、语料库、正在播放、设置。
- 界面重塑：四大核心视图（题库、话题列表、播放页、设置）全面重构；
  文稿采用 `.transcript-row` 单栏高可读札记流，黄底柔和当前句高亮与当前词点亮；
  设置页将底层参数收入折叠卡，优先呈现音色选择。
- 底部 Mini Player 精致重塑：文档标记图标、传送带控制、等宽时间戳（00:00/00:00）、
  音量滑块、倍速切换、中文参考切换、单句重播、A-B 循环、使用当前音色重制此条。
- 移动端适配与安全区：`.global-player` 与移动端底部 4 项导航分层避让，
  时间进度水平紧凑布局，搜索栏与全宽随机抽题按钮防挤压防重叠。
- 测试与门禁：修复 `test_pack_ui.py` 中的文稿选择器兼容，Playwright 4 个 E2E 全绿（13.94s）；
  Playwright 桌面（1280x800）与移动端（390x844）全视图截图走查通过；
  `scripts/check.sh --with-e2e` 全量门禁全绿；打 tag `q03`。

## 2026-09-21 会话 9：可分享版 R01–R05 启动

- Bruce 定稿新主链：安装配置 → 选题 → 回答 → Agent/API → StepFun 音频 →
  网页下载/精听 → Android 导入。
- 产品决策：Agent 模式默认；API 模式共用 StepFun Key；StepFun TTS 2.5 默认、Fish 备选；
  提问者/回答者性别与音色独立；普通 UI 隐藏独白、多轨、整集与 TTS 表演稿。
- 已批准十张 v1 概念图；03 修订为双模式，Android v1 只做文件与手动局域网导入。
- R01 回归测试已先红后绿：390×844、412×915 完整播放器隐藏底栏且控件不溢出。
- R01 完成：产品契约、DESIGN、概念图、移动修复与 check.sh 独立 E2E 端口已落地。
- 完整门禁：ruff 绿；108 passed、1 skipped；独立端口 Playwright 6 passed；服务冒烟绿。
- 下一步：R02 将 StepFun 实验提取为正式 provider；真实调用留到 5 条听感验收门。

## 2026-09-21 会话 10：R02 StepFun 正式语音引擎完成（tag r02）

- 上会话遗留的工作树改动经审阅确认为 R02 半成品，全部保留并续完：stepfun.py 客户端
  （950 字符/429 Retry-After 退避/取消/24k→44.1k mono 128k 标准化）、config provider 默认值
  （旧安装有 Fish Key 保持 fish，不迁移密钥）、tts.py 逐行角色合成路径（问/答独立音色、
  280ms gap、QA+母带复用）、api.py provider-aware voices/sample/settings-test 与双 key 脱敏。
- 本会话补齐：设置页 provider 化（语音服务切换 + StepFun Key + 提问者/回答者音色下拉 +
  provider 连接测试；fish 参数收入折叠卡）；voices.json StepFun 2 女 2 男（含全部规范字段）。
- 真实验收 scripts/r02_acceptance.py（key 内存注入不落盘）：5 条代表语料（2 独白 + 3 对话，
  含 CJK 路径）全 PASS：QA verdict pass、无静音孤岛/削波、与 Fish 时长比 1.02–1.19。
  A/B 清单交付 data/.tmp/r02_acceptance/MANIFEST.md 待 Bruce 听感门（4/5 偏好）。
- 完整门禁：ruff 绿；116 passed 1 skipped；e2e 6 passed；服务冒烟绿。
- tag r02（DONE*：4/5 听感门待 Bruce，工程不阻塞 R03）。

## 2026-09-21 会话 10（续）：R03 Agent/API 双模式闭环完成（tag r03）

- 数据层：original_answer.txt 入 FIELD_FILES/TEXT_FIELDS（不入 STALE——改原始回答不使音频过期）；
  旧条目回退语义 original_answer → chinese → natural_english（rewrite.original_answer_of）。
- server/rewrite.py：StepFun JSON Mode（step-3.7-flash）一次产出 natural_english/podcast_text/
  podcast_script；校验=字段完整+A/B 对话格式+可见文本零标签+表演稿白名单标签+词义一致性
  （内容词 jaccard≥0.35）；结构失败带错误清单修复重试一次；401/403/无 Key → TextPermissionError
  显式提示改用 Agent 模式，不静默降级。
- POST /api/generation-requests：question_id 或 question+topic → 建条目（original_answer 永存）
  → Agent 模式返回 agent_prompt（绝不调文本 API）；API 模式走 jobs.start_api_generation
  （rewrite→save→tts 三阶段 phase），失败保留原始回答不产生音频。
- GET /api/topics/{t}/items/{i}/agent-task：指令刷新后可重取。
- pipeline.py complete 子命令：先校验后原子写入再合成（--no-audio 支持），输出 play_url+mp3_path。
- canonical skills/ielts-audio/SKILL.md + 根 AGENTS 路由段 + .qoder 薄包装。
- 前端：题库作答卡双模式（Agent 默认/API 可选）；Agent 等待态（复制指令+2s 轮询+focus 立即检查
  →自动跳完成页）；API 三阶段进度+失败显式回退按钮；#/done 统一完成页（干净英文阅读版显示层
  剥离旧数据残留标签，表演稿无入口，下载 MP3 + 精听入口）。
- 测试：test_generation_modes.py 18 个（数据回退/校验/修复重试/权限快速失败/双模式全链 mock/
  CLI/同构断言）；e2e test_dual_mode.py（复制→CLI 完成→占位音频→自动跳完成页→无表演稿泄露）；
  既有 bank e2e 第 5 步同步新流程。134 passed 1 skipped + e2e 7 passed 全绿。tag r03。

## 2026-09-21 会话 10（续 2）：R04 已批准 Web/Android UI 完成（tag r04）

- Web（按 docs/design/v1 十张概念图 + 计划文本）：品牌换 IELTS Pod（Speak·Practice·Progress）；
  导航固定为开始练习/我的语料/正在播放/设置，默认入口 #/practice（#/bank 别名保留）；
  选题页标题「今天想聊什么？」；我的语料 = 雅思口语/日常表达双分类（bank.category_index +
  topic_category：题干 norm 命中题库或名称启发；pack 模式默认 ielts）；继续上次收听卡
  （localStorage）；话题页删除独白/女问男答/整集/章节播放术语，单一「可精听」状态。
- 设置页（概念 07）：双引擎卡（StepFun 推荐 / Fish 备选，各自 key+测试连接）主层；
  提问的人/回答的人两张角色卡 = 性别切换→音色网格→试听→选中（fish 模式自动映射 A/B
  reference——B06 旅程在双引擎下打通）；语速/模型名/fish ID/dry-run 收入高级折叠。
- 首配向导 #/setup（概念 01）：三步单页（连接服务→提问者→回答者→保存并开始选题）；
  练习页无 Key 时显示引导横幅。
- Android：构建顺序修正——webDir=www，必须 sync_mobile → cap sync → sync_mobile（Java17 补丁）
  → gradlew；APK 更新必须卸载重装（WebView service worker 缓存旧资产导致白屏）。
  模拟器 API36 实测：LAN 导入（10.0.2.2:8766）→ 我的语料双分类 → 播放页逐词点亮+
  黄底当前句高亮+精听栏；播放路由无底部导航。
- 门禁：ruff 绿；134 passed 1 skipped；e2e 7 passed（manage 断言更新为双引擎测试按钮）。
  截图走查：设置/向导/练习/语料/完成页（桌面+移动）。tag r04。

## 2026-09-21 会话 10（续 3）：R05 公开分享闭环完成（tag r05, v0.5.0 beta）

- scripts/doctor.py 只读诊断：Python/ffmpeg/依赖/引擎配置（脱敏）/音色库/题库/语料目录/端口
  占用（探活 /api/health），每项带下一步提示；密钥只出现前 3 位+长度，测试断言零明文、零写入。
- run.py 前置检查：端口被占直接报错并给两条出路（旧服务在跑→直接开网页；否则换端口），
  绝不静默测试旧服务；ffmpeg 缺失给出 winget 安装提示。
- README 重写：真实仓库 https://github.com/black-customer/podcast-generator、一条主流程、
  Agent 安装指令带真实地址、StepFun 主 / Fish 备、doctor 排错入口；移除旧工作流描述。
- package.py 重写 → dist/ielts-pod-portable.zip：收入 skills/ielts-audio、.qoder 适配、
  question_bank_public.json、start.bat；打包后逐条审计 zip 内容（settings.json/个人语料/
  voice_samples/.tmp/私有题库/音频 APK 任一命中即失败并删除产物）。
- 干净安装冒烟：解压到临时目录 → python -m venv → pip install → run.py 起服务 →
  health 返回 0.5.0 且 data_dir 隔离 → doctor 全项可读 → 端口冲突报错符合预期。
- 产物：ielts-pod-portable.zip (1.4MB/182 文件) + ielts-pod-beta.apk (4.2MB)。
  git push 与 GitHub Release 由 Bruce 决定（AGENTS.md 禁止 agent push）。
- 门禁：ruff 绿（scripts/ 新文件均达标；acceptance_sweep.py 一处历史超长行在门禁范围外）；
  136 passed 1 skipped；e2e 7 passed。tag r05 → R01–R05 全部完成。

## 2026-09-21 会话 11：R01–R05 独立复验与发布前修复

- 独立复验确认五个里程碑提交/tag 和分享产物存在；重新运行当前 HEAD 完整门禁。
- 修复生成策略回归：API Prompt、Agent task 与 canonical Skill 不再允许 `[chuckle]`、
  `[sigh]`、呼吸或通用 `[pause]`；新稿只允许 Q02 定稿的五种轻量标签与数量上限。
- 修复公开 UI：题库隐藏 5 条“原问句缺失”内部占位；非播放页隐藏旧播放器；完整播放页
  隐藏多轨/独白控件与 A/B dialogue 后缀；设置角色摘要按当前 provider 显示真实音色名；
  旧内容管理默认折叠并保持展开状态；题库改为双列任务卡，移动导航不换行。
- 修复 Windows 分享闭环：doctor.py 改用 GBK 安全的 ASCII 状态标记，真实默认控制台运行通过。
- Android 重新 sync + Gradle assembleDebug 成功；beta APK 和 portable ZIP 已用最终源码重建。
- 最终门禁：ruff 绿；143 passed、1 skipped；Playwright 7 passed；服务冒烟绿。

## 2026-09-23 会话 12：Bruce 个性化口语学习包一期（7 音频 + 22 卡）

- 输入：三份雅思口语真实转写（Desktop/雅思，约 2 万词），逐句建立错误清单（十大高频伤口：
  可数性/三单/完成时分词/he-she/sceneries 假朋友/learn knowledge 直译/词汇缺口卡死/
  转折单一/you know 依赖/depend-suggest 句型）。
- 设计依据（检索于 Web）：Noticing 假说（Schmidt 1990）、检索练习+间隔重复（测试效应
  30-50% 保留提升；Nakata 2017）、语块训练提升口语流利度（Albelihi 2022 Frontiers）、
  shadowing 系统综述（Whitworth 2025）。每集结构=错误对比→语块特写→提示音+8s 强制
  开口检索→8.5 分母语者示范（Bruce 真实内容）→带走句。
- 交付 bruce_kit/：00_START_HERE 诊断与使用指南；episodes/EP1-EP7 文稿 JSON（入库）；
  audio/ 七条 MP3 共 19.2 分钟（不入库，可由脚本再生）：EP1 语法急诊室 / EP2 词汇打假 /
  EP3 Part3 军火库 / EP4 流利度手术+AREA 框架 / EP5 我的故事母语者版 / EP6 影子跟读十四句 /
  EP7 热身十一连；cards/ 22 张 1080x1350 PNG（A 错误修补 x10 + B 语块 x8 + C 总览 x4）；
  index.html 播放索引 + 打开学习包.bat。
- 脚本：scripts/generate_bruce_learning_kit.py（Fish 免费档 s2.1-pro-free 真实合成，
  内容哈希缓存于 data/.tmp/bruce_kit_cache，断点续跑；dlg 多说话人单次生成/shadow 逐句
  +等比停顿/warmup 提示-窗口-答案）；scripts/generate_bruce_kit_cards.py（PIL 生成 22 卡，
  西文整词换行器，全部可再生）。
- 质检：响度 -16 LUFS、峰值 -1.8 dB 无削波；EP1 恰一条 8.3s 检索静音、EP7 恰 11 条 5s 窗口；
  卡片经 judge 三轮验收全过（修复：英文断词换行、C1 页脚碰撞、C2 中文字体豆腐块与行溢出、
  C4 页脚文案重复）；check.sh 全量绿（143 passed 1 skipped + 冒烟）。
- 未做（刻意）：视频版（与音频图卡内容重合，宪法已取消字幕卡渲染器）；发音专项（转写掩盖
  发音证据，待 Bruce 录音后做二期）。git push 与是否试听后调整，由 Bruce 决定。

## 2026-09-24 会话 13：全项目 review + 学习套件 organic 版入库 + 首次授权 push

- 全项目 review：`check.sh --with-e2e` 全量门禁绿（ruff 绿；143 passed 1 skipped；
  Playwright 7 passed；导入/启动冒烟绿）。main..HEAD 七个提交（one-question 工作流两变体、
  StepFun 切换、Qwen 实测评议、HTML 修复）全部收敛于 `workflows/qoder-one-question/`，
  产品代码（server/web/data/tests）零改动，无回归风险面。
- 未记录会话产物归属确认（AGENTS 协议）：bruce_study_suite 及 6 个 scripts/ 脚本为上一
  会话「organic 漫谈版」交付——从考试训练风（beep+8s 检索留白）转向纯母语生活漫谈播客
  （Sarah & Ethan 双主持，零说教零测验），磁盘 index.html/STUDY_GUIDE 为 organic 版终态。
- 入库：6 脚本（生成/工作台两代）+ index.html + STUDY_GUIDE.md + 10 张概念图（图片不可由
  仓库代码再生且被工作台引用，故入库）；音频可由 `generate_organic_suite.py` 再生，不入库
  （.gitignore 新增 `bruce_study_suite/audio/` 与根目录 `/*.mp3`，延续 bruce_kit 惯例）。
- 脚本清理：F401 未用导入 / I001 / F541 / 行尾空白修净；E501（台词长行）与 E402
  （sys.path 引导，同 tests/pipeline.py 豁免模式）按 scripts/ 惯例保留；py_compile 全过。
- 工作台验证：index.html 标签闭合完整（5 组闭合标签各 1）、5 期 EPISODES 数据齐全、
  10 图 + 5 音频引用零缺失，音频实测 67.8–78.5s/条。
- push：本会话 Bruce 明示「整个项目提交到 GitHub」，属 AGENTS push 禁令的显式授权例外；
  main fast-forward 至 workflow/qoder-one-question 并推送，分支一并推送。
  并发 worktree（podcastGenerate-glm / workflow/glm-question-coach）未触碰，留 Bruce 裁决。

## 2026-09-26 会话 14：全项目审查问题修复

- 访问控制：跨源请求只允许 Capacitor 本地源；局域网模式仅开放带启动时临时配对码的
  语料包下载，手机导入页与 README 同步增加配对码输入。
- 生成一致性：话题任务在目标选择后再次加锁核对；整集合成不再越过运行中的生成任务；
  API 模式启动冲突清理新建条目与空话题；生成期间改稿保留 stale 标记。
- 内容与导出：A/B 稿件必须有完整问答；StepFun 分段不超过 950 字符；语料包每次独立生成
  并在发送后清理；整集音频与字幕严格按请求轨道返回；RSS GUID 稳定且日期符合邮件格式。
- 回归测试先红后绿（12 个原始场景全红，修复后扩为 13 个全绿）；完整门禁：ruff 通过、
  156 passed / 1 skipped、Playwright 8 passed、服务冒烟通过。导入页桌面 1280×800 与手机
  390×844 截图检查：配对码输入完整，无横向溢出。Android 资源已同步，Gradle debug APK 构建成功。
- 补入 main 并与图标改动合验：157 passed / 1 skipped、Playwright 8 passed、服务冒烟通过；
  Android 调试包与 Windows 可移植包按整合后的源码重建。

## 2026-09-26 会话 15：跨端品牌图标统一

- Bruce 在两轮内置生图预览后选定第一轮 B「对话成声」。保留 1254px 原始母版，
  `scripts/make_icon.py` 从母版生成 Web/PWA 32/192/512 PNG、Windows 多尺寸 ICO、
  Android 五密度方形/圆形/自适应启动图标；自适应图案收进安全区。
- PWA manifest 更新为 IELTS Pod 与品牌色，网页补 favicon，service worker 缓存版本更新。
- 修复 Android 壳把图标同步到 `/icons/` 而页面请求 `/static/icons/` 的路径错位；
  先写失败回归测试，再修正并验证通过。
- 视觉走查：512px、32px、Android 圆形与自适应裁切预览均可辨识，图案未被裁掉；
  本机无已启动模拟器，未做实机桌面截图。
- 验证：图标脚本 ruff 绿；Android `assembleDebug` 成功；`check.sh --with-e2e`
  144 passed、1 skipped、Playwright 7 passed、服务冒烟绿；portable ZIP 审计通过。
- 交付产物：`dist/ielts-pod-b-icon-debug.apk`（调试包）与
  `dist/ielts-pod-portable.zip`（Windows 可移植包）。

## 2026-09-28 会话 16：学习模式研究与设计提案

- Bruce 提出增加主动学习模式，本轮范围为研究与设计。新增
  [LEARNING_MODE_RESEARCH.md](LEARNING_MODE_RESEARCH.md)：29 篇研究/综述与 IELTS 官方标准，
  标明阅读范围、证据边界和设计推论；覆盖注意、检索、间隔、反馈、口语、跟读、书写与迁移。
- 建议主流程：尝试表达 → 定位差别 → 重点模仿 → 遮答案口答 → 新情境使用 → 跨天复习。
  拼写作为搭配、词形和听辨困难的辅助，是否进入默认流程由等时长口语试验决定。
- 提案含完整训练示例、第一版范围、旧数据/离线包/音频定位约束，以及延迟新题口答的验证方案。
  旧宪法与 PRODUCT 的学习模式禁令已指出，并提供修订草案；未修改宪法或开发里程碑状态。
- 本轮仅新增研究报告及账本记录；未改产品代码或语料，未调用真实 TTS。
- 验证：使用 Git Bash 运行 `bash scripts/check.sh`，ruff、157 passed / 1 skipped、
  导入和服务启动冒烟全绿。初次沙箱启动 Git Bash 因 Windows 信号管道权限失败，获执行权限后通过。
  文档任务未运行 E2E，未宣称学习模式已有 UI 或听感验收。

## 2026-09-28 会话 17：学习模式用户流程概念图

- 根据 Bruce「从用户视角看每一步」的要求，使用内置 ImageGen 生成五张桌面概念图，
  共十个连续状态：入口、先说、看重点、跟读、可选填空、脱稿短句、完整原题、换题、收尾、次日复习。
- 使用同一道下班活动题贯穿；每屏突出当前任务与主按钮。录音时长与学习结果为示例，
  开放口答采用回听与自评，不展示虚构的自动口语分数。
- 交付位于 `docs/design/learning-mode-v1/`：五张 PNG、按顺序阅读的 README 与完整 PROMPTS。
  所有图片已查看；定向修正图 2 题干漂移、图 5 次日复习误带六阶段导航两处问题。
- 本轮是界面概念预览，未实现功能、未改生产 UI/语料、未调用 TTS，未改里程碑或宪法。
- 验证：`bash scripts/check.sh` 全绿（ruff、157 passed / 1 skipped、导入与启动冒烟）；
  `git diff --check` 通过。图片为桌面概念验看，未作生产 UI 的 E2E 或移动端验收。
