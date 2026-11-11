# R6 与最终插件制品独立复核

审核者：`/root/adversarial_upgrade_packages`。日期：2026-11-10。被审 HEAD：`f5eef1dbff9377a222492b39f12e6b514b7d39be`。未参与实现；只写本目录临时测试数据，未改项目代码、用户数据或全局配置，未推送/发布。

结论：R6 修复通过；当前三个 ZIP 与当前源码构建逐字节一致；两套单插件可脱离源码运行并完成指定公开 MCP 全链。未发现本范围新 P1/P2/P3 缺陷。F11-01 的真实 Claude 宿主验收仍缺证据，不能仅凭此报告整体勾选。

## 独立实证

- 直接读取当前 `dist/feature-progress-tracker-marketplace.zip`，不是以重新构建的包代替待交付包。旧版从固定提交 `f62f163d79abe92762c68b14291b28359d37a8c2` 独立临时构建。
- 实际 Codex CLI `0.166.0-alpha.6`，两套独立 `CODEX_HOME`：原目录完整替换、换目录移除旧注册再添加新注册，两路线均从已安装/启用的 0.1.0 升级到已安装/启用的 0.2.0；来源路径正确。
- 复现旧触发器：同名市场注册不同路径返回 1；通过实际 shell `&&`，后续安装没有执行，仍为旧版，证明失败即停。
- 两路线均从实际 `installedPath` 启动 MCP：initialize 返回 0.2.0，tools/list 返回 18 个不同工具。安装缓存完整文件集合一致；清单本身及其 35 个文件 SHA-256 均与当前市场 ZIP 一致。
- 独立构建到临时目录，与当前 dist 的三个 ZIP 逐字节比较，全部一致；包内清单、单插件与市场内同宿主字节、运行时代码与源码逐文件匹配。
- 从当前两套单插件 ZIP 解压，在源码以外 cwd 启动 `.mcp.json` 中入口，去除 PYTHONPATH/PYTHONHOME。Codex 和 Claude 包各有全新的独立 workspace；均发现 18 工具，均完整执行：新建/读取 → 保存初始规划 → 新增功能预览/保存 → 记录构造的测试建议 → 选择建议预览/保存 → 源码核对空参考绑定 → 生成/保存台账 → 状态更新 → 历史 → Excel → 只读看板 → 停止服务。
- 两包合计 56 个 JSON-RPC 请求，实际调用 16 个工具（未调用联网搜索/选择参考两个工具）。校验两种预览均不提前保存、旧 revision 写入拒绝、三个历史版本及异常后 ping 仍可用；成功进度结束为 100，预期失败低于 100。
- 两包合计 30 次 HTTP 请求：项目列表、runtime、规划页、规划原文/表格、台账/元信息、历史和 Excel 返回 200。实际返回数据包含新增功能及修改的验收标准。每包四种旧 POST 写入/聊天路径均返回 410 和 host_conversation_required，检查前后全部 Markdown SHA 不变。
- MCP 和 HTTP Excel 均以 ZIP/XML 检查完整性并包含预期功能、验收文本。测试创建的查看服务均已停止；无清理错误。

## 制品 SHA-256

| 制品 | SHA-256 |
|---|---|
| Codex | `1a7c5dd7a71f64a8374574ecca26642cad15cbc4775b5fd8672ede7c5c9b1ac6` |
| Claude | `28f21f93e2d4ab34044799e4ea9ee55c6d90ddc9ac5cd9650c5538afe139ea78` |
| 完整市场 | `a498d868566af20546543ad47b39e08ca0f6a96caf598baa138629b488e4adf0` |

## 评分与未测边界

94/100：功能与验收 38/40（实际 Claude 宿主加载仍缺）；正确性/边界 30/30（本次升级失败链、缓存一致性、预览、旧版本拒绝、HTTP 只读均有实际证据）；验证证据 16/20（未运行真实 Claude CLI、真实模型或自然语言宿主会话，未做浏览器视觉 QA、联网 GitHub/源码下载）；可维护性 10/10（两路线文档明确，清单和公共工具入口可复跑）。这些限制不重新阻断已实证的 R6 修复，但保留 F11-01 待审核。

本轮未重复根 Agent 已完成的 187 项 Python 与 7 份 CJS 全量检查；未声称自己执行这些检查。未验证旧宿主会话自动刷新、其他 Codex 版本或其他操作系统。Claude 标记仅为实际解压包的 stdio 参数，不等于实际 Claude Code 宿主。

## 证据与复跑

- `verify_current_dist_upgrade.py`：基于仓库升级验证脚本审阅后改为读取当前 dist，另加安装缓存文件集合及清单自身哈希验证。
- `upgrade-evidence.json`：19 次实际命令及两次安装缓存检查；临时安装目录已清理。
- `stdio_final_check.py`：当前两套 ZIP 的独立工作区完整流程、HTTP、Excel和制品对比。
- `stdio-final-evidence.json`：精简协议请求摘要、HTTP结果、制品 SHA 和两宿主断言。

```sh
python3 -B /tmp/r6-final-review-sq0i8i3g/verify_current_dist_upgrade.py --output /tmp/r6-final-review-sq0i8i3g/upgrade-evidence.json
python3 -B /Users/olcgb/code/protuct_plan/scripts/build_plugins.py --output-dir /tmp/r6-final-review-sq0i8i3g/rebuilt-market --dist-dir /tmp/r6-final-review-sq0i8i3g/rebuilt-dist
python3 -B /tmp/r6-final-review-sq0i8i3g/stdio_final_check.py
```

已阅读 feature-progress-tracker 技能并检查现有台账 F11-01，按主 Agent 的只读/串行合并分工未改台账。本轮可记录独立关闭 R6 和制品复核通过，真实 Claude 条件仍保留。
