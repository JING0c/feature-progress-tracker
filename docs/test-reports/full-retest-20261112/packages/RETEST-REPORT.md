# 30985b1 ZIP 独立协议复核

审核 Agent：/root/retest_12_packages。关联源码：30985b117bae716b699bd07f9dcf89bd2e65bbfe。
结论：三份 ZIP 的独立重建与完整性验证通过；两套宿主适配入口的 18 个工具全链、进度及无参考记录回归通过。另发现生成台账保留“目标：待规划”的产品文案缺陷，不能把脚本全链通过解释为产品没有缺陷。

## 范围和方法

在独立 /tmp 目录复制既有脚本，保留原版；执行 build_plugins.py --output-dir <tmp>/rebuilt --dist-dir <tmp>/rebuilt-dist。实际解压 dist ZIP，以各自 .mcp.json 的启动参数启动 python3 stdio MCP，发送真实 JSON-RPC，逐条保存请求和全部返回 frames。没有 mock 服务器，也没有真实模型或 Claude 宿主会话。
全部项目数据、解压包、构建输出及证据留在该临时目录。没有修改源码、真实业务目录、台账或提交。

## 制品一致性

| ZIP | SHA-256 | 结果 |
|---|---|---|
| codex | `92d4236f960fc76aa9db6156265a5397761c951de9371e44dd469c95bd2e271a` | 与独立重建逐字节一致 |
| claude | `797fbc2b2dc25a1e205dbe2f92686d4c9ba3cb3b6bf4340c36b1af30e5b4869b` | 与独立重建逐字节一致 |
| marketplace | `4c5acc15f50ad633e53bb5466ef1ded4149f9e7a992d460ca622397a49f9fd61` | 与独立重建逐字节一致 |

Codex 清单 35 文件、Claude 清单 33 文件逐项哈希正确；市场包内两套插件文件与单独包一致；runtime/scripts 与仓库同名源文件逐字节一致。未打入 .env、__pycache__ 或已退役 planning_agent.py。

## 实测覆盖

- 每套宿主枚举且调用全部 18 个工具，共 63 次 tools/call、69 次带 id 的 JSON-RPC 请求。
- 新建项目、保存有效规划、代码新增功能预览、保存、建议记录、选择建议预览、保存、参考查询/空选择、核对报告、台账候选与保存、进度更新、历史、xlsx、启动/停止看板。
- 新增预览和建议预览均未提前写规划；旧 revision 保存拒绝，历史记录使用中文“保存规划失败”。
- 每套历史在追加浏览器夹具之前均有 3 个规划版本；空参考核对只记录一次“未选择参考仓库，本次无源码证据；等待当前宿主提交逐项核对报告。”，没有虚称已读取固定提交。
- 真实 GitHub 请求使用随机无命中查询，两套都返回空列表；未读取外部仓库 README 或源码。
- 每套 11 个 GET 返回 200、4 个旧写接口 POST 返回 410 / host_conversation_required，共 30 HTTP 请求。HTTP 前后所有项目 Markdown 的 SHA-256 不变。
- MCP 导出和 HTTP 导出的 xlsx 为有效 ZIP/XML 工作簿，含图书管理、添加图书、搜索图书和“拒绝空标题”；未做 Excel 应用视觉打开。
- 两套服务均经标准 stop_dashboard 停止，MCP stdin 关闭后 exit=0，stderr 为空；追加 plugin_manager status 确认 running=false。

## 真实进度百分比

两套宿主的相同调用序列一致。成功结束 100%，错误不显示 100%；百分比来自服务器 frames，不是等待时间估计。

| 工具/情形 | 百分比序列 |
|---|---|
| create_project | 5 → 10 → 95 → 100 |
| list_projects | 5 → 100 |
| read_project | 5 → 10 → 95 → 100 |
| save_plan | 5 → 10 → 40 → 80 → 95 → 100 |
| edit_features | 5 → 10 → 40 → 65 → 95 → 100 |
| save_plan（失败） | 5 → 10 → 10 |
| record_suggestions | 5 → 10 → 40 → 80 → 95 → 100 |
| preview_suggestions | 5 → 10 → 40 → 95 → 100 |
| search_references | 5 → 10 → 40 → 80 → 95 → 100 |
| select_references | 5 → 10 → 80 → 95 → 100 |
| prepare_source_review | 5 → 10 → 95 → 100 |
| submit_source_review | 5 → 10 → 65 → 80 → 95 → 100 |
| generate_ledger | 5 → 10 → 65 → 95 → 100 |
| save_ledger | 5 → 10 → 80 → 95 → 100 |
| update_feature_progress | 5 → 10 → 80 → 95 → 100 |
| history | 5 → 10 → 95 → 100 |
| export_project | 5 → 10 → 80 → 95 → 100 |
| open_dashboard | 5 → 100 |
| stop_dashboard | 5 → 100 |
| create_project（失败） | 5 → 5 |

