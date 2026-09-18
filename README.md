# 播客生成器（Bruce English Corpus 工具）

基于 **Agent 编剧 + 工业级声学母带流水线 + Spotify 风格私有视听媒体库** 的高保真英语播客系统。

> 详见项目声学宪章：[docs/AUDIO_ENGINEERING_STANDARDS.md](docs/AUDIO_ENGINEERING_STANDARDS.md)

### 工业级 4 层声音工程体系
1. **剧本层**：微话轮交替（Micro-turn Taking，单人连续发言严禁超 2 句/25 词）、高频真实接茬（*“Dude, 100%”*, *“Wait what?”*）、思维假起步（False Starts）；
2. **韵律层**：副语言动作注入（`[chuckle]`, `[sigh]`, `[slight pause]`）与标点截断；
3. **物理母带层（Mastering Chain）**：录音室微底噪注入（-54dBFS，彻底消灭数字绝对死寂）、双人立体声场微分离（L15%/R15%）、广播级温暖 EQ 与动态压限；
4. **音色层**：美式年轻大学生活力音色 + 灵动双语女主播。

## 快速开始

双击 `start.bat`（首次运行会自动创建 venv 并安装依赖），浏览器会自动打开
`http://127.0.0.1:8765`。

手动方式：

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run.py
```

依赖：Python 3.10+、ffmpeg（需在 PATH 中）。

## 配置

可直接在前端 **设置** 界面配置，或复制配置模板后修改：
```bash
cp data/settings.example.json data/settings.json
```

1. 填入 [fish.audio](https://fish.audio) 的 **API Key**；
2. 在 fish.audio 挑选/设计一个音色（年轻、清晰、conversational 的 General American 男声/女声），
   复制其 **Reference ID** 填入——声音身份由它决定，选定后建议几个月内不要更换；
3. 模型默认 `s2.1-pro-free`（官方免费档，以官网政策为准）；
4. 点击 **测试连接** 验证 ffmpeg 与 API。

> 没有填 key 时系统自动处于 **dry-run 模式**：照常走完全流程，但生成的是占位音频，方便先熟悉工具。

### 双人对话播客

设置里再填一个**音色 B**（Reference ID B）后，条目文本只要是 `A:` / `B:` 开头逐行交替的对话，
就会自动生成双人对话音频。默认走 **单次多说话人生成**（`<|speaker:0|>` / `<|speaker:1|>` 标记 +
声音数组，整段对话一次合成）——模型能看到完整上下文，接话节奏、反应、停顿由模型自己演绎，
真人感远高于逐句拼接；接口异常时自动回退为逐行分音色合成。

```
A: Hey, I'm trying to adjust my sleep schedule.
B: Nice! That's a big change.
```

不填音色 B 或文本不是对话格式时，一律按单音色朗读。想提升语气生动度，可把设置里的
**temperature** 调到 0.6–0.8（默认跟随服务端）。

## 日常工作流

界面分两半：**🛠️ 工作台管理** 负责内容生产，**媒体库 / 专辑 / 曲目** 页负责播放学习。

对每个问题（例如 `Do you work or are you a student?`）：

1. **建条目录入**：进入「🛠️ 工作台管理」→ 选择话题 →「新建条目」（或「批量创建」一次粘贴一批题目）；
   把问题和你不受时长限制的中文自由回答粘进去（像跟朋友聊天一样说透）。
   也可以直接在条目编辑器里填双轨文本：独白轨（Monologue Text）与播客轨（Podcast Text，
   `A:` / `B:` 逐行交替的双人对话）。
2. **生成 Natural English**：条目编辑器点 **📋 复制改写请求**，把内容粘给 AI（ZCode / 任意对话模型），
   会得到保留你人格与啰嗦程度的地道口语英文；把结果粘回 Natural English 栏并保存。
3. **（可选）生成 Fish Script**：点 **🎚 复制配音请求**，AI 会按 voice director 提示词
   在文本里加少量 `[slight pause]` 等标签；结果粘回 Fish Script 栏。留空则直接合成 Natural English。
4. **生成音频**：工作台里选轨道（播客 / 独白 / 全部），单条点 **⚡ 生成**，整批点 **⚡ 批量生成音频**；
   下方进度条实时显示完成度，失败的单条会列出原因，修好后可单独重试。
5. **合成本集**：点 **🎬 合成播客整集 / 独白整集**，把该话题所有条目按顺序连成一集
   （条目间自动加停顿），在专辑页可直接下载。
6. **听 & 学**：媒体库选专辑 → 点曲目进入播放器。双轨随时切换（播客版 / 独白版），
   Live Transcript 卡拉OK式逐句高亮跟随，点任意句子跳播；支持 0.8x–1.5x 倍速、±15 秒跳转。

批量/自动化场景可不走 UI：直接编辑 `data/` 下的纯文本文件（人和 agent 都能写），
或使用 `pipeline.py` 命令行一次性存入并生成：

```bash
python pipeline.py --topic "02-travel" --question "Do you like traveling?" \
  --chinese-file zh.txt --podcast-file dialog.txt --track all
```

两套 AI 提示词保存在 `prompts/`：
`promptA_zh_to_natural_english.md`（人格保持型改写）、`promptB_voice_direct.md`（voice director）。

## 数据结构

一切都在 `data/` 下，纯文本文件，可直接编辑（也可以让 agent 直接批量写入）：

```
data/
  settings.json                 # API key、音色、语速等
  topics/01-my-studies/         # 话题 = 一集
    topic.json
    items/001-do-you-work-or-are-you-a-student/
      question.txt              # 问题
      chinese.txt               # 中文自由回答
      natural_english.txt       # 地道口语英文
      fish_script.txt           # 配音稿（可选）
      monologue_text.txt        # 独白轨原文（可选）
      monologue_script.txt      # 独白轨配音稿（可选）
      podcast_text.txt          # 播客轨 A:/B: 对话原文（可选）
      podcast_script.txt        # 播客轨配音稿（可选）
      meta.json                 # 状态/时长/时间戳
      audio.mp3                 # 条目音频（独白/播客轨另有 audio_monologue.mp3 / audio_podcast.mp3）
  episodes/01-my-studies.mp3    # 合成的整集（双轨为 *_monologue.mp3 / *_podcast.mp3）
```

## 开发与测试

```bash
.venv/Scripts/pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest tests/test_core.py -q    # 隔离测试，不碰 data/ 真实数据
.venv/Scripts/python -m pytest tests/test_api_endpoints.py -q  # 冒烟测试，依赖已生成的真实数据
```

后端 API 文档在运行时访问 `http://127.0.0.1:8765/api/docs`。开发时加 `--reload` 开启热重载：
`python run.py --reload`。

## 推荐学习方法（听 → 提取 → 自动化）

1. **第一阶段 只听**：认真听（不是当背景音），把「这个意思原来英文这样说」绑定起来；
2. **第二阶段 口译法**：学习模式里看中文自己说，2–4 秒内说不出就直接看答案；
3. **第三阶段 shadowing**：跟读模仿 chunk、重音、语调，不只模仿单词；
4. **第四阶段 脱稿重答**：只看问题重新回答，观察哪些表达已经能自动出来；
5. **隔 1 / 3 / 7 天重复**。

## 注意事项

- Fish 免费政策有 Fair Use 限制并可能变化，以 [官方说明](https://fish.audio) 为准；
- 长回答会按句子边界自动分段（默认 700 字符/段）依次合成再拼接，段间默认 350ms 停顿；
- 生成是后台任务，失败的单条会记录错误并可单独重试，不会阻断整批。
