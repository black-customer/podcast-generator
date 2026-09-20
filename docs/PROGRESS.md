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
