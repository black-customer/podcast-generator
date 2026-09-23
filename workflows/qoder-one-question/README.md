# one-question：一道题 + 你的回答 → 一份你学得完的教学包

给一个雅思口语题，给你自己录的原始回答（转写文本即可，越烂越好），
这个工作流产出一份**剂量封顶**的训练包：一条 6 分钟音频、3 张卡、一个页面，一轮 12 分钟。

它存在的唯一理由是**剂量**。一次性给你 40 分钟音频和 35 张卡，你不会去学，只会关掉。
所以这里的所有上限是硬编码的，超了直接构建失败，而且不许改校验器放行。

## 30 秒上手

```bash
# 1. 量化你的回答（纯规则，不联网，不花钱）
cd workflows/qoder-one-question/scripts
python -m one_question.diagnose --question "Do you have a favourite teacher?" \
       --answer "Actually I don't have kind of favorite teacher..."

# 2. 让 Agent 按 diagnose 的输出写 lessons/<id>/lesson.json
#    （这一步是教学判断，必须由语言模型做；见 skills/one-question/SKILL.md）

# 3. 构建
python -m one_question.build ../lessons/<id>/lesson.json
open ../lessons/<id>/page.html
```

第 2 步可以直接对你的 Agent 说：**「用 one-question 工作流，题目是 X，我的回答是 Y」**，
它会读 `skills/one-question/SKILL.md` 自己跑完。

## 剂量上限

| 维度 | 上限 |
|------|------|
| 纠错点 | 3 |
| 语块 | 3 |
| 示范答案 | 4–6 句 / 60–85 词 |
| 音频 | ≤ 6:30，≤ 7 个强制输出窗口 |
| 卡片 | 3 张 |
| 一轮 | ≤ 12 分钟 |

`scripts/test_one_question.py` 里 9 个测试专门验证这些上限**真的会拒绝**超限的 lesson，
包括"把用户错误原话偷偷改漂亮"这种情况——那是这套方法的燃料，不是脏数据。

## 训练机制为什么长这样

- **注意到差异**：音频先念你的原话错误，紧挨着念正确版。不解释，先让你听见差别。
- **检索练习**：每个示范后是一个强制输出窗口（提示音 → 静音 → 提示音），窗口里必须张嘴。
  听懂和会说在大脑里走的是两条不同的通路，静音听完十遍一句也不会说。
- **中文→英语，不是跟我读**：窗口给的是中文提示，逼你自己组装句子，而不是回声。
- **自我参照**：示范答案只用你自己说过的经历和观点，不编例子。
- **压速收尾**：最后用考试节奏抽问一次。先给答案再抽考，顺序反过来就变成听力练习。

## 目录

```
skills/one-question/SKILL.md          Stage 1 规范（Agent 读这个）
skills/one-question-creator/SKILL.md  Stage 2 自媒体包装规范（可选，见下）
scripts/one_question/diagnose.py      确定性诊断，零依赖零联网
scripts/one_question/build.py         lesson.json → 音频 + 3 卡 + 页面（含剂量校验）
scripts/one_question/engine.py        TTS 缓存、时间轴、母带、HTML→PNG
scripts/one_question/creator.py       Stage 2：封面 + 逐镜清单 + 发布文案 + 短片
scripts/one_question/minimax.py       本地 Minimax 图生视频适配器（可选，失败自动跳过）
scripts/test_one_question.py          剂量上限的测试
lessons/<id>/                         每题一个目录：lesson.json 是唯一的源
kit/                                  个人全套材料（私人语料，不进 git，不对外）
```

## 开源分发

拷走整个 `workflows/qoder-one-question/` 目录即可，只依赖：

- Python 3.11 + `playwright`（Chromium）+ `ffmpeg` 在 PATH
- 宿主项目的 `server/stepfun.py`、`server/tts.py`、`server/audio.py`、`server/config.py`
- TTS 后端由 `data/settings.json` 的 `tts_provider` 选择：`stepfun`（默认，`stepaudio-2.5-tts`，境内直连）
  或 `fish`（多说话人一次成型，但境内需要代理）。换第三家只需替换 `engine.Synth.__call__` 与 `_stepfun_dialogue`
- **StepFun 限速按「开放平台累计充值」定档，与消费端 App 会员无关**（实测确认）：
  V0（充值 ¥0）= **10 RPM / 5 并发**；V1（充值 ¥100）= **1000 RPM / 100 并发**。
  引擎按 `settings.stepfun_rpm`（默认 9）主动压速，不靠上游 429 重试硬撞；
  升到 V1 后把这个值改成 300 就提速，不用改代码。
  StepFun 一次只能一个音色，所以引擎逐行合成再拼接，行间距用 `stepfun_gap_ms`

**不要带上 `kit/`**——那是锚定本人真实录音的私人材料。
`one-question-creator` 是自媒体附加层，别人只要备考，可以整层删掉，Stage 1 不受影响。

## Stage 2（可选）：把教学包变成别人愿意看完的作品

```bash
python -m one_question.creator ../lessons/<id>/lesson.json          # 封面 + 文案 + 短片
python -m one_question.creator ../lessons/<id>/lesson.json --no-video   # 不碰 TTS，只出封面文案
```

核心约束：一条视频**只讲一个**啊哈点。Stage 1 的三个纠错点，发布时砍到只剩一个，
由 `lesson.json` 的 `publish.aha_fix_id` 指定——这是编辑判断，不是算法判断。

## 已知边界

- 音频合成需要网络（TTS 上游）。网络不通时**卡片、页面、封面、文案照常产出**，
  并写 `PENDING.json` 记下重跑命令；不会整条流程崩掉。
- 诊断器是规则包，覆盖的是高频中式错误。它没命中不代表你说对了——
  教学判断仍由 Agent 在写 lesson.json 时补足。
- 发音与流利度问题无法从文字转写稿可靠推断（转写本身会吃掉口音）。
  要针对发音训练，需要真实录音。
