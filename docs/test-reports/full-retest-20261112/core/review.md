# 2026-11-12 独立核心回归复测

- 审核 Agent：/root/retest_12_core
- 被测版本：30985b117bae716b699bd07f9dcf89bd2e65bbfe
- 结论：本轮自动化范围通过，未发现 F09-04 / F12 回归；不代替浏览器、真实宿主模型或长期压力验收。
- 测试/检查命令：14 条，全部退出码 0；未重复运行同一测试命令。
- 计数：常规 Python 194 项；额外历史 7 组、层级/状态/依赖 13 项、记录真实性 5 项；顶层 CJS 8 份；独立 CJS 1 份含 3 组断言；git diff --check 1 条。各类计数不相互相加冒充统一测试数量。
- 隔离：TMPDIR 指向本报告目录 tmp；所有项目写入均为临时夹具，仓库仅作源码读取。历史脚本的持久夹具亦留在 tmp 子目录。
- 261 个被跟踪文件前后 SHA-256 相同，git status --short 为空；未修改产品代码、台账，未提交。

## 关键证据

- F09-04：无参考明确显示无源码证据；文档/空/超大/二进制仓库无可用源码片段；有效片段记录实际仓库/片段数；Git 未出生、UTF-8 损坏、读取超时、票据写入失败均记录失败而非成功；旧失败记录读取不改写；14 种旧失败标题仅显示中文翻译。
- F12-01/F12-03：24 轮父子审核与需求变更，台账从 1,112 增至 93,799 字节，首轮后每轮 3,865–3,872 字节；12 轮升级保留旧嵌套历史原文；取消/重新采用四轮总数稳定；五种明确非完成状态准确保存；临时依赖映射、保留编号、过期完成拒绝、已验收结构保护通过。夹具审核身份是测试数据，不是业务验收或真实模型输出。
- F12-02：本轮全量回归覆盖过期版本/报告/参考绑定、跨项目候选、外部编辑、跨进程锁和历史保存回滚；追加脚本拒绝过期建议、规划和台账候选，拒绝时原文不变。
- F12-04/本次界面修复：8 份页面脚本覆盖只读 GET、旧写路由拒绝的 Python 配套、轮询乱序、历史选择、三级父子优先展示、独立详情折叠保留、项目排序后路径展开状态与更新路径保持、未知或恶意文本安全显示。

## 独立评分

| 维度 | 得分 | 依据 / 扣分 |
|---|---:|---|
| 功能与验收标准 | 40/40 | 自动化范围与当前验收相符，前次反例均通过；未扩大为真实模型验收 |
| 正确性和边界 | 29/30 | 25 组/项额外边界通过；未验证超大历史、长期高并发与跨平台 |
| 验证证据 | 18/20 | 命令、退出码、全部 stdout/stderr、文件校验齐全；本 Agent 未亲点浏览器或真实宿主模型 |
| 可维护性 | 9/10 | 既有脚本可直接复跑；usability 两脚本含当前机器绝对源码路径，移机需适配 |
| 总计 | 96/100 | 本轮自动化范围通过，无阻断 |

## 限制

- Node DOM/VM 断言不是浏览器布局、键盘或读屏实机验收；本 Agent 未操作浏览器。
- 全量测试使用 codex/claude 协议标签及夹具，不表示真实 Claude CLI 安装或模型会话通过。真实模型、真实 GitHub 网络、平台兼容及长期压力未由本 Agent 复测。
- 本轮没有重新构建安装包；常规套件包含既有制品运行测试，单独的制品、升级与实机网页范围由其他 Agent 负责。
- 曾有一次日志读取辅助命令因漏 import json 退出 1，补正后只重新读取日志；不属于上述 14 条测试命令，未重跑测试或改产品。

## 命令与完整日志

| # | 命令（cwd 为项目根目录） | 退出码 | 日志前缀 |
|---|---|---:|---|
| 1 | `python3 -B -m unittest discover -s tests -v` | 0 | `01-unittest` |
| 2 | `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node tests/test_adoption_dashboard.cjs` | 0 | `02-test_adoption_dashboard` |
| 3 | `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node tests/test_dashboard_hierarchy_view.cjs` | 0 | `03-test_dashboard_hierarchy_view` |
| 4 | `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node tests/test_dashboard_poll.cjs` | 0 | `04-test_dashboard_poll` |
| 5 | `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node tests/test_markdown.cjs` | 0 | `05-test_markdown` |
| 6 | `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node tests/test_planning_activity.cjs` | 0 | `06-test_planning_activity` |
| 7 | `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node tests/test_planning_history_races.cjs` | 0 | `07-test_planning_history_races` |
| 8 | `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node tests/test_planning_sheet_view.cjs` | 0 | `08-test_planning_sheet_view` |
| 9 | `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node tests/test_readonly_viewer.cjs` | 0 | `09-test_readonly_viewer` |
| 10 | `git diff --check` | 0 | `10-diff-check` |
| 11 | `python3 -B docs/test-reports/host-chat-repairs/history_acceptance_audit.py` | 0 | `11-history-acceptance` |
| 12 | `python3 -B docs/test-reports/host-chat-repairs/adversarial_r345_review.py` | 0 | `12-r345-adversarial` |
| 13 | `python3 -B docs/test-reports/usability-repairs/review_usability_repairs.py` | 0 | `13-usability-boundaries` |
| 14 | `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node docs/test-reports/usability-repairs/review_usability_repairs.cjs` | 0 | `14-usability-dom` |

每条命令的完整输出分别存于同目录 `<日志前缀>.stdout.log` 和 `<日志前缀>.stderr.log`。元数据见 `summary.json`，文件校验见 `tracked-before.json` / `tracked-after.json`。

> 后续范围补充：已独立确认两项新发现的既存 P3（目标占位持久化、功能详情字段重复），见 additional-review.md。原自动化通过不代表整体无问题。
