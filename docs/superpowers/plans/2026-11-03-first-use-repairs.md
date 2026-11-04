# 首次使用体验修补 Implementation Plan

> 执行方式：当前会话直接实现，完成后独立 Agent 审核。用户已要求开始解决，不再重复请求实施许可。

**Goal:** 修复首次使用报告 A01–A15 的入口、保存、阅读和反馈问题，用同一路线复验。
**Architecture:** 沿用单页、Markdown 事实来源及 Excel 式层级清单。首次规划按状态显示需求与参考，已有规划继续原导航；共用编辑保存动作，安全呈现来源链接。后台只在 Codex 等待期间提供真实取消，不取消文件写入事务。
**Tech Stack:** Python 标准库、原生 JavaScript/CSS、现有 CJS/HTTP 测试。
**Spec:** docs/ux/2026-11-03-first-use-acceptance.md

## Global Constraints
- 保留现有配色、稳定编号、采用选择、历史、导出格式及规划门槛。
- 用户项目不作测试数据；从独立交付副本、空目录、1280×720 复验。
- 不伪造 GitHub 参考理由或百分比；不执行参考仓库代码。

## Review Focus
- 导入/恢复草稿与真正空白项目不可混淆，仍显示有效原资料。
- 顶部保存必须提交编辑中的字段，失败保留草稿，不能保存旧 planText。
- 生成切清单；轮询不得打断用户手选的章节和编辑。
- 取消只针对当前项目当前任务，进程退出后才报告取消，不触发后续保存。
- 新任务开始后，旧任务完成提示的定时器不能隐藏新进度。

## Tasks
- [x] 1. 主流程：planning.html、planning-workflow.js、planning-sheet-view.js。在已有 VM 测试先覆盖顶部编辑保存、首次状态、生成后的清单切换；修复并运行 CJS。
- [x] 2. 阅读和反馈：planning-workflow.css、planning-sheet.css、planning-activity.js、planning-markdown.js。显示简短说明、压缩编号列、技术准备收进逐行详情、合并父标题置顶、编辑时隐藏原表、完成通知定时消失；安全链接和摘要用现有测试验证。
- [x] 3. 新建目录及取消：projects.html、serve_dashboard.py、planning_progress.py。空目录仅新建时分配独立目录，导入仍要求路径；取消必须终止当前 Codex 子进程再解锁。先写真实 HTTP 回归。
- [x] 4. 全套测试与独立审核；从交付副本真实 Codex 重走基线路线，截图编号、总览及点击对比；更新报告、台账并本地提交，不推送。

执行结果：最终产品1deb484；独立审核94分。主路线两轮真实重走，最终12点击/25张含附加截图；剩余A06、A07细节和A10打磨另列F09-07，未宣称15项全清。
