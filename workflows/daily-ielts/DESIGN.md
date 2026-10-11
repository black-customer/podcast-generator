---
name: "每日雅思口语材料"
description: "独立备忘录长图、问答录音和手写语块笔记的已实现视觉系统"
colors:
  paper: "#FDFBF7"
  ink: "#25221E"
  annotation: "#863B38"
  underline: "#F0D1D2"
  season: "#66615A"
  translation: "#5B554D"
  footer: "#6C665F"
  header-rule: "#DAD4CB"
  note-rule: "#E6E0D8"
typography:
  topic:
    fontFamily: "Georgia, serif"
    fontSize: "70px"
    fontWeight: 700
    lineHeight: 1.35
  season:
    fontFamily: "Georgia, Microsoft YaHei, serif"
    fontSize: "46px"
    fontWeight: 400
    lineHeight: 1.4
  question-en:
    fontFamily: "Georgia, serif"
    fontSize: "56px"
    fontWeight: 700
    lineHeight: 1.4
  question-zh:
    fontFamily: "Microsoft YaHei, sans-serif"
    fontSize: "51px"
    fontWeight: 400
    lineHeight: 1.6
  chinese-answer:
    fontFamily: "Microsoft YaHei, sans-serif"
    fontSize: "76px"
    fontWeight: 400
    lineHeight: 1.5
  bilingual-en:
    fontFamily: "Georgia, serif"
    fontSize: "54px"
    fontWeight: 400
    lineHeight: 1.38
  bilingual-zh:
    fontFamily: "Microsoft YaHei, sans-serif"
    fontSize: "51px"
    fontWeight: 400
    lineHeight: 1.58
  phrase:
    fontFamily: "Georgia, serif"
    fontSize: "60px"
    fontWeight: 700
    lineHeight: 1.4
  meaning:
    fontFamily: "KaiTi, Microsoft YaHei, serif"
    fontSize: "70px"
    fontWeight: 400
    lineHeight: 1.45
  usage:
    fontFamily: "Microsoft YaHei, sans-serif"
    fontSize: "45px"
    fontWeight: 400
    lineHeight: 1.6
  example-en:
    fontFamily: "Georgia, serif"
    fontSize: "51px"
    fontWeight: 400
    lineHeight: 1.5
  example-zh:
    fontFamily: "Microsoft YaHei, sans-serif"
    fontSize: "48px"
    fontWeight: 400
    lineHeight: 1.55
  cue-en:
    fontFamily: "Georgia, serif"
    fontSize: "54px"
    fontWeight: 400
    lineHeight: 1.5
  cue-zh:
    fontFamily: "Microsoft YaHei, sans-serif"
    fontSize: "65px"
    fontWeight: 400
    lineHeight: 1.6
  footer:
    fontFamily: "Microsoft YaHei, sans-serif"
    fontSize: "29px"
    fontWeight: 400
    lineHeight: 1.6
spacing:
  sentence-gap: "18px"
  meaning-gap: "24px"
  pair-gap: "30px"
  note-gap: "38px"
  section-gap: "44px"
components:
  memo-sheet:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    padding: "100px 94px 76px"
    width: "1260px"
    height: "2800px"
  memo-header:
    textColor: "{colors.ink}"
    padding: "0 0 44px"
  question-block:
    textColor: "{colors.ink}"
  chinese-line:
    textColor: "{colors.ink}"
    typography: "{typography.chinese-answer}"
  bilingual-pair:
    textColor: "{colors.ink}"
    padding: "0 0 18px"
  phrase-note:
    textColor: "{colors.ink}"
    padding: "0 0 32px"
  recording-caption:
    textColor: "{colors.ink}"
  preview-download:
    textColor: "{colors.annotation}"
---

# Design System: 每日雅思口语材料

## Overview

**Creative North Star: "普通备忘录，漂亮手写笔记"**

本系统只约束 `workflows/daily-ielts/` 的导出材料与本地预览。读者通过题目、回答、
逐句翻译和语块笔记理解并复用表达；纸面和文字承担视觉层级。本地预览安静地展示
独立文件，录音使用浏览器原生控件。这里不继承桌面学习页或手机主题的界面配色。

视觉以 Bruce 的备忘录和笔记截图为参考；当前落地是平整米白纸面、英文衬线文字、
清楚的中文和楷体释义。楷体是字体渲染，不宣称每个字由人手写。本文从 `build.py`
的 `STYLE`、`material_html()` 和 `preview_html()` 提取已实现的值，不加入未来设想。

**Key Characteristics:**

- 三张固定比例长图与一个独立问答录音视频。
- 中文回答逐行铺开，英文与中文逐句相邻。
- 棕红楷体释义与淡粉语块划线，装饰让位于内容。
- 平面纸张、细分隔线、原生视频控件。

## Colors

配色来自真实 CSS；上方 frontmatter 是数值真源。

### Primary

- **棕红批注**（`annotation`）：语块中文释义、视频说话人、本地下载链接及键盘焦点。

### Secondary

- **淡粉划线**（`underline`）：重点英文语块下方的局部标记与本地预览的文本选择背景。
  语块背景从字高的 70% 开始着色，文字颜色继承正文。

### Neutral

- **米白纸面**（`paper`）：图片、视频字幕画面与预览背景。
- **深墨正文**（`ink`）：主要中英文内容。
- **月份灰**（`season`）：题库月份与 Part。
- **翻译灰**（`translation`）：逐句中文和例句中文。
- **页脚灰**（`footer`）：回答来源与本地题库标签。
- **页眉细线**（`header-rule`）与**笔记细线**（`note-rule`）：划分文字区域。

