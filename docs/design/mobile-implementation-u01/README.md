# 英语说说说：最终手机实现规范

2026-10-06 Bruce 批准实施。此规范取代此前未采用的首页蓝色大卡片与新图标提案。

- 原图标所有资源保持；系统展示名称为英语说说说，应用内部仅出现功能标题。
- 练习首页直接展示中文，口头尝试；查看答案展示英文及音频控件但不自动播，
  听答案展示英文并播放现有片段，收起/换句/离开停止播放，换句重新隐藏答案。
- 当前口答、当前学习、到期句子、已有完整材料按顺序取句并去重。无材料给选题/导入入口。
- 首页轻练只读，不创建会话、不改阶段、提示、记录或日程；正式学习规则继续保留。
- 清透白和午夜蓝共用布局，默认浅色，保存本机偏好；切换不重绘任务或重置播放。
- 导航练习/题库/内容/我的；添加集中在内容，“我的”表单进入详情，减少同屏按钮。
- 正式练习保留当前主动作、帮助、无录音和安全退出；两类学习均保持原有规则。

验收：数据读取回归、首页交互与音频竞态、两主题、移动三尺寸/大字体/键盘、
旧学习流程、图标哈希、Android覆盖安装与资源一致性。全部用合成材料，不调用收费API。
实现截图与本地APK不代表GitHub下载版本已发布；N01实机听感门仍独立保留。

| 角色 | 清透白 | 午夜蓝 |
| --- | --- | --- |
| 背景 | #F5F7FB | #111827 |
| 阅读面 | #FFFFFF | #1C2538 |
| 正文 | #161A24 | #F4F6FD |
| 辅助文字 | #617089 | #A6B2C8 |
| 主操作 | #3150D5 | #B7C7FF |
| 主操作文字 | #FFFFFF | #111827 |

历史概念稿仅留本机，不作为新首页与图标的实现参考。

## 实现与验证

首页候选在本地域模块纯读取，由原生适配的既有今日接口附加返回；服务端公开API、
持久化schema和旧存储键不变。到期超过10句仍整体优先，失效指纹或无可对应音频的
重点不拿整段音频冒充答案。读取今日不再初始化材料学习进度。
记录页同时展示三阶段完整回答与口答录音；进入记录/恢复页读取最新快照。
个人服务表单单独进入详情，提交只保存该详情的字段，不回填/输出密钥。

实际运行及结果：

- `python -m pytest tests/test_mobile_home.py tests/test_mobile_learning.py -q`：3 passed，
  包含读取无副作用、来源/到期顺序、来源音频一致性。领域与UI均先复现失败后修正。
- `python -m pytest tests/e2e/test_mobile_home_ui.py tests/e2e/test_mobile_learning_ui.py -q`：
  13 passed；隔离原生桥、合成WAV，验证隐藏/显示、音频失败/迟到、主题、XSS、录音记录及完整学习。
- `bash scripts/check.sh --release`：ruff、245 passed / 1 skipped、55 e2e、导入/启动冒烟，
  1554KB便携ZIP隐私审计通过。使用本机Git Bash明确路径，未上传包。
- `gradlew :app:assembleDebug :app:assembleDebugAndroidTest :app:testDebugUnitTest --offline`：
  BUILD SUCCESSFUL；JVM测试结果3/3通过。同步后执行既有Java17补丁。
- `adb shell am instrument -w ...AndroidJUnitRunner`：8 tests通过，真实Rhino摘要和WebView首页、
  展示名、原生录音中断保留、后台生成/媒体及既有错误恢复；原生测试使用隔离目录。
- 签名一致的`adb install -r`保留应用目录中的测试标记。模拟器无真实学习状态文件，
  此项证明覆盖安装目录保留；不冒充用户实机私人材料恢复验收。
- APK与源码23份资源一致，原图标源30份、旧APK中193份原生PNG均未变。
  详细哈希与验证计数见verification.json。本地包dist/英语说说说-debug.apk。

## 截图

screenshots包含浅色首页、深色答案、设置/默写及原生空库/答案/音色页；均为合成材料。
三尺寸和大字体批量截图在忽略目录data/.tmp/u01-screenshots。检查后集中修正按钮主题、
标题重复、分类可见性与旧样式优先级，并确认一轮。机械扫描未报告问题，但不能自动
解析服务端/static样式链接；实际截图和交互回归用于补充验证。
原生答案截图使用缺失的合成音频路径验证文字保留，不作为真人听感或音频精度证明。

## 首页视觉修正（2026-10-06，待 Bruce 确认）

Bruce 否定首轮首页视觉。保持已认可的清透白／午夜蓝与中文轻练行为，集中重排首页：
中文居中阅读，来源与答案操作收在同一阅读面内，换句与当前候选序号位于底部；
完整学习入口单独成行。字号跟随正文缩放，不新增统计、生成服务或学习记录写入。
答案按钮保留图标并提供展开状态；系统栏图标随主题切换，程序聚焦标题不显示控件方框，
可交互控件继续保留键盘焦点。静态缓存更新到v12。

- 首先复现答案展开状态缺失与暗色系统栏未切换的失败，再实现并确认通过。
- 首页与完整学习专项：13 passed / 1 deselected；最终`bash scripts/check.sh --release`：
  ruff通过、245 passed / 1 skipped、56 e2e、启动/导入冒烟与1557KB便携包审计通过。
  全量测试曾暴露题库测试在异步回答读取完成前断言；改为等待真实链接后专项与全量均通过。
- 离线`gradlew :app:assembleDebug :app:assembleDebugAndroidTest`构建成功；
  实际`LearningMobileUiTest#nativeUiImportsTextAndKeepsMobileNavigation`：1 passed。
  本轮没有重复声称此前8个原生测试均重新运行。
- 包内23份资源匹配源码，34份图标/启动图片源与193份原生PNG保持；签名与旧包相同。
  证据与新包SHA256见homepage-refinement.json。

本轮真实WebView截图：screenshots/native-home-light.png、native-home-dark.png、
native-home-answer.png；浏览器两主题、三尺寸、长句与大字体截图在data/.tmp/home-refinement。
截图仅使用合成练习，页面布局来自实际运行代码；不是生成概念图。
本地新包dist/英语说说说-首页优化-debug.apk，旧包保留；未上传公开安装包。
首页视觉验收继续等待 Bruce 看结果，工程门禁不能代表审美认可。
