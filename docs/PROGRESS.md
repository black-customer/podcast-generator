# PROGRESS — 工作会话账本

更新：2026-09-19 会话 2 终版

## 最终状态：20/20 里程碑完成

M01-M20 全部 DONE。验收 sweep 8/8 PASS（scripts/acceptance_sweep.py → docs/BASELINE.md）。
测试：66 单元/API + 2 e2e，全绿。Git tag：v0.1, m02...m13, m17, m18, m19（逐里程碑）。

## 语料现状

- 3 个话题、24 条目、25 份 QA 报告（全 pass）、374 秒音频、全部条目有实测对齐
  （对话条目 mode=sse 逐词 288 词；独白条目 mode=measured + words）
- 示例语料 20 条为模板回答（dry-run 音频），Bruce 填入真实中文回答并重新生成后即为正式语料

## 关键工程事实（持续有效）

- SSE：/v1/tts/stream/with-timestamp；alignment 为块内本地时间；按 chunk_seq 取每块末事件，
  全局 = chunk_audio_offset_sec + local；多说话人 reference_id 数组 + <|speaker:i|> 标记
- 词映射对话行：贪心 token 匹配（3 词容错窗口、>80% 阈值）
- 摘要缓存：TTL 2s + scandir 签名；写路径（update_item_texts/meta/create_item）必须失效
- check.sh 必须以 `set -o pipefail` 运行；MCP evaluate 只收表达式；页面 hash 导航不重载
  ——改前端后必须 reload 再测
- 原生 confirm 保留用于删除确认（决策记录）

## 若继续（下一程候选）

- 词级卡拉OK在全部视图打磨；SSE 用于独白轨逐段（现逐段已有实测句级）
- M14 补充：pipeline.py 加 --batch 参数直连 import_batch
- 分享包实测：在干净机器解压 dist/bruce-corpus-share.zip 跑通
