---
name: project-manager
description: 在当前对话中管理多个项目、规划功能、增删改功能表、采纳建议、核对源码、保存台账、更新进度、独立审核或导出Excel时使用。
---

# 项目管理器

先读[完整工作流程](references/workflow.md)。所有项目编排都在当前 Claude Code 对话完成；网页只是可选的只读查看器，无需到网页聊天或点击保存。

- `list_projects` / `create_project` 选择或新建导入项目，`read_project` 读取当前资料与版本。必须明确workspace和project_id，不扫描无关项目。
- 分析使用当前会话，必要时使用真实子智能体；`search_references`提供GitHub参考、`prepare_source_review`提供源码证据，不启动后台大模型。
- `save_plan`、`edit_features`、`record_suggestions`、`preview_suggestions`、`submit_source_review`、`generate_ledger`、`save_ledger`、`update_feature_progress`由代码执行操作并保留历史。未保存预览要明确，版本冲突先读取再处理。
- `history`回看记录，`export_project`直接导出Excel/Markdown并给用户文件路径。`open_dashboard`只在用户想看网页时调用，`stop_dashboard`结束本插件只读服务。
- 完成勾选必须真实独立审核通过，不能用建议或源码核对冒充验收。
- 工具未出现时说明需更新插件并开启新会话，不建议绕过版本校验直接重写文件。不要为处理失败修改全局配置。

详细台账与验收规则见[功能跟踪规范](../../runtime/SKILL.md)。
