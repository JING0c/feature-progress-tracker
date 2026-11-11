# 项目管理器 · Claude Code

这是自包含的 Claude Code 插件，运行需要 Python 3.9+。网页 AI 功能使用已安装并登录的 Claude Code CLI。

临时加载解压后的插件目录：

```sh
claude --plugin-dir "/插件解压目录"
```

在会话中运行 `/feature-progress-tracker:project-manager`，给出要使用的绝对管理目录。管理目录的 `项目列表.md` 登记项目位置；规划书和功能台账保存在各项目自己的目录，以登记路径为准，不写入插件缓存。导入项目仍在原目录。

文件用途、备份范围及三个 ZIP 的区别见[项目文件说明](runtime/docs/项目文件说明.md)，安装与切换步骤见[安装说明](runtime/docs/plugins.md)。

包含 `open_dashboard`、`list_projects`、`read_project` 三个 MCP 工具。AI 提供分析和建议，确定性的表格操作、保存、台账转换和导出由程序完成。本包不是 Claude Desktop 扩展。

源码与完整安装说明：[feature-progress-tracker](https://github.com/JING0c/feature-progress-tracker)。