空参考搜索没有可读取仓库，所以本轮没有出现源码读取阶段或 GitHub 中间抓取百分比；没有编造未发生的阶段。

## 发现：新建项目台账保留占位目标（P2，非阻断）

已保存规划的目标是“帮助管理员整理和查看个人借阅图书。”，inspect_plan 返回 valid=true。Codex、Claude 的 generate_ledger 候选都以“目标：待规划”开头，save_ledger 接受后最终文件仍是该文本；并非网页缓存或仅预览。
最小只读复现使用实际 ZIP 中的纯函数：ledger_from_plan(有效规划，create_project 生成的默认台账，parse)。规划仅含 F01 与 F01-01，无需建议、进度更新或外部参考。
根因位置：scripts/serve_dashboard.py:619 创建默认“目标：待规划”；scripts/planning_operations.py:294-296 同步功能后整段保留旧台账正文，未从规划取目标；scripts/project_service.py:487 生成、:505 再验算、:512 保存同一结果。
需求依据：仓库 SKILL.md:35 台账格式含真实目标，SKILL.md:20/:24 描述先保存有效规划再按规划转换。该文案与已经 ready 的规划状态不一致，会误导阅读台账者；没有证据表明它影响功能层级、规划门槛或进度统计。没有修改源码。

## 浏览器复核夹具

- workspace：`/private/tmp/fpt-30985b1-package-review-r5g3m8xp/codex-workspace-vw6rs4mg`
- 解压 Codex 包：`/private/tmp/fpt-30985b1-package-review-r5g3m8xp/codex`
- 已规划项目：`p-f27375b3eb85`；F01-02 搜索图书下通过 edit_features 分配 F01-02-01 筛选作者，save_plan 保存；prepare/submit_source_review 重核当前规划；generate/save_ledger 成功。
- 空项目：`p-9d95580a7662`；planning_status=pending、ready=false。
- 服务已停止；主 Agent 可自行启动此隔离 workspace。完整路径及 revision 见 browser-fixture.json。

## 限定评分

93/100：功能与验收 37/40（剩余占位目标文案缺陷）；正确性与边界 28/30（过期版本、非法参数、未保存预览、HTTP 禁写已实测，未穷尽所有参数组合）；证据 19/20（完整原始 stdio、构建、历史、HTTP成功响应与工作簿证据，外部参考仅空查询）；可维护性 9/10（制品完整性与相关路径已核对，未做全仓库架构审计）。
此分数只适用于本报告限定的实际 ZIP、确定性工具链和只读 HTTP 复核，不是 Claude 实机安装、真实自然语言模型、浏览器视觉或整个产品的最终验收。工具链回归通过与剩余 P2 文案问题并列成立。

## 原始证据

- stdio_all_tools_check.original.py：原始脚本；stdio_all_tools_check.py：本次实际执行脚本，仅加原始记录和浏览器夹具。
- build-stdout.json、build-stderr.log：独立构建输出。
- stdio-raw-transcript.jsonl：每次请求、所有 progress frames、最终 response 原文结构。
- stdio-all-tools-evidence.json、stdio-stdout.log、stdio-stderr.log：断言、计数、哈希和执行结果。
- codex-history-records.json、claude-history-records.json：首次完整链历史快照。
- codex-http-*.body、claude-http-*.body：HTTP 成功响应原始字节；拒绝响应的解码错误码与断言记录在主 evidence 文件。
- progress-summary.json：每种实际进度序列；services-stopped-evidence.json：停止状态。
- ledger-goal-observation.json、ledger-goal-minimal-readonly-evidence.json：目标文案问题的原始调用抽取与只读最小复现。
- browser-fixture.json：浏览器复核工作区、项目 id、路径与版本。

按 feature-progress-tracker 做了轻量检查，证据交协调 Agent 串行同步已有台账；本审核 Agent 未更改台账。
