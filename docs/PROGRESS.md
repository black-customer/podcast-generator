# PROGRESS — 工作会话账本（每次会话重写本文件）

更新：2026-09-19 会话 2（长程批次继续；网络已恢复）

## 当前状态

- 完成：M01-M08、M10（9/20）+ 音色试听（M15 部分）+ SSE 逐词对齐落地（M02 收尾）
- 门禁：53 单元/API 测试 + 2 e2e 全绿；check.sh 含 ruff
- 网络尾项已清：SSE 探针→解析器校准→单次合成接 SSE→真实 AC PASS（mode=sse, 288 词, 5 句全准）
- 语料现状：02-sleep-healthy-eating/001 与 01-my-studies 全部条目均有逐词对齐（words）
  02 条目 mode=sse；my-studies 三条 mode=measured+words

## SSE 关键事实（来之不易，别再踩）

- 端点 POST /v1/tts/stream/with-timestamp，SSE，`data:` 行 JSON
- 每块多个事件（音频分片+渐进 alignment），alignment 是**块内本地时间**，
  全局 = chunk_audio_offset_sec + local；按 chunk_seq 取每块最后一个事件，按块序拼接
- 多说话人：reference_id 传数组 [A,B]，文本用 <|speaker:0|>/<|speaker:1|> 标记
- 词映射对话行：贪心 token 匹配（容错 3 词窗口，>80% 匹配率，数字/标签容错）

## 本批次落地

- M06：A-B 循环（金色标记）、句间导航、键盘（空格/←→/A/B/L/R）、词级卡拉OK渲染
  （words 存在时句内逐词点亮）、A24 程序性滚动判别、A32 跳转排队、A23 深链播放列表
- M07：路由令牌 viewStale（null=程序性重渲染）、轮询生命周期+熔断、audio onerror、
  去演示残留（Tom Holland/荷兰弟/硬编码语块）、e2e 自清理（try/finally + API 删话题）
- M08：中文参考面板（播放器开关）、轨道语义修正 A9/A19、真实轨道药丸 A27、
  对话条目禁用不可用音轨（消 404）
- M10：manifest 章节偏移 offset_sec + 原子输出； EpisodePlayerView 章节跳转；
  剧集过期检测 stale + 一键重建；now_iso 毫秒精度（修秒级碰撞）
- 音色试听：GET /api/voices/{ref}/sample（官方样本代理→缓存 data/voice_samples/→
  缺失时现场合成一句）；展台卡试听按钮（单实例播放器）
- 基建：now_iso 毫秒；get_topic 带 per-track 标志/时长/QA 结论

## 工程注意事项（新踩的坑）

- `set -o pipefail` 后跑 check.sh（管道吃退出码）
- MCP 浏览器 evaluate 只接受**表达式**（IIFE ok；var/function 语句不行）；
  hashchange 不会重载页面——改前端代码后必须 tab.reload() 再测
- e2e 依赖真实主语料 02-sleep-healthy-eating/001（对话+独白按钮禁用断言依赖其对话属性）
- now_iso 已是毫秒；时间戳字符串比较即可判新旧

## M11 已完成（tag m11）

- server/exports.py：export_m4b（ffmetadata 章节，AC=ffprobe chapters==N 且标题正确）
- export_srt（alignment→SRT，剥标签）
- API: POST /topics/{tid}/export/m4b、POST /topics/{tid}/items/{iid}/export/srt、
  GET /exports/{filename}（防穿越）
- 工作台按钮：导出 M4B / 导出 SRT（依赖 ManageState.editingItemId）
- item_title 增强：英文轨文本首行（剥 A:/B: 前缀）可作标题
- 测试：tests/test_exports.py（ffprobe 章节 AC + SRT 内容）

## M12 已完成（tag m12）

- server/exports_media.py：export_vtt（词级 cue 288 条）/export_lrc/export_srt/build_rss
- API：/api/rss.xml（局域网订阅，enclosure 绝对 URL）、
  POST .../export/vtt、/export/lrc、/export/srt
- 测试 tests/test_media_export.py（VTT 格式/LRC 时间标签/RSS 条目）

## M13 已完成（tag m13）

- PWA：manifest.webmanifest + sw.js（API 网络优先/静态缓存优先）+ 图标
- SW/manifest 根路径路由（main.py；曾 404）
- Media Session 锁屏控制（play/pause/prev/next/seek）+ 元数据
- 移动底部导航布局（≤860px）；修 updateMediaSession 作用域截断播放链的严重 bug
  （setTimeout 求值函数引用时同步抛错→playItem 断链→时间轴永不渲染；函数提升到顶层修复）
- 清理测试残留话题（debug-manage-x / e2e-manage-* / 01-persist）

## 下一步（按序，接着跑完 M11-M20）

1. M14 pipeline.py 批量改写落盘+lint；M15 voices.json 真源化；M16 自媒体模板；M17 性能
2. M12 字幕导出（alignment→SRT/VTT/LRC）+ 局域网 RSS（enclosure 绝对 URL）
3. M13 PWA（manifest+SW+Media Session+移动布局+配对二维码）
4. M09 UI 质感（设计令牌/空错态/截图审查子代理；es modules 拆分评估）
5. M14 pipeline.py 批量改写落盘+lint；M15 voices.json 真源化+表演规范 v2；
   M16 自媒体草稿模板；M17 /api/topics 索引缓存+500 条压测
6. M18 测试矩阵（timeline/mastering/并发覆盖、e2e 全视图、requirements-dev 补 playwright/requests）
   M19 README 重写+TROUBLESHOOTING+打包；M20 验收 sweep + docs/BASELINE.md + ≥20 条真实语料
