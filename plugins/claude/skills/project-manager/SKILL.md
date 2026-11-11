---
name: project-manager
description: 使用本地项目管理器进行多项目规划、功能拆分、Markdown 功能台账维护、独立验收或打开功能看板时使用。
---

# 项目管理器

先阅读 [工作流程](references/workflow.md)。本插件连接本机 Python 服务，项目文件保存在用户选定的目录。

- 先用 `list_projects` 了解指定管理目录中已有的项目，再把目标项目的 `id` 作为 `project_id` 传给 `read_project`，读取其规划书与台账。
- 用户要求打开页面时调用 `open_dashboard`，使用其返回的实际 URL 打开浏览器。三项工具均使用明确的 `workspace` 路径；不要把插件安装目录当作项目目录。
- 需求分析由当前 Claude Code 会话完成。网页内的生成、建议与源码理解使用本机已登录的 Claude Code CLI；没有可用 CLI 时如实说明，仍可在当前会话分析并使用网页编辑功能表。
- MCP 暂时不可用时，可在确认 Python 可用后运行下面的备用命令。以命令返回的 JSON 中的 URL 为准，不猜端口。

```sh
python3 "${CLAUDE_PLUGIN_ROOT}/runtime/scripts/plugin_manager.py" start --workspace "/用户指定的管理目录" --agent claude --port 8765
```

路径中的占位文字须替换为本次已确认的绝对目录。`${CLAUDE_PLUGIN_ROOT}` 由 Claude Code 在读取技能时替换，不依赖终端预先设置此变量。

详细台账格式及独立审核规则见 [功能跟踪规范](../../runtime/SKILL.md)。
