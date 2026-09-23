# 验收报告 · 单题工作流（2026-09-23 夜间自主完成）

分支：`workflow/qoder-one-question`（从 `main` 切出，**项目原有文件一个都没改**）

## 你要的两件事，做完了

**Stage 1 —— 一道题 + 你的回答 → 一份你学得完的教学包**
规范在 `skills/one-question/SKILL.md`，引擎在 `scripts/one_question/`。
下次你只要对 Agent 说「用 one-question 工作流，题目是 X，我的回答是 Y」，它自己跑完。

**Stage 2 —— 把教学包包装成能发布的作品**
规范在 `skills/one-question-creator/SKILL.md`，工具是 `python -m one_question.creator`。
这一层明确标注为**你的私有能力，开源时整层删掉不影响 Stage 1**。

## 实验题：Do you have a favourite teacher?

产物在 `lessons/01-favourite-teacher/`，双击 `page.html` 就能看。

诊断器对你那句话的量化结果（`diagnose.json`）：

- 54 词里 **`kind of favorite teacher` 出现 2 次**、`don't have kind of favorite teacher` 2 次
- `common interacts`（动词当名词用）、`learn knowledge`、`teach me knowledge`、`a deep relationship` 各 1 次
- 理由 0 次、例子 0 次、让步 0 次、观点标记种类 0
- 填充词密度 **7.41 / 百词**（母语者 casual 约 0.2–0.5）

**这一题真正的失分点不是语法，是"说完就没有了"。** 所以示范答案没有堆高级词，
而是把你自己在另一份稿子里说过的「最近帮我最多的就是 AI」搬进来了——一句假话都没编。

示范答案（84 词，5 句，三个语块全部用上）：

> I don't really have a favourite teacher, **as such**. I've had good teachers, but I was never
> **close to** any of them — I'm the quiet one who sits at the back. They delivered the lesson,
> I took the notes, and that was that. If you ask who's actually taught me the most recently,
> **what comes to mind** isn't a person at all — it's an AI. It answers questions without judging
> me for asking them, which is exactly what I couldn't do in a classroom.

## 音频：已改用 StepFun stepaudio-2.5-tts，已生成

你给的 key 之前项目里没有，已写入 `data/settings.json` 的 `stepfun_api_key`
（该文件在 `.gitignore:15`，不会进 git），`tts_provider` 切到 `stepfun`。
**建议你把这把 key 轮换掉**——它出现在对话记录里了，而对话会被同步。

`server/stepfun.py` 里的 `MODEL` 本来就是 `stepaudio-2.5-tts`，所以项目侧不用改，
我只给工作流引擎加了按 `tts_provider` 分发的能力（Fish 走多说话人单次合成，
StepFun 一次只能一个音色，所以逐行合成再拼接，A 用 `lively-girl`、B 用 `vibrant-youth`）。

**踩到一个真实的坑并修了：** StepFun 免费档限 **10 请求/分钟**，逐行合成第一版直接撞 429。
现在引擎按 `stepfun_rpm`（默认 9）主动压速，不再靠上游重试硬撞。

成品：`lessons/01-favourite-teacher/audio.mp3`，**6:28 / 388 秒**，7 个强制输出窗口。

## 短片：已生成

`lessons/01-favourite-teacher/short.mp4`，1080×1920，**41 秒**，h264 + aac，322KB。
逐镜结构就是规范里那六拍（钩子 → 错版 → 正确版 → 语块 → 抽问 → 评论区收口）。
首版内容挤在画面上 1/3，手机上看会被平台标题栏压住，已改成上下弹性居中并放大字号。

## Minimax H3：起不来，原因不是我不会操作

三条硬事实：

1. **机器上没有任何 MiniMax 部署**——HF 缓存里只有 `faster-whisper-base.en`，
   没有 ComfyUI、没有 sglang/vLLM、没有权重目录，常见推理端口一个都没在监听。
2. **显存不够。** 你是 **RTX 5060 Laptop，8GB**。H3 这类视频模型 INT8 也要 ~14GB 起。
   这不是下载能解决的问题，硬件到不了。
3. C 盘只剩 47GB（已用 82%），权重本身要几十 GB。

所以我没有"帮你把它调起来"这条路可走。真要上，只有两个选择，**都要你决定，我不擅自动**：

- **走 MiniMax 云端 API**：需要你在 platform.minimaxi.com 开一把 key，按量付费。
  适配器 `one_question/minimax.py` 已经按官方异步接口写好了，你给我 base_url + key 就能用。
- **换台有 16GB+ 显存的机器**跑本地权重。

现在 `--motion` 检测不到服务就自动跳过，静态封面照常出，不阻塞发布。

