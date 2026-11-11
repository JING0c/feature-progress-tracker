# Codex 与 Claude Code 插件

插件提供“项目管理器”技能与三个本地 MCP 工具：打开管理器、列出项目、读取项目规划和台账。页面沿用现有功能清单、建议预览、保存、源码核对及看板流程，数据继续保存在用户选定目录的 Markdown 文件中。

这里的 Claude 插件面向 **Claude Code**；不是 Claude Desktop 扩展。两个插件都运行在本机，不是上传到云端后自动可用的服务。

不清楚源码、安装包和用户资料放在哪里时，先看[项目文件说明](项目文件说明.md)。管理目录保存项目登记；规划书与台账保存在各项目登记的目录，导入项目保留原位置。

## 准备

- Python 3.9 或更新版本，可通过 `python3 --version` 检查。
- 支持插件的 Codex 或 Claude Code。网页内的 AI 分析还需要对应 CLI 已安装并登录；Claude 插件不会改用 Codex 处理分析。
- 一个与插件安装目录分开的管理目录，用于存放项目登记和项目文件。插件更新不会搬动或删除这些文件。

不需要安装 Python 第三方依赖。GitHub 初稿调研需要联网，最终源码核对需要本机可用的 Git。

## 下载安装包（推荐）

直接下载[完整插件市场 ZIP](https://github.com/JING0c/feature-progress-tracker/releases/download/v0.1.0-preview.1/feature-progress-tracker-marketplace.zip)，解压后按下方各宿主的“只收到 ZIP 时”步骤安装，无需克隆源码或运行构建命令。

[v0.1.0-preview.1 发行页](https://github.com/JING0c/feature-progress-tracker/releases/tag/v0.1.0-preview.1)提供完整市场及两个单插件 ZIP、安装命令和 SHA-256。请选择命名为 `feature-progress-tracker-*.zip` 的附件；GitHub 自动生成的 `Source code` 是源码压缩包。此版本标为预览版：Codex 已实测隔离安装与 MCP 工具调用，Claude Code 真实宿主安装和模型调用尚待验证。

## 从源码构建（可选）

在本仓库根目录运行：

```sh
python3 scripts/build_plugins.py
```

生成：

```text
build/plugin-marketplace/                 可注册的本地插件市场
  .agents/plugins/marketplace.json        Codex 市场清单
  .claude-plugin/marketplace.json         Claude Code 市场清单
  plugins/codex/                          自包含 Codex 插件
  plugins/claude/                         自包含 Claude Code 插件
dist/feature-progress-tracker-codex.zip
dist/feature-progress-tracker-claude.zip
dist/feature-progress-tracker-marketplace.zip  可独立分发的完整双宿主市场
```

两个单插件 ZIP 将插件文件直接放在归档根目录，可解压到任意目录；包含运行脚本，不需要回到源码仓库读取程序。完整市场 ZIP 额外包含两个市场清单和 `plugins/codex`、`plugins/claude`，适合直接交给其他人安装。包中不包含真实项目、账号凭据、测试资料或仓库历史。`package-inventory.json` 记录包内文件的 SHA-256，用于核查制品。

`plugins/codex` 和 `plugins/claude` 是构建模板，不是直接安装目录。源码仓库的市场清单引用构建产物，必须先构建。**不要直接用 GitHub 仓库地址添加这个源码仓库作为远程市场**：Git 忽略了构建产物，远程检出后不会自动执行构建。需要分发时发送 ZIP，或发布完整的 `build/plugin-marketplace` 目录。

## 在 Codex 安装

在仓库根目录注册已构建的本地市场：

```sh
codex plugin marketplace add "$PWD/build/plugin-marketplace"
codex plugin add feature-progress-tracker@jing0c-project-tools
```

如果当前 Codex 版本只支持注册市场，注册后重启桌面应用，在插件目录中选择 `jing0c-project-tools` 并安装“项目管理器”。以本机 `codex plugin --help` 提供的命令为准。

安装后开启新的会话，选择项目管理器插件并说：

> 打开项目管理器，使用 /绝对路径/项目管理 作为管理目录，先列出已有项目。

插件会使用 `open_dashboard` 返回的实际网址。从项目管理器开始新建或导入项目，然后完成规划书、编辑功能表、确认并保存到看板。不要将规划保存在插件缓存中。

**只收到 ZIP 时**：使用 `feature-progress-tracker-marketplace.zip`，解压到例如 `/绝对路径/feature-progress-tracker-marketplace`，然后执行：

```sh
codex plugin marketplace add "/绝对路径/feature-progress-tracker-marketplace"
codex plugin add feature-progress-tracker@jing0c-project-tools
```

这个解压目录必须直接包含 `.agents/plugins/marketplace.json`。单独的 `feature-progress-tracker-codex.zip` 是插件包，不能直接传给 `marketplace add`；它适合加入已有本地市场，普通安装请使用完整市场 ZIP。

## 在 Claude Code 安装

可以先临时加载，验证后再安装：

```sh
claude plugin validate ./build/plugin-marketplace/plugins/claude
claude --plugin-dir "$PWD/build/plugin-marketplace/plugins/claude"
```

在 Claude Code 会话中使用 `/feature-progress-tracker:project-manager`，说明要打开的管理目录。正式安装可在仓库根目录执行：

```sh
claude plugin marketplace add "$PWD/build/plugin-marketplace"
claude plugin install feature-progress-tracker@jing0c-project-tools
```

只收到单插件 ZIP 时，先解压到独立目录，再把该目录传给 `claude --plugin-dir`。收到完整市场 ZIP 时，解压后把市场根目录传给 `claude plugin marketplace add`，再执行同名插件的安装命令。不要把 ZIP 文件本身作为插件目录。

## 工具与分析的分工

| 工具 | 参数 | 行为 |
|---|---|---|
| `open_dashboard` | `workspace`（绝对目录） | 启动或复用本机服务，返回真实 URL |
| `list_projects` | `workspace` | 读取管理目录中登记的项目 |
| `read_project` | `workspace`、`project_id` | 读取所选项目的规划书和台账 |

MCP 不直接采纳建议或重写功能表。当前宿主会话可以分析项目资料；网页中的 AI 按插件选择调用对应的本机 CLI。表格增删改、建议合并、台账转换、保存和导出由现有代码执行，保存前仍需用户审阅。

## 切换宿主与停止服务

同一个管理目录只运行一个可写的插件服务。Codex 已打开该目录时，Claude Code 不会静默复用 Codex 的 AI，也不会另开一个同时写入的服务。确定要切换后，先保存网页中的修改，再在独立终端停止当前宿主的服务，例如从 Codex 切换到 Claude Code：

```sh
python3 "/已安装插件/runtime/scripts/plugin_manager.py" stop --workspace "/绝对路径/项目管理" --agent codex
```

再在 Claude Code 中调用 `open_dashboard` 打开同一个管理目录。命令中的插件路径使用实际解压/安装位置；源码用户也可使用 `python3 scripts/plugin_manager.py`。`stop` 只停止身份核验通过的本插件服务，不会按端口杀死其他程序。升级后提示旧运行版本时，按同样方式先停止旧服务，再重新打开。

只关闭浏览器不会停止服务。需要结束时使用上述 `stop` 命令；Markdown 项目文件继续保留。

## 排查与更新

- 工具未出现：确认安装的是 `build/plugin-marketplace/plugins/...` 中的成品，重启宿主或开启新会话，查看宿主的插件/MCP 错误；不要把源码模板安装进去。
- `python3` 找不到：安装 Python，并确保从桌面应用启动时同样可访问。插件不会自动安装依赖。
- 网页 AI 报 CLI 不可用或未登录：在终端检查 `codex --version` 或 `claude --version`，按对应工具的正常方式完成登录。文件读取和手动编辑不等于 AI 分析已可用。
- Claude Code 提示阻止嵌套会话：先停止当前管理器，再从独立终端运行 `python3 "/已安装插件/runtime/scripts/plugin_manager.py" start --workspace "/绝对路径/项目管理" --agent claude`。网页会明确报告分析失败，不会假装已经生成建议。
- 端口被占用：使用 `open_dashboard` 返回的地址，不关闭其他服务，也不要假定一定是 8765。
- 修改运行代码后：重新执行构建，按宿主流程刷新或重装插件；缓存中的旧版本不会因改了源文件自动更新。发布新版本时同步两个宿主的 manifest 版本。
- 卸载：使用宿主插件管理界面；项目 Markdown 保存在各项目登记的目录，与插件缓存分开。卸载不代表删除项目。

包级校验使用 `python3 -m unittest discover -s tests -p 'test_plugin_packaging.py' -v`。真实宿主安装、MCP 调用和对应 CLI 的实际 AI 回复是另外的检查；包级测试通过不能代替这些验证。

## 格式依据

- [OpenAI 插件包与本地市场](https://developers.openai.com/plugins/build/plugins)：Codex 提供 portable `plugin.json`、`mcp.json`，并保留 `.codex-plugin/plugin.json` 和 `.mcp.json` 兼容配置。
- [Claude Code 插件清单](https://code.claude.com/docs/en/plugins-reference)：使用 `.claude-plugin/plugin.json`、`.mcp.json`、`skills/` 及 `${CLAUDE_PLUGIN_ROOT}`。
- [Claude Code 本地市场](https://code.claude.com/docs/en/plugin-marketplaces)：构建目录包含 `.claude-plugin/marketplace.json` 和可安装的插件内容。
