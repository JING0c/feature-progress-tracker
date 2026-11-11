# R6 本地市场升级验证

日期：2026-11-10。实施者：`/root/inspect_upgrade_route`。范围：修正[插件说明](../../../plugins.md)和[仓库首页](../../../../README.md)中的本地市场升级路径；不修改业务代码。本记录是实施者验证，不代替另一位 Agent 的独立审核。

旧包来自固定提交 `f62f163d79abe92762c68b14291b28359d37a8c2`（0.1.0）；新包来自 `12fc75c358db470fe777df26653a376bc932074a` 加本轮文档改动（0.2.0）。两者先在临时目录构建完整 ZIP，再解压安装。宿主为 `codex-cli 0.166.0-alpha.6`。

## 复跑

从仓库根目录运行：

```sh
python3 -B docs/test-reports/host-chat-repairs/upgrade/verify_codex_upgrade.py --output /tmp/codex-upgrade-evidence.json
```

实际输出：

```text
PASS: both routes 0.1.0 -> 0.2.0; installed MCP caches expose 18 tools; conflict chain stops.
```

[验证脚本](verify_codex_upgrade.py)每次创建独立 `CODEX_HOME`，退出时删除临时市场、安装缓存和配置。新包读取当次工作区，输出同时记录 Git HEAD、ZIP SHA-256 和实际安装缓存文件摘要，避免仅凭版本号区分制品。

## 结果与证据

[本次命令输出及缓存检查](codex-upgrade-evidence.json)保存 20 次命令的参数、退出码、标准输出和错误输出，以及两次缓存 MCP 检查。`tools/list` 只保留18个工具名、数量和完整输出摘要，省略大体积参数 schema。

| 验证 | 实际结果 |
|---|---|
| 两条路线各自先安装旧包 | `plugin list --json` 确认已启用 0.1.0，来源指向各自旧市场 |
| 直接把同名市场注册到新路径，并以 `&&` 接安装 | 首条退出1，提示来源冲突；后续安装未执行，列表仍为0.1.0 |
| 换目录：`marketplace remove` → `marketplace add` → `plugin add` | 全部退出0；列表为已启用0.2.0，市场来源为新目录 |
| 原目录：备份旧目录，完整换入新版 → `plugin add` | 退出0；列表为已启用0.2.0，市场来源保持原路径 |
| 每条路线从安装结果 `installedPath` 启动真实 MCP 进程 | 退出0，`initialize` 返回0.2.0，`tools/list` 返回18个不同工具 |
| 实际安装缓存逐文件对比本次包清单 | 每条路线35个文件的SHA-256全部一致 |
| CLI帮助 | `marketplace upgrade` 明确只刷新Git市场 |

本次新市场 ZIP SHA-256：`a498d868566af20546543ad47b39e08ca0f6a96caf598baa138629b488e4adf0`。两条路线的 Codex `package-inventory.json` SHA-256 均为 `dc99bb5caf83a6608a6bcb4cf36a968c49bd8885bd19b38c316500f8dab44e11`。后续源文件变化会产生新摘要，应重新运行验证。

Claude 部分依据[官方安装管理文档](https://code.claude.com/docs/en/discover-plugins#manage-marketplaces)及[命令参考](https://code.claude.com/docs/en/plugins/cli-reference#plugin-update)，区分 `plugin update`、安装范围和移除市场会卸载全部来源插件的行为。本机没有 Claude CLI，未把官方文档核对记作实际宿主安装测试。

未调用模型、未访问用户项目、未改全局配置、未推送或发布。未验证旧会话自动刷新、真实宿主自然语言对话或其他Codex版本。证据中的临时路径已清理，不能当作仍可用的插件入口。
