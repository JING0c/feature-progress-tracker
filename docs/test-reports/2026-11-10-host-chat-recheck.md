# 宿主对话编排独立复核

日期：2026-11-10。结论：**不通过，1 个 P1、5 个 P2，均尚未修复。**

被审产品版本：`e8d51eafd13de5f193dcd82dcd5710521e5be4f7`，分支 `feat/chat-project-orchestration`，插件制品版本 0.2.0。对照迁移前版本 `f62f163d79abe92762c68b14291b28359d37a8c2`。

本轮仅复核、记录证据并同步已有功能台账，没有修改业务实现或重新发布安装包。三位未参与本轮实现的审核者分别检查服务、进度、插件交付；根 Agent 交叉重跑 R1–R5。测试数据全部位于独立临时目录，未操作用户项目。本文对受影响范围的结论取代上一份报告中的通过结论，旧报告保留。

## 已验证的部分

- 根 Agent 重跑 Python 全量：161 项通过，12.563 秒；7 个顶层 CJS 测试文件全部通过。这些测试没有覆盖下列反例，不能据此判定交付通过。
- 三个 ZIP 与临时重建制品逐字节相同，包内清单及技能链接有效。
- Codex CLI `0.166.0-alpha.6` 的隔离新安装成功，实际安装缓存中的 MCP 入口返回 0.2.0 和 18 个工具。
- Codex、Claude 两种包的实际 stdio 进程共完成 29 次 JSON-RPC 请求，调用了 18 个工具中的 16 个；覆盖项目创建/读取、规划保存、功能编辑、建议预览、无参考仓库的核对流程、台账生成/保存、进度更新、历史、Excel 导出、共用只读服务及跨宿主停止。成功操作进度到 100，错误没有假报 100；错误之后进程仍可响应。
- 服务审核者另独立重跑 41 项服务、采用及聊天边界测试。精确候选比较、旧版本拒绝等保护没有在本轮检查中发现新的绕过。

## R1 · P1：两类历史互相嵌套，正常修改六轮后不能保存

位置：[project_progress.py](../../scripts/project_progress.py) 第 64–67 行、[planning_operations.py](../../scripts/planning_operations.py) 第 117–120 行。

仅一个功能的项目，交替执行“更新实施证据 → 修改验收标准 → 生成并保存台账”。进度快照只剔除自己的进度历史，规划快照只剔除自己的规划历史，两者把对方的完整历史继续嵌入新快照。

| 轮次 | 已保存台账字符数 | UTF-8 字节数 |
|---|---:|---:|
| 初始 | 200 | 414 |
| 1 | 1,083 | 1,821 |
| 2 | 4,336 | 6,420 |
| 3 | 18,361 | 23,975 |
| 4 | 87,135 | 101,993 |
| 5 | 454,008 | 493,068 |

第 6 轮生成候选达 2,503,357 字符，`save_ledger` 被 MCP 参数上限拒绝：`ValueError: arguments.content 长度无效`。这不是大项目或超长用户输入；初始规划只有 186 字符。此时旧文件仍能读取，但正常台账同步已被阻断。

建议：两类快照统一排除递归历史，采用扁平记录或引用，同时保留实际实施与审核证据；不能仅调大长度限制。

证据：[复现脚本](host-chat-recheck/history_growth.py)、[实际输出](host-chat-recheck/history-growth.log)。关联 F12-01、F12-03。

## R2 · P2：规划变更后，仍能按旧验收新标记完成

位置：[project_service.py](../../scripts/project_service.py) 第 529–534 行；进度入口只检查台账版本，没有核对当前规划中的采用与验收。

先生成台账并填实施者及证据，再把已保存规划中的该功能改成“不采用”，验收由“保存后能读取订单”改成“保存后须加密订单”。不重新同步台账，提交独立审核字段并调用 `update_feature_progress` 标记完成，操作成功：台账仍保留旧验收，勾选完成且汇总为 1/1。

规划与台账在预览、保存之间暂时不同是允许的；这里的问题是**允许基于已经过期的要求新增完成结论**。用户会把旧验收结果当成当前项目进度。

建议：完成入口校验当前规划的采用及验收绑定；不一致时明确要求先同步台账。不要仅检查台账里的旧“取消跟踪”字段。

证据：[复现脚本](host-chat-recheck/state_edges.py)、[实际输出](host-chat-recheck/state-edges.log) 中 `completion_against_stale_plan`。关联 F12-03。

## R3 · P2：重新采用子项后，父子被重复计入总数

位置：[planning_operations.py](../../scripts/planning_operations.py) 第 323–325 行、[serve_dashboard.py](../../scripts/serve_dashboard.py) 第 57–59 行。

初始规划 F01 包含 F01-01，总数为 1。保持父项采用，只取消子项并同步台账，父项成为有效叶，总数仍为 1。随后重新采用子项并同步，所有保存均成功，但父项追加在旧子项之后；解析器只查找已经读到的父项，于是将两项解析为并列根节点，汇总变成 2。

这是采用状态切换，不是删除后复用编号。最终需求仍只有一个最细子功能，父子包含关系与看板分母均错误。

