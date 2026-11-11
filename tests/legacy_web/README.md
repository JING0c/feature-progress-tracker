# 旧网页编排测试档案

这些文件保留改为宿主对话编排前的回归资料，不属于当前版本的测试集，也不代表当前版本已验证。

当前版本已移除网页聊天、网页创建项目、网页修改/保存和后台模型调用。继续运行依赖 HTML 写入令牌、网页 POST 接口或旧聊天按钮的测试，只会验证已退役的交互约定。当前 Python 测试发现命令不会递归进入此目录（没有 `__init__.py`）；前端测试只运行 `tests/` 顶层的 `.cjs` 文件。

- 12 份 Python 文件保存了迁移前原文。顶层同名文件仍保留适用于当前版本的解析、Excel、采用规则、历史事务和源码引用纯函数测试，以及其他测试引用的夹具常量。
- 其中 `test_planning_agent.py` 整份对应已退役的后台模型适配器；其余归档内容中的旧 HTTP 集成类从当前测试集中移除。
- 9 份 `.cjs` 文件直接执行旧网页创建、聊天、编辑、保存或其退役辅助模块，原样移至此处；旧运行模块已移除，历史源码可从 Git 版本读取。
- 需要复现旧行为时，应在对应旧版本 checkout 中运行，不能修改当前只读网页以迎合这些测试。

当前入口的替代验证：

| 原保护 | 当前验证 |
|---|---|
| 项目隔离、导入不覆盖、规划门槛、保存冲突 | `../test_chat_regressions.py`、`../test_project_service.py` |
| 参考选择和源码核对失效、旧候选拒绝 | `../test_chat_regressions.py`、`../test_project_service.py` |
| 已验收记录保护及独立审核进度更新 | `../test_chat_regressions.py`、`../test_project_progress.py`、`../test_planning_operations.py` |
| 功能修改、建议采纳、保存和导出 | `../test_project_service.py`、保留的纯函数测试 |
| 新网页只读、轮询、视图和导航 | `../test_readonly_viewer.cjs`、只读 HTTP 集成测试 |
| 插件 stdio/MCP 工具与安装包 | `../test_plugin_runtime.py`、`../test_plugin_packaging.py` |

迁移不将旧模型端到端记录当作新宿主实测。当前 Claude Code 真实宿主运行仍需单独验证。
