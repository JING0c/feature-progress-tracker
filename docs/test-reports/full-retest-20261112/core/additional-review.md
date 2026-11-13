# 2026-11-12 追加独立审计：目标占位与重复详情

审核 Agent：/root/retest_12_core；版本：30985b117bae716b699bd07f9dcf89bd2e65bbfe。

结论：两个观察均成立，建议作为 F09-07 的新增 P3 子问题记录，并关联 F12-01、F12-04。不因这两个现象撤销 F08 / F12 的现有技术验收；原先 14 条基线自动化命令通过的事实不变，但不能将其解释为整体没有问题。本次追加 1 条只读 Python 复现命令，包含 2 个新观察，未重复跑原有测试。

## 1. P3：有效规划生成的台账仍保留“目标：待规划”

- 包 Agent 的两份证据显示 Codex / Claude 协议标签下均出现，候选生成后最终保存也保留占位。本 Agent 又用当前 checkout 的纯函数独立复现：规划通过 inspect_plan，目标正文明确为“帮助管理员整理和查看个人借阅图书。”，结果仍有“目标：待规划”。
- 根因：scripts/serve_dashboard.py:619 在新建项目时初始化该占位；scripts/planning_operations.py:294–296 同步功能记录后保留原台账头部，没有从有效规划提取目标。scripts/project_service.py:505–507 要求候选精确匹配转换结果，因此当前不能通过 save_ledger 任意替换这个头部。
- 性质：这是**自动生成台账头部元数据不准确**，会持久化，不能只描述成 CSS 或屏幕排版问题。但原规划目标未被删除，功能树、验收、完成统计及写入保护没有因为它失效。
- 验收映射：F08-01 约定最新规划/当前页保护；F08-02/03 约定源码与版本绑定。F12-01 约定宿主工具操作，F12-02 约定版本/源码/跨宿主写保护，F12-03 约定采用/审核进度，F12-04 约定只读网页与导航。现有条文没有规定台账头部自动同步项目目标；本观察也未反证其中任何门槛。因此建议在已有未完成 F09-07 增加明确子问题“有效规划生成台账后清除待规划目标占位，保留用户已有自定义头部”，关联 F12-01，而不按源码或进度失败重新打开 F08/F12。
- 与旧三修复关系：这不是空参考源码记录失真、父子展开顺序、中文标题/路径折叠的复发。

## 2. P3：展开验收详情后技术/准备各显示两次，采用进入备注

- 本 Agent 已通过 view_image 实际查看根 Agent 的 05-adopted-acceptance.png。F01-01 展开后，上方完整介绍已有“所需技术：待确认”“前期准备：测试书目”，下方再出现同样两段；“备注：采用：是”也确实可见。
- 随后读取同一项目真实规划：F01-01 原始备注只有“测试夹具”，采用为“是”，技术和准备各只有一个字段。只读转换前后原文件 SHA-256 均为 4307162e10f6a28bc7ee922e98bd47e827c3a588345cee03b4ad7c8239d99f2a。
- 根因路径：scripts/planning_sheet.py:170–186 未把采用/技术/准备识别为独立类型，均归 extra；291–293 拼入备注；416–418 再将备注拼入“功能介绍”；509–525 将技术/准备另投影为列；scripts/project_service.py:34–45 保持单独列；scripts/planning-sheet-view.js:118 先显示含这些值的完整介绍，再追加技术/准备两段。
- 性质：只读投影/展示重复和标签错位，增加阅读长度与混淆。源 Markdown 字段未损坏，采用选择/统计、父子功能或审核状态未因此改变。登记 F09-07 阅读打磨子问题，关联 F12-04；不能说技术和准备缺失。

## 历史与范围

git diff --stat 4b9f60d..30985b1 对上述 planning_operations.py、planning_sheet.py、planning-sheet-view.js、serve_dashboard.py 四文件输出为空；4b9f60d 中两条关键逻辑已存在。因此它们是本轮新发现的既存问题，不能归因于 1eeaf33 的三项修复。

14 条基线测试/检查中对三项修复的反例、边界和独立 DOM 检查仍通过。原 96/100（40/29/18/9）仅为自动化审查范围评分，不是整体用户体验已无问题的评分；两个新增 P3 均未修复，不增加完成勾选。