**The Paper Rule.** 导出材料使用同一米白纸面和深墨正文，棕红与淡粉只服务文字批注。

## Typography

英文题目、话题、回答和例句使用 Georgia；中文正文使用 Microsoft YaHei；
中文释义与“重点语块”标题使用 KaiTi，并保留已实现的字体回退。字体全部来自本机，
不依赖 CDN。上方 typography 记录常用角色；以下补充实际变体。

- 话题中文为中等字重（500），字号 56px、行高 1.4，与英文话题间隔 30px。
- 考官／考生标签为粗体（700），图片字号 43px，下方间距 20px。
- 中英对照图片的题目收为英文 49px、中文 46px；句对正文保持 frontmatter 的角色值。
- “重点语块”标题为楷体 60px、行高 1.4；释义继承 `annotation`。
- 视频月份为 34px，英文话题 53px、中文话题 45px；中文话题左间距 24px。
  说话人标签为 38px 粗体，页脚为 25px、行高 1.6。
- 本地预览标题为 28px／600，区域标题为 20px，辅助段落为 15px／1.7。

**The Sentence Pair Rule.** 每句英文后紧跟对应中文，句内距离小于句组之间的距离。

## Layout

发布物恰好为 `01-chinese.png`、`02-dialogue.mp4`、`03-bilingual.png`、
`04-notes.png`。三图画布固定为 1260×2800（9:20），纸面内边距为
100px 94px 76px；视频为 1080×1920（9:16），内边距为 92px 78px 74px。
尺寸服务导出画布，不是应用页面的响应式断点。

共用页眉先显示月份／Part，再显示中英话题，下方保留 44px 与 2px 细线。
图片题目区域外距为 42px 0 34px；页脚上距为 44px。主区使用纵向 flex，
保留 `min-height:0`；导出器在截图前拒绝横向溢出及正文侵入页脚。

中文回答按内容规划分行，每行不自动换行；行与行用剩余竖向空间均匀铺开。
中英对照的每个句对内部英文下距 18px、句组底部留 18px，主区最小组距 30px。
笔记主区最小组距 38px，每组底部留 32px；最后一组去掉底线和底部留白。
视频中央纵向排列当前说话人、英文和对应中文，英文下距 42px，页脚上距 24px。

本地预览最大内容宽度 740px，页面外距 40px auto、横向内边距 20px；
区域外距 54px 0 68px。图片与视频按容器宽度缩放并保留比例；
视频限制显示高度 760px，使用 `object-fit:contain`。没有自定义媒体查询断点。

## Elevation & Depth

图片、字幕画面和预览均为平面。纸面没有阴影、纸纹、渐变背景或浮起的卡片。
两种细分隔线建立区域边界；语块的淡粉下划线是局部文字标记，不承担容器层次。
CSS 没有界面动效；字幕变化来自实测语音时间轴对应的静态画面切换。

## Shapes

纸面与文字区域保持矩形，不添加圆角卡片、胶囊或贴纸。分隔线为 2px。
本地视频的播放、暂停、音量等形状由浏览器原生控件提供，不将它们仿制到导出画面。

## Components

- **共用页眉与页脚**：月份、Part、中英话题与细线；页脚明确回答来源和本地题库标签。
  月份只代表题库收录范围，不能转写成“最新官方真题”。
- **中文回答纸面**：英文题目和题目中文后，考生回答只显示中文。分行保留完整原意，
  用竖向空间铺开；不加入英文答案或练习指令。
- **逐句中英对照**：英文一句、中文一句组成单个区域，所有句子按录音顺序出现。
- **语块笔记**：当前作品为三个表达，每组包含淡粉划线的英文、棕红楷体中文意思、
  用法、英文例句及对应中文。日常生成契约允许 1–3 个表达，不为填版增加材料。
- **录音字幕画面**：单次考官提问和单次完整考生回答；当前说话人、英文及中文同时出现。
  字幕使用真实句跨度或词时间戳，不按字数估算；不加入练习停顿或重复答案。
- **本地预览**：四个下载链接和四个内容区；仅视频使用原生 `controls`、`playsinline`
  与 `preload="metadata"`。链接保留原生下划线、4px 下划线偏移和 2px 棕红键盘焦点。

实现核对样本为 `output/2026-10-11-v2/` 的 Music 材料，题目 ID 为
`q_1atqseprhxsi`，标注本地 2026年5–8月题库。视觉与导出范围的 finish review 已通过；
这不代表真人听感、语音自然度或 Bruce 的审美认可通过，不标记 C01 DONE。

## Do's and Don'ts

### Do:

- **Do** 保留三张 9:20 长图与一个独立 9:16 问答录音视频的文件契约。
- **Do** 按真实录音逐句对应中英文，中文回答分行保持原意和完整内容。
- **Do** 让纸面、字号、行距、释义和局部划线承担阅读层级。
- **Do** 在本地预览使用原生视频控件，并明确本地题库月份与回答来源。

### Don't:

- **Don't** 把本目录套成蓝绿应用卡片或四步合成练习视频。
- **Don't** 加入进度圆点、波形、装饰横幅、自定义按钮或迁移挑战。
- **Don't** 把整篇英文和整篇中文分开排，或在中文回答区泄露英文答案。
- **Don't** 用技术 QA 代替听感和审美验收，或把本地月份标签写成已核验官方新题。
