---
name: 英语说说说
description: 安静清晰、完成度一致的口语练习工作区
colors:
  primary: "#4359c7"
  primary-soft: "#edf0fc"
  on-primary: "#ffffff"
  background: "#f4f5f8"
  surface: "#ffffff"
  surface-soft: "#eceff5"
  ink: "#202638"
  ink-soft: "#626c80"
  rule: "#dce1eb"
  dark-primary: "#b4c2ff"
  dark-primary-soft: "#303d62"
  dark-on-primary: "#1d284b"
  dark-background: "#151923"
  dark-surface: "#202634"
  dark-surface-soft: "#2a3243"
  dark-ink: "#f0f2fa"
  dark-ink-soft: "#b8c1d5"
  dark-rule: "#414c63"
  recording-stop: "#b3343d"
typography:
  display:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif'
    fontSize: "2.25rem"
    fontWeight: 650
    lineHeight: 1.45
    letterSpacing: "-.035em"
  headline:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif'
    fontSize: "1.75rem"
    fontWeight: 650
    lineHeight: 1.4
    letterSpacing: "-.035em"
  transcript:
    fontSize: "1.25rem"
    lineHeight: 1.75
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif'
    fontSize: "1rem"
    lineHeight: 1.65
  label:
    fontSize: ".875rem"
    fontWeight: 500
    lineHeight: 1.5
rounded:
  tag: "5px"
  compact: "8px"
  control: "10px"
  panel: "12px"
  player: "14px"
  workspace: "16px"
spacing:
  small: "8px"
  control: "12px"
  medium: "16px"
  inset: "20px"
  section: "24px"
  panel: "28px"
  roomy: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.control}"
    padding: "9px 16px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "9px 16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.control}"
    padding: "12px"
  navigation-active:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.primary}"
    rounded: "{rounded.compact}"
    padding: "11px 14px"
  chip:
    backgroundColor: "{colors.surface-soft}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.tag}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "28px"
---

# Design System: 英语说说说

## Overview

**Creative North Star: "口语练习工作区"**

雾灰底、白色工作面、深墨文字和靛蓝动作构成安静清晰的现代学习工具。
导航紧凑，内容有阅读留白；字重、尺度和连续分区建立层级，辅助操作退后。
所有用户可见页面共享这套语言，手机深色主题通过语义令牌保持相同主次。

2026-10-16 Bruce在否定v3首次打开首页后授权整体升级。当前方向契约为
`docs/design/experience-v4/README.md`，实际令牌取自最后加载的`web/product-ui.css`。
v3属于历史交接；更早暖纸与手机方案保存在`docs/design/experience-v3/PREVIOUS_DESIGN.md`。
本次独立截图审查在五项修正后给出ship；这不是Bruce的视觉验收。
原图标和中文系统名称“英语说说说”保持，应用内使用功能标题。

**Key Characteristics:**

- 中性工作面与单一靛蓝动作色。
- 连续列表、分组表单和明确的当前任务。
- 系统无衬线字体与可选择的中英文正文。
- 同一学习步骤的输入、播放与视图连续性。

## Colors

浅色主题以雾灰和白色承载正文，手机暗色以炭蓝工作面和浅靛蓝动作保持层级。

### Primary

`primary`用于当前主动作、选中状态和可交互强调；`primary-soft`用于参考、选中行与逐词高亮。
`on-primary`定义主按钮文字。暗色对应`dark-primary`、`dark-primary-soft`与`dark-on-primary`。
录音停止使用`recording-stop`，只表达正在录制时的停止动作。

### Neutral

`background`是页面和桌面导航底色；`surface`是正文、控件与工作面；`surface-soft`用于辅助区域。
`ink`用于正文，`ink-soft`用于说明和元信息，`rule`用于列表、表单和区域分隔。
全部手机暗色值在前置令牌的`dark-`项中对应，不能保留旧主题硬编码颜色。

**The Semantic Theme Rule.** 明暗主题切换只改变语义颜色，不重启训练、音频或草稿。

## Typography

**Display Font:** 系统无衬线，与正文共用前置令牌中的字体栈。
**Body Font:** 同一系统栈，中文回退到Microsoft YaHei；无CDN字体依赖。

**Character:** 界面通过字号、字重、行距与分区表达层级；学习内容保持清楚和可复制。

### Hierarchy

- **Display:** 首页空状态行动标题；手机缩至（1.875rem）。
- **Headline:** 页头；播放器问题保持同级字号，行高（1.45）。
- **Title:** 题目列表使用（1.0625rem / 550）；表单与学习工作面标题较紧凑。
- **Body:** 基础正文使用body；播放器英文使用transcript；页头说明最大（65ch）。
- **Label:** 操作标签使用label，辅助说明常用（.8125rem）；时间和序号使用等宽数字。

