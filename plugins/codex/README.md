# 项目管理器 · Codex

这是自包含的本地插件，运行需要 Python 3.9+。网页 AI 功能另需已安装并登录的 Codex CLI。

通过随附的本地市场安装后，选择“项目管理器”插件，给出要使用的绝对管理目录。插件先列出项目，再打开本地网页；项目规划和功能台账保存在该管理目录，不写入插件缓存。

Codex 的 `marketplace add` 需要市场目录，不能直接接收本单插件 ZIP。普通安装请使用同版本的 `feature-progress-tracker-marketplace.zip`，解压后注册其根目录；本单插件包也可以加入已有的本地市场。完整步骤见 [安装说明](runtime/docs/plugins.md)。

包含 `open_dashboard`、`list_projects`、`read_project` 三个 MCP 工具，以及 `project-manager` 技能。AI 提供分析和建议，确定性的表格操作、保存、台账转换和导出由程序完成。

源码与完整安装说明：[feature-progress-tracker](https://github.com/JING0c/feature-progress-tracker)。ZIP 解压目录就是插件根目录，不需要访问原作者电脑上的文件。
