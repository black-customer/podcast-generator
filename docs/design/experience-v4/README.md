# 整体视觉升级 · 2026-10-16

Bruce以首次打开的首页截图否定v3的视觉完成度，并明确要求升级所有用户可见页面。
范围：首页、导航、题库、材料、训练、播放器、设置及手机明暗主题；原功能与数据规则保持。

## Direction contract

THESIS：让产品呈现为完成度一致的口语练习工作区。空状态也须有明确构图和实际入口，
不用孤立的白框、大片无组织留白或虚构统计来填充页面。

OWN-WORLD：雾灰背景、白色内容面、深墨文字、靛蓝动作。统一无衬线字体，靠字重、尺度与
分区建立秩序；导航较紧凑，正文有阅读留白。辅助操作不与当前主任务竞争。

STORY：用户一眼知道从哪里开始；选题、准备、练习、回听都有稳定的页头、工作面与操作区。
首页说明真实学习流程，已有记录优先显示继续任务；不引入学习新功能或虚假成就。

FIRST VIEWPORT：首页宽幅双栏，左侧用较大的行动标题和主按钮建立重心，右侧用三个真实步骤
解释训练。下方是练习安排及已有内容入口；手机按任务优先顺序垂直排列。
题库紧凑筛选与连续题目列表；播放器正文与参考双栏；设置以清楚的表单区块组织。

FORM：在现行中性视觉系统中进行整体构图升级，用户已明确授权自主完成；code-led，
不另行进行概念抽签。视觉签名是首页的行动区与有序训练路线，而不是装饰插图。

FINISH：unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## 研究依据

[NN/g 空状态设计](https://www.nngroup.com/articles/empty-state-interface-design/)：解释当前状态、
帮助理解产品、提供直接行动。参考[Linear 默认视图](https://linear.app/docs/default-team-pages)
的工作区分工；具体构图是本项目的设计判断，不是研究已证明的最优方案。

全部截图使用隔离的合成内容；不公开私人回答、录音或密钥。工程验证与Bruce主观认可分开。

## 本轮实现与验收边界

- 网页版为主：桌面首页、左侧导航、题库、语料、材料理解、逐句练习、整题录音、完成页、播放器、设置的共享视觉已升级；Android复用相同前端。
- 首页空状态具备行动重心、三步训练路线和实际材料入口；有任务时优先继续训练或到期复验，不填充虚假统计。
- 逐句中文下方直接评价，帮助单独成区；重点选择实时计数、底部继续操作保持可达，零选择仍可直接进入整题。
- 题库连续列表和下划线分类；播放器改为两行控件，播放与进度优先；设置移除无意义外层嵌套。
- 同步骤继续保留输入/选区/滚动；切到不同页面回到起点，返回题库仍恢复原位置。
- 新增六项回归，覆盖主操作顺序、重点反馈、手机搜索宽度、首页真实入口、跨页滚动、播放器裁切。
  缺陷对应测试先失败再通过；原有学习规则、音频生成、隐私和数据结构未改。

截图目录`./screenshots/`共20张，使用合成内容；桌面覆盖1280、1440和2048宽度，手机覆盖明暗与大字。
播放器截图为四句合成文稿及30秒占位音频，不代表真实听感测试。

独立视觉审查最初给出fix，列出播放器拥挤/过强重制按钮、手机搜索挤窄、题库顶部间距、设置嵌套、
播放器元数据未就绪五项。集中修正后，审查对这五项给出ship；这是截图范围内的复核，不是Bruce审美认可。
样式检测返回空列表，但提示动态/static引用无法完整解析，不能据此宣称全量自动视觉合格。

网页完整质量门禁结果见PROGRESS；安卓构建和JVM任务已通过，本轮暂不宣称安卓实机验收通过。
不调用付费服务、不发Release、不上传APK或ZIP。源码推送与公开下载更新是不同交付。

## 网页版交付预览

[首页 · 首次使用](screenshots/desktop-home-empty.png) · [大屏首页](screenshots/desktop-home-2048.png) ·
[题库](screenshots/desktop-bank.png) · [语料](screenshots/desktop-content.png) ·
[练习](screenshots/desktop-sentence.png) · [播放器](screenshots/desktop-player.png) ·
[设置](screenshots/desktop-settings.png)

最终`bash scripts/check.sh --with-e2e`：270 passed / 1 skipped，72 e2e passed，CHECK GREEN。
本地网页版8765已启动，HTML/CSS/训练脚本与源码哈希一致。浏览器旧缓存可用Ctrl+F5刷新。