## Layout

桌面导航宽（224px）。超过（900px）时主应用区域内边距为（40px 48px），训练区域另用紧凑
水平边距。首页最大宽（1120px）；行动区与训练路线按（1.65fr / 1fr）组成整体，第二列最小
（260px）。中等宽度（701–1100px）调整为（1.3fr / 1fr），辅助列最小（240px）。
这套首页构图属于v4首页，不强制套用到其它页面。

题库使用紧凑筛选和连续题目列表，题目、元信息与动作分层。材料列表复用连续行。
播放器将正文与参考分区；桌面固定播放器为两行（136px），主内容和侧栏预留对应底部空间。
设置按真实表单职责分组；声音区内部用分隔线组织，避免多层卡片叠套。

手机在（700px）及以下将首页与参考区纵向排列，主要留白为（20–24px）。搜索独占一行，
题目动作移到下方；播放时间不换行。页面处理顶部安全区，正式训练随可视高度适应软键盘。
正式训练隐藏浏览导航，保留返回、题目和五阶段定位；按当前操作展开录音、参考、默写与自评。

## Elevation & Depth

工作面通常通过底色与细边框分区；卡片无投影。仅选中导航、固定播放器与对话框使用有限深度。

### Shadow Vocabulary

- **Selected navigation** (`0 2px 8px #20263808`)：桌面当前入口。
- **Fixed player** (`0 -4px 18px #15203508`)：底部持续播放区。
- **Dialog** (`0 12px 48px #10182830`)：模态容器，遮罩为（#10182866）。

## Shapes

小标签、控件、工作面依次使用前置rounded令牌；页内工作面比控件更舒展。
题库选项用底线标识当前项，列表内部保持直线分隔。手机主题开关和路线序号使用圆形。

## Components

### Buttons

清楚克制，当前任务拥有实色主按钮。通用按钮至少（44px），手机训练按钮至少（48px）。
主按钮悬停保持动作色并降低亮度至（.92），按下位移（1px）；次按钮悬停转柔和底色。
背景和边框过渡为（160ms ease-out），减少动态效果设置关闭过渡、动画与平滑滚动。
禁用透明度（.48），处理中呈现忙碌指针。键盘焦点为动作色（2px）外轮廓，偏移（3px）。

### Chips

标签使用柔和工作面、次级文字和小圆角；音频状态强调可用淡动作色。
题库Part切换采用底线选项，不能把所有元信息都提升成主按钮。

### Cards / Containers

工作面使用surface与rule；设置卡片、题目回答区和学习区复用panel圆角。
首页行动与路线合为更大圆角容器，播放器使用独立player圆角。
空状态说明真实情况并给出实际入口，不用虚构统计填空。

### Inputs / Fields

输入使用白色或暗色surface、细边框和可见光标；聚焦时边框转动作色。
文本可选择，文本域可纵向调整；训练文本域最小高度（132px）。
同一步更新保留DOM身份、焦点、选区、展开和滚动，新句或新阶段才重置内容起点。

### Navigation

浏览导航使用次级文字，桌面选中项为白色面、靛蓝字与轻投影；手机选中项为淡动作色。
正式训练隐藏浏览入口。返回题库保持已有筛选和滚动；键盘操作保留可见焦点，非交互标题不画控件框。

### Training and playback

中文口答提示是当前重心，参考、音频、默写与替代表达按需展开；评价与继续保持主要层级。
停止录音后在原位保存与回听；失败保留本机副本并支持重试，录音中离开先停止并保存。
播放按钮使用实色动作，进入学习是次操作；正文高亮复用淡动作色。
学习与数据行为仍以雅思单题v2契约为准，视觉升级不改变API、材料指纹、幂等或复验判定。

## Do's and Don'ts

### Do:

- **Do** 让当前真实任务、正文和主动作先被看到。
- **Do** 用共享语义令牌维护手机明暗主题。
- **Do** 保持输入、音频、草稿与同一步视图连续性。
- **Do** 保留原图标、中文名称、键盘焦点与正文选择复制。

### Don't:

- **Don't** 用虚构统计、成就或自动评分填充空状态。
- **Don't** 把v3首页、暖纸或旧手机色值当作当前视觉权威。
- **Don't** 把全部学习状态同时铺成表单或让辅助操作争抢主任务。
- **Don't** 将独立截图审查的ship表述为Bruce已验收。
