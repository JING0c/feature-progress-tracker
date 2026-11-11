# 三项易用性修复与复验

日期：2026-11-11。修复提交：`1eeaf33`，基线 `4b9f60d`，插件 0.2.0。范围为上轮实测的三项遗留问题；没有恢复网页对话或编辑功能。

## 修复结果

| 上轮问题 | 当前行为 | 证据 |
|---|---|---|
| 空参考仍称“已读取固定提交” | 无参考明确记录“本次无源码证据”；固定提交没有可用片段时也明确说明；有片段记录实际仓库和片段数量；失败和超时保留真实原因，不记成功 | [当前记录](usability-repairs/browser/10-source-record-open.png)、专项 Python 7 项、独立边界 5 项 |
| 子功能埋在父项约 12 组字段下面 | 展开父卡先显示子功能；父项完整字段放在“查看本功能详情”；叶子仍一次展开显示详情；箭头只随本卡状态变化 | [父子卡片](usability-repairs/browser/05-child-first.png)、[详情](usability-repairs/browser/06-child-details.png) |
| 内部失败名、长路径占据界面 | 新失败记录使用中文动作名；旧 `save_plan 失败` 只在显示时译为“保存规划失败”，不重写历史；项目、工作区及看板路径折叠在“文件位置” | [旧失败显示](usability-repairs/browser/11-legacy-failure-readable.png)、[窄屏收起](usability-repairs/browser/15-mobile-path-collapsed.png)、[展开](usability-repairs/browser/16-mobile-path-expanded.png) |

源码核对资料准备不等于核对报告通过，更不等于项目实现或验收。旧版日志的原始事实未迁移，也未猜测当时是否实际读过源码；修复作用于新记录和可识别旧失败标题的显示。

## 实际网页复验

从新解压的 Codex ZIP 启动服务，使用独立临时目录内的上轮图书夹具副本，保留相同父子和历史数据以便比较；新建全新浏览器来源，不接触用户项目或缓存。根 Agent 通过真实页面操作，未直接调用前端内部函数。

路线：项目总览 → 功能看板 → 叶子详情 → 父功能与子功能 → 父功能完整详情 → 当前规划 → 操作记录 → 当时功能表 → 返回记录 → 下载当前 Excel → 窄屏总览与文件位置 → 待规划项目 → 返回总览。宿主协议的新增、建议、保存流程由独立 Agent 另测，不能把只读网页点击算成执行了写入。

- 1280×720，补充 390×844；15 次点击、2 次 Enter，19 张编号截图，没有定位失败。编号 16、17 顶部离开视口是聚焦控件后的正常滚动位置。
- 与上轮同一功能树比较，父入口 y=439.4，子入口 y=589.9，相隔 **150.5 像素**；基线为 **775 像素**。子入口现可在首屏看到。当前仅展开父卡页面高 911 像素；上轮 2,110 像素包含更多详情，不将两种状态当作严格等价的页面高度对比。
- 总览→父功能→子功能详情的最短路径仍为 **3 次点击**。本次改善的是可见性和滚动距离，没有为了宣称优化而把不同路线点击数直接相减。
- 使用 Enter 打开父功能详情和文件位置；叶子一次展开直接显示验收等字段。修改隔离台账后，轮询保留父卡、子卡及父详情的独立展开状态；总览路径展开也在数据更新后保留。
- 390 像素下路径默认收起，展开换行后页面总宽仍为 390，没有整体横向溢出。
- 当前功能清单显示 4 行，旧快照显示 2 行；返回不覆盖当前表。实际下载的 Excel 包含“拒绝空标题”“搜索图书”“筛选作者”，ZIP/XML 结构有效，7,634 字节。[下载检查](usability-repairs/browser/download-check.json)
- 空项目保持待规划；已规划项目进度变化只影响本项目。浏览器 warning/error 日志为空。
- 四页截图总览：[1](usability-repairs/browser/overview-1.jpg)、[2](usability-repairs/browser/overview-2.jpg)、[3](usability-repairs/browser/overview-3.jpg)、[4](usability-repairs/browser/overview-4.jpg)。[测量及环境](usability-repairs/browser/observations.json)
- 复测服务端口 59946 已停止，核验不再监听；未停止用户其他服务。

## 自动化与独立审核

- 全套 Python：**194 项通过**，退出码 0。由实现 Agent 执行，原始输出末尾和准确命令见[测试记录](usability-repairs/core-results.json)；未保存完整原始日志，不冒称存在。
- 根 Agent 集成执行：**8 份顶层 CJS 全通过**。新增回归先红后绿；另有独立 Agent 实际运行 32 项 Python、4 份 CJS、5 个额外 Python 边界及额外前端三级树/路径/冻结历史记录检查。
- `/root/review_usability_repairs` 独立代码、自动化及五张实际截图审核：**96/100（40/29/18/9）**。没有发现阻断问题。浏览器点击、Enter 与几何测量由根 Agent 执行，审核者只复核截图和证据。[独立报告](usability-repairs/review_usability_repairs.md)
- `/root/verify_repair_packages` 对三个 ZIP 独立重建并比对字节，分别启动两套包的真实 stdio：**每包成功调用全部 18 工具，合计 60 次 MCP、30 次 HTTP**。新增→预览→采纳→保存规划→核对资料/报告→台账→导出完整链通过；旧版本拒绝、HTTP 写入 410 及只读不改 Markdown 通过。两包均直接断言空参考文案和中文失败标题。[包审核](usability-repairs/packages/independent-review-summary.json)
- 包测试的原脚本实际只成功调用 16 个工具；本轮扩展脚本增加真实 GitHub 空结果检索和显式空选，达到 18 个，不把工具列表数量冒充执行覆盖率。[协议证据](usability-repairs/packages/stdio-all-tools-evidence.json)

安装包已在本机重建。SHA-256：Codex `92d4236f960fc76aa9db6156265a5397761c951de9371e44dd469c95bd2e271a`；Claude `797fbc2b2dc25a1e205dbe2f92686d4c9ba3cb3b6bf4340c36b1af30e5b4869b`；marketplace `4c5acc15f50ad633e53bb5466ef1ded4149f9e7a992d460ca622397a49f9fd61`。未推送或发布 GitHub，未改用户全局插件安装。

## 边界与台账

F09-04 的记录真实性经独立复审恢复通过，保留旧失败历史。F09-07 只关闭本轮嵌套入口、失败用语和路径展示子范围，不将全部历史打磨待办标成完成；F12-04 的相关只读与轮询行为复验通过。统计恢复为 43/46（93.5%），待审核 2，未开始 1。

本轮未重跑真实 Codex/Claude 自然语言宿主会话、非空远程仓库克隆、原生 Excel、真机或屏幕阅读器。远程搜索仅空结果，源码边界使用真实隔离本地 Git 与故障注入。F11-01 真实 Claude 宿主及 F05-04 长合并组保持待审核。看板进度历史仍直接显示结构文本，属于 F09-07 已登记的其他阅读打磨，未在本轮处理。没有把当前三项通过当作全部产品体验通过。
