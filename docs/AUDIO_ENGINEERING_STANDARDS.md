# 工业级 AI 播客声音工程标准 (Audio Engineering Standards)

> **版本**：v1.0  
> **适用范围**：本项目所有后续播客剧本生成、TTS 渲染及音频母带处理。所有生成任务必须严格遵照本规范执行。

---

## 核心设计哲学：如何打破“AI 念稿感”？

传统 AI 语音之所以听起来像机器在“背课文”，根本原因在于以下三点：
1. **伪对话（Monologue Hand-off）**：每个人一口气读 3~5 句话（20~30秒），缺乏真实人类交谈的微对话轮换。
2. **绝对数字死寂（Digital Silence）**：句子间的停顿是振幅为 0 的纯数学空白，引发耳蜗的生理性排异反应。
3. **单声道声像重叠（Mono Center）**：两个主播的声音从同一个声学点挤出来，缺乏物理录音室的空间纵深。

为此，本项目全面实施**工业级 4 层声学与剧本工程体系**：

```
Layer 1: 语音前置剧本工程 (Speech Acts & Micro-Turns)
   ↓
Layer 2: 韵律与副语言声学引导 (Paralinguistic Latent)
   ↓
Layer 3: 广播级物理母带流水线 (Studio Room Tone & Stereo Panning)
   ↓
Layer 4: 活力音色基准库 (College-Age Conversational Reference)
```

---

## 第一层：语音前置剧本规范 (Scriptwriting & Speech Acts)

1. **单次话轮熔断机制（Strict Micro-turn Limit）**：
   - **硬性上限**：任何一个说话人，单次发言严禁超过 **2 句话** 或 **25 个单词**。
   - 必须由另一位搭档以反应词、打断或接茬形式切入。
2. **高频反向接茬（Backchanneling & Interjections）**：
   - 频繁使用真实大学生的语气接茬词：
     - 赞同：*“Dude, 100%.”*, *“Right? Exactly.”*, *“Totally.”*
     - 震惊/质疑：*“Wait, what?”*, *“Wait, are you serious?”*, *“No way.”*
     - 思考过渡：*“I mean... honestly?”*, *“Here's the crazy part—”*
3. **思维假起步与自我修正（False Starts & Self-Correction）**：
   - 真人说话是边想边组织语言，绝不是事先写好的逻辑严密小作文。
   - 规范写法示例：
     - *❌ 错误（报告腔）*：`"When I was chatting with AI, I realized that I had no idea how to say whole grains."`
     - *✔ 正确（口语假起步）*：`"So I was talking to this AI, and I was like—wait, how do I actually say 'whole grains'? Total brain freeze."`

---

## 第二层：韵律与副语言标记规范 (Paralinguistic Tags)

1. **声学物理动作标记**：
   - `[sigh]`：自嘲、无奈、反思。
   - `[slight pause]`：思考时的自然呼吸顿挫（约 200~300ms）。
   - `[speaking slightly faster]`：情绪高涨、吐槽时的语速突变。
   - `[chuckle]`：⚠️ **高危标签，仅在 Fish Script 表演层谨慎使用**。Fish TTS 偶发
     5~6 秒失控长笑（已发生过真实事故）。系统 QA 门禁（`server/audioqa.py`）会检测
     时长比与 VAD 非语音孤岛，失控自动隔离并剥离全部标签重试一次。
     三份生成类 prompt 一律禁止源头产出该标签（幽默感用词句传达）。
2. **标点符号隐式驱动**：
   - 破折号 `—`：用于**截断急停（Abrupt Stop）**或**思维跳跃**。
   - 省略号 `...`：用于句尾拖音或寻找词汇时的犹豫。
   - 逗号 `,`：用于短促呼吸断句，防止长句被平铺念出。

---

## 第三层：广播级物理母带流水线 (Acoustic Mastering Chain)

所有由 TTS 生成的原始干音频（Dry Audio），必须通过 `server/mastering.py` 执行无损后处理：

1. **录音室微底噪注入（Studio Room Tone Injection）**：
   - 在人声音轨下方，全程混合一条经过高低切滤波（40Hz~8000Hz）的录音棚空气感微底噪（电平控制在 `-54dBFS ~ -56dBFS`）。
   - **作用**：彻底消除句子间隔处的绝对数字死寂，使整个音频拥有物理实体的温暖空间感。
2. **双人立体声场分离（Stereo Panning）**：
   - **Speaker A**：微偏移至 `左声道 15%`（`c0=0.85*c0+0.15*c1, c1=0.15*c0+0.85*c1`）；
   - **Speaker B**：微偏移至 `右声道 15%`；
   - **作用**：模拟两位主播坐在专业电台圆桌两侧面对面交流的真实 3D 声像。
3. **广播级人声 EQ 润色与动态压限**：
   - **高通滤波（High-pass 75Hz）**：彻底切除低频麦克风喷麦杂音与低频嗡鸣；
   - **温润胸腔增益（+2.0dB @ 220Hz, Q=1.2）**：赋予人声如 Shure SM7B 般的磁性与厚度；
   - **齿音柔化（-2.5dB @ 5.5kHz, Q=2.0）**：平滑过锐的 "s/sh/ch" 尖刺高频；
   - **动态平滑压限（Dynamic Normalization）**：平衡轻声笑语与大声吐槽之间的动态，确保通勤收听不刺耳、不漏词。

---

## 第四层：音色选型标准 (Voice Selection Criteria)

1. **男声（Voice A）**：
   - 必须为 **美式年轻大学生（General American College-Age / 20-25岁）**；
   - 音色特征：清亮、松弛、语调略带上扬（Upspeak）、带自然呼吸声与少年感，严禁低沉严肃的中年播音腔。
2. **女声（Voice B）**：
   - 必须具备中英双语无缝切换能力；
   - 音色特征：灵动、亲和、思维敏捷，适合教学点拨与幽默吐槽。