建议：同步时确保父项在子项之前，或解析时先收集节点再独立建立层级；保留原有子项历史。

证据：[复现脚本](host-chat-recheck/state_edges.py)、[实际输出](host-chat-recheck/state-edges.log) 中 `readopt_child_after_parent_becomes_leaf`。关联 F12-03。

## R4 · P2：用户明确要求“待审核”，却保存成“进行中”

位置：[project_progress.py](../../scripts/project_progress.py) 第 155–157 行。

将已独立验收的功能更新为“待审核”，工具成功返回，但 `reopened_fields` 覆盖了明确请求的状态。最终状态为“进行中”，取消勾选，汇总为 working=1、review=0。

取消旧审核合理，改变用户明确提交的合法状态不合理，会让待审核工作从对应统计中消失。

建议：使旧审核失效时，保留本次明确指定的合法目标状态。

证据：[复现脚本](host-chat-recheck/state_edges.py)、[实际输出](host-chat-recheck/state-edges.log) 中 `explicit_review_status`。关联 F12-03。

## R5 · P2：新增功能与修改依赖一起提交，临时编号落入正式文件

位置：[project_service.py](../../scripts/project_service.py) 第 314、321–323、331 行。

同一次 `edit_features` 新增临时编号 N1，并把既有 F02 的依赖改为 N1。新增功能被分配为 F01-02，但既有行里的依赖没有同步转换。`save_plan`、`generate_ledger`、`save_ledger` 均成功，最终 Markdown 台账仍保存“依赖：N1”，找不到对应正式功能。如果直接写未来编号 F01-02，又会在合并新增项之前被校验为不存在。

建议：完成合并后对全部行做统一编号映射和依赖校验；未解析的临时引用至少应拒绝保存。

证据：[完整保存复现脚本](host-chat-recheck/dependency_roundtrip.py)、[探索性输出](host-chat-recheck/dependency-probe.log)。关联 F12-01。

## R6 · P2：旧用户照安装说明升级，仍装到 0.1.0

位置：[plugins.md](../plugins.md) 第 40–41 行。

在隔离配置中先安装旧版 0.1.0 市场，再把新版 ZIP 解压到另一目录，按当前说明依次运行市场注册和插件安装：

1. 注册同名市场失败，提示该市场已从另一来源添加，需先移除旧来源。
2. 下一条插件安装返回成功，但实际仍从旧市场安装 0.1.0；`plugin list` 也确认版本为 0.1.0。

全新安装 0.2.0 没有这个问题。旧用户会以为已升级，却缺少本次对话编排新增的工具。

建议：补充旧市场换路径或原路径更新的明确升级路线，并以实际安装版本 0.2.0 校验结果。

证据：[真实隔离安装/升级输出](host-chat-recheck/install-upgrade-evidence.json)。关联 F11-01。

## 独立审核结论与范围

| 审核者 | 范围 | 评分（功能/正确性/证据/维护） | 结论 |
|---|---|---|---|
| `/root/fresh_progress_review` | 进度、采用与独立验收 | 72（30/16/18/8） | 不通过，R1–R4 |
| `/root/fresh_service_review` | 服务、编辑、建议及保存 | 87（36/25/18/8） | 不通过，R5 |
| `/root/fresh_plugin_review` | ZIP、stdio、真实 Codex 安装升级 | 88（34/30/14/10） | 不通过，R6 |

高分不替代尚未满足的验收。本轮将 F12-01、F12-03 重新标为待审核，保留旧审核记录；F11-01继续待审核。其余已通过范围未因本轮推测性扩大影响而撤销。

建议修复顺序：R1 → R2 → R3，然后 R4、R5、R6。前三项分别影响持续保存、验收可信度和看板统计；升级文档可并行处理。

未覆盖：真实 Claude Code 宿主安装（本机无 CLI）、宿主自然语言模型端到端、真实远程 GitHub 搜索/克隆、浏览器逐屏点击和截图、原生 Excel、Windows、长期高并发或断电。本轮双包 stdio 协议实测不冒充真实 Claude 宿主实测，前一轮网页截图也不作为本轮新证据。

## 复现与证据

从仓库根目录运行下列脚本。它们通过公开 MCP `call_tool` 及参数校验操作独立临时项目；输出用于重现当前缺陷，不是已通过的产品回归测试。前两份脚本自动清理临时目录，依赖脚本保留并打印自己的临时目录，方便检查文件。

```sh
python3 -B docs/test-reports/host-chat-recheck/history_growth.py
python3 -B docs/test-reports/host-chat-recheck/state_edges.py
python3 -B docs/test-reports/host-chat-recheck/dependency_roundtrip.py
```

- [Python 全量输出](host-chat-recheck/python-suite.log)
- [制品重建与技能链接](host-chat-recheck/artifact-evidence.json)
- [实际 stdio 请求与响应](host-chat-recheck/stdio-evidence.json)
- [前一轮实现报告](2026-11-10-host-chat-orchestration.md)

报告中的代码行号对应 e8d51ea。日志里的临时目录、进程号和端口仅记录当次测试，不能当成仍运行的项目入口。
