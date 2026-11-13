# 真实 GitHub 与静态源码绑定独立复测

独立测试 Agent：`/root/retest_12_sources`。限定范围通过，96/100（40/28/19/9）。未发现本任务范围内的产品失败或阻断问题。测试时间以 evidence.json 中 UTC 原始记录为准（2026-11-13 UTC / 客户端 2026-11-12）。

被测 HEAD：`30985b117bae716b699bd07f9dcf89bd2e65bbfe`。真实解压当前 `dist/feature-progress-tracker-codex.zip` 后按 `.mcp.json` 启动 Python stdio MCP；包 SHA-256：`92d4236f960fc76aa9db6156265a5397761c951de9371e44dd469c95bd2e271a`。核心 4 个源码文件与当前 checkout 逐字节相同。

## 命令

```sh
python3 /tmp/fpt-20261112-github-final-d67v4d1j/run_stdio_live_test.py /tmp/fpt-20261112-github-final-d67v4d1j search
python3 /tmp/fpt-20261112-github-final-d67v4d1j/run_stdio_live_test.py /tmp/fpt-20261112-github-final-d67v4d1j prepare
python3 /tmp/fpt-20261112-github-final-d67v4d1j/finish_stdio_source_test.py /tmp/fpt-20261112-github-final-d67v4d1j finish
```

全部从本目录的 `run_all.py` 顺序执行；search / prepare / finish 均退出 0。共 48 次真实工具调用、51 次 JSON-RPC 应答；11 次工具拒绝均为预期，MCP 服务最终退出 0，stderr 为空。

## 观察与证据

- `search_references` 真实联网返回 jonschlinkert/is-number、真实链接、MIT 许可证与 README（README 仅作资料）。显式选择后 prepare 浅克隆固定提交 `98e8ff1da1a89f93d1397a24d7413ed15421c139`，`--no-checkout`，未安装依赖、未运行参考代码、测试或 benchmark。
- 实际 1 仓库 / 4 片段：index.js 1–18、test.js 1–140、benchmark/index.js 1–92、benchmark/fixtures.js 1–140。四份编号节选均与固定提交 `git show` 的对应 blob 行完全相同。
- 本 Agent 实际静态阅读 index.js 11–17（有限数字、非空字符串与转换后的有限性）及 test.js 32–44、102–114（正例与空字符串/空白反例）。报告逐项引用真实行号并注明未运行、不代表实现或开发验收；无伪造模型分析或独立开发审核身份。
- 首次准备记录为“已读取 1 个参考仓库的固定提交，共 4 个源码片段；等待当前宿主提交逐项核对报告。”再次准备同样计数，返回“已克隆，使用本地提交”；binding 与 snippets 不变，第二次 GIT_TRACE 无 clone/fetch。
- 明确不选参考后，repositories/snippets 为空，记录为“未选择参考仓库，本次无源码证据”；不再误称读取固定提交。
- 有效报告 → 台账候选 → 保存完成；1 个最细功能、0 个已完成，状态未开始，执行 Agent 待分配、实现证据无、审核与评分待审核，没有把参考依据当开发完成。
- 11 个预期拒绝：不存在行号 400；规划变化后的旧报告生成、旧 ticket、旧候选 409；重新提交报告后的旧候选 409；缓存 HEAD 漂移后的旧报告生成、旧 ticket、旧候选 409；缺失缓存生成 409 且没有隐式克隆；参考选择变化后的旧 ticket、旧候选 409。
- 每种拒绝组后原台账逐内容/版本保持不变。全部成功调用进度有序到 100；9 次失败停 30、2 次失败停 10，无失败 100%。失败操作记录为中文标题，保留实际失败原因。
- 缓存漂移仅在隔离目录用原树构造 TEST ONLY 本地 commit，未把它作为真实 GitHub 来源提交任何核对报告；随后恢复原真实 HEAD。缺失缓存测试临时移动目录后复位。最后恢复真实选择并重新核对/生成/保存，仍 0 完成。

## 测试脚本问题及修正

首次隔离运行把 history 的倒序列表末项当最新项，造成“明确不选”日志断言失败。原始返回实际正确，已保留在 prior-harness-correction.json 及旧隔离目录；改读 records[0] 后在全新目录完整重跑三阶段通过。最终核验另误写包内源码路径 package/scripts，FileNotFoundError 后依据 .mcp.json 改为 package/runtime/scripts，4 文件比较通过。这两项是测试假设错误，不计为产品失败；没有隐去原始记录。

## 评分与限制

功能与验收 40/40：本任务要求的真实流程、计数日志、缓存复用、旧绑定拒绝全部有证据。正确性和边界 28/30：未在本轮联网阶段注入 GitHub 限流、断网、超时、无支持源码仓库或并发写入。验证证据 19/20：真实 stdio 与完整 frames 可查，但不等于真实 Codex/Claude 自然语言宿主会话。可维护性 9/10：源码读取和绑定职责明确、错误按阶段记录，现存紧凑写法略不利检查；未覆盖系统整体维护性。

本报告仅覆盖 GitHub/静态源码/绑定链路，不替代浏览器、全量自动化、真实宿主安装或模型会话验收。未扫描用户文件，未修改产品源码、产品台账或创建提交。已按 feature-progress-tracker 读取现有规划/台账，向协调者提供本测试证据，由协调者串行同步已有项目台账；本子任务不自行勾选。

## 证据文件

- evidence.json：全部请求、应答、进度通知、实际报告与断言结果。
- search.log / prepare.log / finish.log：三个阶段输出。
- summary.json：命令、包散列、版本、结果、分数与限制。
- git-trace.log：实际 Git 调用；evidence.json 的 cache_reuse.git_trace 为第二次准备的精确区间。
- package-source-matches.json：四个当前产品源码与解压包逐字节比较。
- prior-harness-correction.json：初次测试假设错误及原证据路径。
- run_stdio_live_test.py / finish_stdio_source_test.py / run_all.py：适配后的完整复现脚本。
