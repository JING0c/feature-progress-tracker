# 独立审核：2026-11-11 易用性修复

审核 Agent：/root/review_usability_repairs。只读代码和测试，未修改产品代码、项目文档或提交；补充测试全在 /tmp。

结论：本轮范围的代码与自动化审核通过；未发现阻断或应修复的回归。综合 9.5/10。浏览器视觉、实际点击与键盘操作由根 Agent 另行验证，本报告不冒称已做。

| 项目 | 结果 | 评分 | 证据与边界 |
| --- | --- | --- | --- |
| 源码核对记录事实准确 | 通过 | 9.7/10 | 无参考或明确不选不会声称已读取；固定提交无片段明确区分；有证据写实际仓库/片段数量；无 HEAD、损坏缓存、超时、无效 UTF-8、写票据失败均追加失败且不生成成功记录，不改旧记录/规划；未做实际联网 clone，本轮使用真实隔离 Git 仓库与故障注入。 |
| 父子卡片渐进展开 | 代码/自动化通过 | 9.3/10 | 三级父节点先放 children 后放独立 details；叶子直接 meta；字段与 notes 全保留；父卡、子卡与父详情键独立；祖先闭合时后代的 open 状态也能保留；检查 scoped arrow CSS，原颜色及嵌套样式保留。真实浏览器视觉/键盘未由本审核 Agent 执行。 |
| 中文失败标题及路径折叠 | 代码/自动化通过 | 9.5/10 | 11 种真实服务失败中文化且原因原样；14 种历史标题在冻结对象上显示翻译，原始文件读前/读后字节不变；未知 snake_case 操作用中文兜底。项目路径默认收起、换序/路径更新后按项目身份保留展开，workspace/single mode 正确。真实视觉由根 Agent 验证；前后端各一份标题映射属低维护成本风险，不是阻断。 |

关键位置：scripts/project_service.py:56、141、414；scripts/dashboard.html:10、12、24、25；scripts/planning-activity.js:3、4、24；scripts/projects.html:18、28、40、47。

执行并通过：

- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_source_activity_truth.py' -v（7）
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_source_review.py' -v（3）
- PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_project_service.py' -v（22）
- Node tests/test_dashboard_hierarchy_view.cjs
- Node tests/test_planning_activity.cjs
- Node tests/test_dashboard_poll.cjs
- Node tests/test_readonly_viewer.cjs（10 场景）
- PYTHONDONTWRITEBYTECODE=1 python3 /tmp/review_usability_repairs.py（5 个独立补充边界）
- Node /tmp/review_usability_repairs.cjs（独立三级卡片、路径身份与原始记录冻结检查）
- git diff --check

Node 实际路径：/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node。

本轮源文件 SHA-256（便于根 Agent 核对独立审核适用版本）：

- project_service.py: e118984bc2bfbd1c424ad94a2b57f6b267ff71e2ec9eb5f7f0741cfd7ec13e7f
- dashboard.html: 6012fb5f68734ba78ebb9d7f529038252a0f7b10ab39b9c7055b292a9f765e98
- projects.html: 2da2a6eae08d9f99d35a3f9a4dda587a7c2b42c52bd4bdcbb6bd03fd030cf0b4
- planning-activity.js: da23721ad2d83c2aab9d4bc6b49d12f7f18f72d4f7425281bd92f47041b0438c

台账检查：已读取 feature-progress-tracker 技能及已有项目规划/功能台账，F09-04（事实记录）与 F09-07（体验）是相关项。按协调者串行合并规则，本 Agent 不并行写台账。根 Agent 可以将本报告的审核身份、范围、分数和边界写入对应项；不要据本次局部修复勾选 F09-07 的全部历史待办。

## 浏览器证据补充及最终独立结论

2026-11-11 补充：审核 Agent 实际使用 view_image 查看根 Agent 保存的五张截图，未亲自执行浏览器点击。复核时四个产品文件 SHA-256 与上文一致。

截图目录：/private/var/folders/qf/r4lx43010kx0s658zr73bpbw0000gn/T/fpt-usability-fixes-0c578d5h/browser-evidence/

- 05-child-first.png：1280×720 首屏可见展开父卡“搜索图书”和内部子卡“筛选作者”；父级完整字段没有挡在子功能前。粉色父卡、浅色子卡、状态侧线、父向下/子向右箭头均可直接观察，层级清楚。
- 10-source-record-open.png：展开的“源码核对资料已准备”记录显示“未选择参考仓库，本次无源码证据；等待当前宿主提交逐项核对报告”，摘要与详情一致；未冒称已读取固定提交。
- 11-legacy-failure-readable.png：旧失败事件显示“保存规划失败”，保留“文件已变化或缺少版本，请重新读取后操作”的原因；同页仍清楚区分未采纳建议、尚未保存预览与功能表保存。
- 15-mobile-path-collapsed.png：390 宽窄屏项目卡默认只显示“文件位置”，长路径不挤占卡片首屏，操作链接及进度仍可见。
- 16-mobile-path-expanded.png：展开后完整路径按行换行，仍在项目卡边界内；可见聚焦边框。静态截图不能独立证明键盘按键过程。

根 Agent 提供的执行证据（本人未重新点击）：父 y439.4、子 y589.9，相差150.5像素，对比基线775像素；Enter可打开父级详情及项目路径；轮询数据变化后父、子、父详情三个details均保持open。该报告与截图结构和本审核独立VM状态验证相互印证。父子间距缩减约80.6%，测量来源明确为根 Agent。

### 按技能40/30/20/10评分

最终本轮修复独立评分：96/100（40/29/18/9），通过，无阻断发现。此评分在五张浏览器截图独立复核后替代前文临时9.5/10结论；不代表历史体验待办全部达标。

- 功能与验收标准40/40：本轮三类修复的约定行为均有实现、自动化与可视截图支持；记录事实、父子渐进展开、失败名称及长路径展示满足范围。
- 正确性与边界29/30：真实隔离Git及独立反例覆盖无HEAD、无片段、编码异常、部分失败、超时、票据写入失败、历史不变、三级独立展开与项目重排；减1分因本轮未重复极端并发、长期大日志压力验证。
- 验证证据18/20：32项仓库Python、4个CJS、5个独立Python反例及独立前端检查通过，并实际独立查看五张截图；减2分因真实浏览器按键和坐标测量来自根Agent执行报告、审核者未重跑浏览器，且未重新发起实际联网clone。
- 可维护性9/10：修改集中、未迁移历史、保持原读取协议；减1分因前后端动作标签各保留一份以及现有渲染器长单行降低后续维护便利性。两者均为非阻断项。

### 台账结论

- F09-04：重新达标，可恢复当前“已完成”及勾选。此次撤销验收的具体原因是空参考误报“已读取固定提交”；现在新增记录事实准确，失败状态忠实，旧日志没有被改写。建议保留2026-11-10失败历史，并追加本次修复和复审证据。本结论基于本次受影响范围复审及此前有效验收记录，不冒称对F09-04所有历史功能重新完成联网端到端验收。
- F09-07：只关闭2026-11-10新增的本轮子范围——父卡完整字段阻挡子功能、失败标题显示内部名称、窄屏长路径默认占位。父级详情按需展开、中文标题与路径折叠已通过。F09-07总项保持未勾选；A06候选中文说明、A07取消/阶段用语、A10内部滚动及原有整体交互问题未由此修复或验收。

协调者按技能串行将本补充写入既有台账，本审核 Agent 未修改项目文件。
