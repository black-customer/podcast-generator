# Q05：选题、找回答与继续使用

暖纸视觉沿用 Q04；本轮只完善现有选题、回答、浏览与收听流程。

## 入口与行为

| 任务 | 入口 | 行为 |
| --- | --- | --- |
| 筛出回答过的题 | 题库 → 作答状态 | 全部／未回答／已回答，与 Part、话题、考季和关键词组合；随机遵守同一筛选 |
| 查看旧回答 | 题库 → 已回答题目 | 默认最新创建的回答；下拉切换版本，原始回答与已有中英文分开 |
| 再回答／找回草稿 | 题目右侧；题库上方「找回未提交草稿」 | 不覆盖已提交条目；草稿不算已回答 |
| 搜索回答内容 | 我的语料顶部 | 搜索全部语料，或当前离线包；可直接查看、播放或进入原有学习页 |
| 继续收听 | 我的语料继续卡；普通播放 | 恢复真实音轨和时间；播放器「从头播放」可重置起点 |

- 已回答要求实际非空回答文本；只有题目或未提交草稿不计入。音频失败不改变回答事实。
- 创建时间决定回答顺序；修改正文、重制声音不改变顺序。无法确认时间时显示「历史回答」。
- 完整 Part 2 cue card 使用完整题干匹配；不只取标题首行。
- 搜索支持原始回答、题目、中文、英文及对话正文，300ms 防抖，Enter 立即搜索，每页 20 条。
- 搜索 URL 保存关键词和页码；清空回到原分类。读取时保留输入，结果区域不可操作，迟到响应不覆盖新页。
- 草稿 800ms 自动保存，离页立即保存。显示未提交、保存中、已保存和失败状态。
- 同题一份草稿，含文字和 Agent/API 模式；版本冲突保留本页文字，用户明确选择服务草稿或本页内容。
- 浏览器暂存未落盘内容；刷新后核对版本及完整题干。题目变化／消失时保留原草稿，允许复制，不自动套用。
- 提交成功只清除对应草稿；提交失败、版本冲突或等待期间的新文字仍保留。
- 单条双轨、桌面整集及完成页收听共用位置记录；只在实际播放后更新最近记录，每 5 秒和暂停／切曲时保存。
- 已听完只由 ended 事件确认。显式从头、点句、章节跳转优先。音频字节变化后旧位置失效。
- 在线位置保存在电脑服务；离线位置在设备内，不承诺电脑／手机自动同步。重新导入相同音频可恢复。
- 手机不新增学习或作答布局；从头播放入口位于播放页标题下，原有点句和中文切换保留。

## 最小接口增量

- `GET /api/bank/questions`：新增 `answer_status`，默认 all；旧 random 与 random_pick 均可用。
  随机响应保留原字段，追加 selected_page，供页面将随机题定位到可刷新恢复的 URL。
- `GET /api/bank/questions/{id}/answers`：实际回答引用、状态、创建时间；正文用现有条目接口。
- `GET /api/search`：扩展匹配范围、snippet、has_audio、study_status；page/page_size 可选，旧无分页结果保留。
- `GET /api/answer-drafts`：找回草稿，包括题干变化／缺失说明。
- `GET/PUT/DELETE /api/answer-drafts/{id}`：revision 校验；PUT 含 question_text、answer、mode、revision。
  DELETE 必须传 revision，清除后保留版本墓碑，防止旧写请求复活。
- `GET/PUT /api/listening-progress`：kind=item/episode、topic_id、item_id、track。
  PUT 还需 audio_fingerprint、position、duration、completed；由实际音频核对时长和指纹。
- `GET /api/listening-progress/latest`：返回最近仍可打开的来源，无记录为 latest=null。

私有文件为 `data/study_private/answer_drafts.v1.json` 和 `listening_progress.v1.json`，
version=1，records 是可读记录映射。采用锁与原子写；损坏或未知版本返回可恢复错误，不覆盖原文件。
私有读写沿用本机及来源保护，排除 Git、公开语料包和便携包。学习记录结构不变。

## 验收证据

截图使用合成题目、文字与静音音频，不含用户配置、密钥或真实回答。
before 来自 Q04 源码界面，after 来自本次 Q05 界面；三个桌面尺寸为
1536×1024、1280×800、1024×768；手机为 390×844、430×844。

截图保存在本目录 screenshots/；测试运行先写 data/.tmp/q05-ui，确认后再归档，
避免自动测试直接改动已提交截图。页面包括题库、语料、播放器、搜索、草稿失败及离线对应状态。

验证包含全量筛选／随机分页、时间排序、旧文本、草稿冲突和原子失败、搜索兼容，
双浏览器恢复、提交期间继续输入、迟到请求、真实播放后的即时恢复、失败位置保留。
HTTP 合成音频模拟 206 分段响应，恢复断言限制 3 秒，避免等待播放自然到达位置而误判。
局域网缺少 SubtleCrypto 时使用本地 SHA-256，验证标准 abc 测试向量。

最终命令、门禁结果及源码同步结果记录于 PROGRESS。无真实文本模型／TTS 调用。
GitHub Release、公开下载版本号和 APK/ZIP 上传不在本轮发布授权内。

最终验收：`bash scripts/check.sh --release`：238 passed / 1 skipped、42 E2E passed，
ruff／启动／打包隐私审计绿。Android debug 离线构建成功，8 份静态资源及 index／SW
与源码 SHA256 一致。便携包在临时中文目录启动并核对空配置、空记录成功。
浏览器模拟禁用 Service Worker，防止它绕过 Page.route 将测试位置写到个人文件。

代表截图：[桌面题库](screenshots/after-1280-bank.png)、
[语料搜索](screenshots/after-1536-search.png)、
[草稿保存失败](screenshots/after-1280-draft-failure.png)、
[手机离线播放器](screenshots/after-430-offline-player.png)。