## 已经验证过的（不是"应该没问题"）

| 检查 | 结果 |
|------|------|
| 剂量校验测试 | `9 passed`（含 4 个"超限必须拒绝"的反向用例） |
| 反向用例：加第 4 个纠错点 | 被拒绝 ✓ |
| 反向用例：把用户错误原话改漂亮 | 被拒绝 ✓ |
| 反向用例：示范答案漏用语块 | 被拒绝 ✓ |
| `bash scripts/check.sh` | **CHECK GREEN**，143 passed / 1 skipped |
| ruff（整个 workflows 目录） | All checks passed |
| 三张卡逐张看图 | 发现并修掉：语块卡第三块被裁切、滚动条出现在封面右上、答案卡留白失衡 |
| 卡片自动缩放 | 内容超高时整体 zoom，实测三张卡零裁切 |
| 短片 ffmpeg 拼接路径 | 用静音占位音跑通，产出 19.5s 有效 mp4（**最终旁白版待网络**） |
| 页面浏览器实测 | 3 图加载、0 破图、降级提示可见 |
| API Key | 全程未读取未打印 |

## 关于 Minimax

我查了官方文档并写了适配器 `scripts/one_question/minimax.py`（异步任务：提交 → 轮询 → file_id → 下载），
配置只从环境变量读：`MINIMAX_BASE_URL` / `MINIMAX_API_KEY` / `MINIMAX_MODEL`。

**但我探测了你机器上所有常见推理端口（8000/8001/5000/5001/7860/8188/3000/8080/11434/1234/30010），
没有任何一个在提供模型服务**——回应的都是 QQ、微信、Armoury Crate、OneDrive 这类普通应用。
所以 `--motion` 现在是空转（会自动跳过，不阻塞出片）。你把服务起起来、告诉我端口，它就能用。

我的判断（你让我定的）：**Minimax 只用在一处——把封面做成 3–5 秒有呼吸感的开场。**
理由很硬：文字必须清晰，而视频模型会糊字，所以带字的帧永远由我们的 HTML 渲染提供，模型只负责"动"。
口播数字人要露脸授权、全生成场景废片率高，都不划算。

## 关于并发

同一时间有另一个会话在这个仓库里产出了 `bruce_kit/`、`bruce_study_suite/`、
`scripts/generate_bruce_learning_kit.py` 等一批同类文件（时间戳和我的构建完全重叠）。
**我没有动它们，也没有提交它们。** 你要不要合并成一套是你的决定——
现在两边是两套并行实现，建议先各看一遍再定留哪个。

## 并发事故（重要，影响你怎么安排多个 Agent）

我按你的要求建了 `workflow/qoder-one-question` 分支并切过去。但**另一个会话在我们中间
把同一个工作目录切到了 `glm-workflow` 分支**，所以我那次 `git commit` 落到了它的分支上。

已经修正：我的提交 `74f4011` 现在在 `workflow/qoder-one-question` 上，HEAD 也在这条分支。
`glm-workflow` 上仍留有同一个提交（只是多一个指针，没有复制文件，也不影响它的历史）。
要清掉的话你自己决定，一条命令：`git branch -f glm-workflow 3392181`——我没动它，
因为那是别的会话的分支，我不该替它决定。

**根因**：同一个工作目录里切分支，会连带改变所有会话看到的文件树。
另一个会话用的是 `git worktree`（`workflow/glm-question-coach` 挂在
`D:/project/podcastGenerate-glm`），那才是对的并发方式。

**建议**：以后每个 Agent 一条独立 worktree，别共用主目录。约定可以是
`git worktree add ../podcastGenerate-<agent名> -b workflow/<agent名>-<用途>`。
命名按 agent 身份而不是模型名——Qoder 不对外暴露底层模型，我也不会去猜。

## 还没做的

- **你实听**。参数都对（−16.7 LUFS / 峰值 −1.8 dB / 7 个窗口时长精确），但"像不像真人、
  听着累不累"按你的质量约定只能你过听感门。StepFun 是逐行拼接，行与行的衔接自然度
  不如 Fish 的整段对话模式，重点听这一点。
- **第二个实验题**（验证跨题型泛化）。建议拿 Part 3 的 "Has technology made our lives easier?"
  再跑一次，那道题你有真实观点，能测出 lesson 结构在长答案上够不够用。
- **旧的 5 轨全套材料**（`kit/learning_kit_bruce/`）还是 Fish 生成的。要不要用 StepFun 重做，
  取决于你听完 01 轨后的判断——那是 134 次合成，别白烧。
- 把 `one-question` 注册成 Qoder 可自动发现的 skill（现在需要你在指令里点名）。