## 真实宿主调用证据边界

本 Agent 只读核对了根 Agent 产出的 host/command.json、events.jsonl、result.json：Codex exec 测试进程退出 0；配置明确 approval_policy="never"；20 个 MCP 完成事件中 18 个 status=completed/error=null，另 2 个 prepare_source_review 为 failed，错误原文均为“MCP tool call requires approval, but approval policy is never”。失败发生在宿主工具批准层，不能写成产品源码读取执行失败或成功。

该隔离规划明确不选外部参考，其 generate_ledger/save_ledger 成功是无参考分支证据。不能冒称本轮真实 Codex 的源码准备、读取、报告提交端到端已通过；也不能将 Claude 协议标签夹具写成真实 Claude 模型。未发起新的模型调用、网络检索或浏览器操作。

## 证据

- 本 Agent 的两个只读复现：同目录 additional-observations-repro.json。
- 包 Agent 证据：/tmp/fpt-30985b1-package-review-r5g3m8xp/ledger-goal-minimal-readonly-evidence.json、ledger-goal-observation.json。
- 实际截图：/private/var/folders/qf/r4lx43010kx0s658zr73bpbw0000gn/T/fpt-20261112-retest-y41a_d5n/browser/05-adopted-acceptance.png。
- 实际宿主日志：上述 fpt-20261112-retest-y41a_d5n/host 下 command.json、events.jsonl、result.json。
- 未修改产品代码或台账、未提交；feature-progress-tracker 验收标准已对照，交主 Agent 串行登记。

## 最终主报告与台账记录审计（2026-11-12）

限定结论：**修订后的主报告与台账记录审计通过**。这不是整体产品无缺陷、真实 Claude 或真实宿主源码准备/提交全流程通过的声明。审计对象为 docs/test-reports/2026-11-12-full-retest.md 与本轮 功能执行情况.md 差异；只读核对归档证据、3 张逐屏总览和现有测试结果，本 Agent 未重新操作浏览器或模型。

- 已核实并纠正两处表述：目标占位由包/核心各自复现，详情重复由核心实际看图与只读投影确认；倒序历史假设错误对应新目录整轮重跑，包路径错误仅对应修正后的 4 文件比对。没有把两者混为多次完整测试。
- 原始包协议重数：69 条 JSON-RPC 记录，其中 63 次 tools/call；Codex、Claude 两入口各覆盖 18 种工具。源码证据重数：51 条 JSON-RPC，48 次 tools/call，11 个预期拒绝。
- 真实宿主证据仍为 18 成功、10 种成功工具、2 次 approval_policy=never 宿主拒绝；没有扩大为真实源码全流程或真实 Claude 通过。新验收内容的语义进入各产物；台账分号规范为逗号已公开说明。
- 本 Agent 核对 3 张逐屏总览，并确认归档有 16 张编号截图；13 点击/2 Enter、390 文档及 body 宽度来自根 Agent 的实际操作测量记录，与截图相符，不冒充本 Agent 亲自点击。当前 4 行与历史 2 行、子项先于父详情、窄屏路径折叠/换行在截图中可见。
- 独立读取实际下载文件：8,274 字节，SHA-256 a9bf629122973eba4308dacff437ce57c673039f906fb56cb1d4154ddecfe5b8，ZIP 10 项、XML 8 项解析通过，“搜索图书”“筛选作者”“拒绝空标题”存在；未在原生 Excel 中打开。
- 台账改前改后解析均为有效叶 46、完成 43、待审核 2、进行中/受阻 0；本轮没有新增完成勾选。F09-07 保持未完成，两项问题及 P2/P3 分歧公开记录。保留 F08/F12 技术验收有当前范围依据，未将新问题遮蔽。
- 主报告和台账的 staged diff --check 通过。完整 staged diff --check 曾返回 2，仅归档原始 host/规划操作记录.md 的 18、119 行尾空白；该夹具需要保留原始字节，属于证据文件格式例外，不能宣称整个暂存区该命令无条件通过。没有修改原始证据或产品来隐藏检查输出。

审计对象具体摘要与文件 SHA-256 见同目录 final-evidence-audit.json。本次审核只写 /tmp 中本报告与元数据，仓库由根 Agent 负责归档、校验和提交；没有重跑已通过的产品测试。
