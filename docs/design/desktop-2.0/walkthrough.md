# 英语说说说 2.0 桌面走查

2026-11-25，Windows 桌面网页。三步练习入口为 `#/train/<topic>/<item>`，闪电刷句入口为
`#/blitz`。已有条目仍可从精听播放器播放。在今日练习选择「历史训练与复验」可打开旧流程。

## 桌面操作

1. 在[今日练习](screenshots/01-home.png)选一道题，或查看到期句子和口语病历榜。病历榜只统计当前材料里能与原始回答核对的错误。陪练指令包含今天练过的语块和排名最高的两个类别。
2. 在题库打字、使用输入法语音，或点「直接开口盲答」。录音结束后由本机转写并提交，原声随条目保留。使用配置好的 API 时，生成完会打开[完整问答](screenshots/02-listen.png)。可以点词定位，也可以把原话和改法并排对照。
3. 按 `Space` 开始[看中文逐句开口](screenshots/03-recall.png)。3.5 秒反应条结束后可继续作答。再次按 `Space` [揭晓并播放本句](screenshots/04-reveal.png)。也可以按住 `R` 跟录、松手连续听示范和自己的录音。`1` 顺畅、`2` 卡壳，两种结果都更新 FSRS-4.5 日程。
4. [只看原题脱稿回答](screenshots/05-final.png)，最长 60 秒。可以直接完成，也可以录音后查看[口语前后对比](screenshots/06-results.png)。有原声时可分别回听盲答、脱稿和示范，或导出三合一 MP3。长停顿按大于 0.8 秒计数。中英混合、无录音或无有效时间轴时，对应不可比较的指标显示为缺失。
5. [闪电刷句](screenshots/07-blitz.png)使用 3 秒反应条。按 `Space` 听示范，按 `1` 或 `2` 评分并进入下一句。学习阶段和闪电刷句使用同一套复习卡，旧卡首次走新入口时保留历史日程并迁移调度状态。

## 设置与旧条目

[生成设置](screenshots/08-settings.png)的文本引擎预设为 DeepSeek。粘贴 Key 后点「测试连接」会保存并运行一次最小 JSON 请求。高级设置可选兼容接口。原方案的 `deepseek-chat` 已停用，当前预设用 `deepseek-flash`。未配置新 Key 时可使用旧 StepFun 文本配置或 Agent。 [DeepSeek 模型文档](https://api-docs.deepseek.com/quick_start/pricing/)

本机语音通过 `D:/project/ChineseAccent/.venv` 工作。网页可选择和试听考官与回答声音，已有个人声纹可选择「我的母语分身」。声纹与微调权重由 ChineseAccent 管理。没有声纹时分身选项使用 Liam。没有实测句子位置的旧条目会提示并播放完整问答，已有音频不需要重制就能继续收听。

Agent 可在同一份 JSON 里填 `natural_english`、`podcast_text`、`podcast_script` 和 `study_material`，再执行 `pipeline.py complete`。独立的 `pipeline.py study` 可以给旧音频补材料。[三文本与逐句契约](../../../skills/ielts-audio/SKILL.md)

## Windows 实测

使用 RTX 5060 Laptop GPU，输入为合成测试问答。女声 `af_bella` 提问，两句回答经 Seed-VC V2 转成已有个人分身。ChineseAccent 当时报告声纹已存在，未检测到个人微调权重。测试 MP3 为 5.480 秒，18 个词有实测时间戳。两句回答的定位为 1.420–3.520 秒和 3.640–5.480 秒。约 20ms 指对齐模型的帧粒度，尚未用人工标注的词边界测量绝对误差。

状态读取后首次分身问答用时 36.74 秒，热跑 10.00 秒。相同问答热跑纯 Kokoro、对齐与母带用时 2.66 秒。仅合成一次提问和一句回答，默认 ONNX CPU 设置的热跑中位数为 0.919 秒。对比测试的 1、2、4、8 线程设置更慢。独立并行实验的中位数为 0.754 秒，最快一次 0.635 秒。当前尚未达到 0.5 秒。FFmpeg 检测到平均音量 −16.2 dB 和峰值 −1.8 dB。

英文录音实测转写热跑 0.91 秒，识别到 `helps me unwind`，CTC 命中 `like swimming`。多语言 Faster-Whisper 权重已缓存。中英合成录音实测保留了两种语言，中文有识别误字。结果命中 `twice a week`，同时留空不可比的英语语速。实际分身 MP3 的 Playwright 回归验证了点击词后高亮、按实测起止播放单句、示范与跟录在同一时间点衔接。

截图使用合成题目、模拟录音指标和私有配置占位状态。实际分身样本留在本机 `tmp/arcade-2.0/local-voice.mp3`。Bruce 试听反馈为「还可以吧，有一点像」。

## 质量门禁

- `.venv/Scripts/python -m pytest tests/ -q --ignore=tests/e2e` 在全量门禁中得到 282 项通过、1 项跳过。
- `bash scripts/check.sh --with-e2e` 全绿，包含 Ruff、导入与启动冒烟、73 项浏览器回归。
