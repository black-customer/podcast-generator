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
3. ⏳ B01 PC 题库（进行中）
4. B02 手机 APP；5. B03 分享开源（待做）
