# Markdown 项目管理器

在 **Codex 或 Claude Code 对话中**管理多个项目：讨论需求、参考 GitHub、编辑功能清单、采纳建议、核对源码、保存台账、更新进度和导出 Excel。AI 负责分析，代码工具负责操作，项目资料保存在 Markdown 中。

网页保留粉绿配色和大功能包含小功能的看板，仅用于查看已保存内容。新版不再提供网页聊天、创建项目或编辑保存入口。

## 开始使用

| 需要什么 | 入口 |
|---|---|
| 安装插件并在对话中使用 | [插件安装与工具说明](docs/plugins.md) |
| 看懂代码、安装包和项目资料的位置 | [项目文件说明](docs/项目文件说明.md) |
| AI 接手项目及独立审核规则 | [SKILL.md](SKILL.md) |
| 本工具自身的开发记录 | [规划书](项目规划书.md)、[功能台账](功能执行情况.md) |

安装并开启新会话后可以直接说：

> 使用 /我的目录/项目管理，新建一个图书借阅项目。先找 GitHub 参考，再和我梳理功能清单。

随后继续说“在图书管理下面增加预约功能”“采纳第2条建议并保存”“核对所选仓库源码后生成台账”“把登记图书标为待审核，证据是……”“导出这次规划的Excel”。工具会在同一对话完成操作并返回文件与实际结果，未保存预览会明确标注。

## 插件与安装包

当前源码版本 **0.2.0（宿主对话编排）**。构建不需要第三方Python依赖：

```sh
python3 scripts/build_plugins.py
```

生成完整市场 `dist/feature-progress-tracker-marketplace.zip`（推荐）及两个单插件ZIP，包含自有运行文件，不依赖源码位置。解压完整市场后按[安装说明](docs/plugins.md)注册。

[GitHub发行页](https://github.com/JING0c/feature-progress-tracker/releases)目前已发布的 `v0.1.0-preview.1` 是旧网页编排版；本轮0.2.0本地包尚未发布到GitHub，不要把旧下载包当作本轮新版。

## 数据与流程

管理目录的 `项目列表.md` 登记项目；每个项目在自己的目录保存规划书、台账、参考与操作历史。导入已有项目保留原位置和文件。新建/导入都先在宿主对话中完成有效规划，再转换和保存台账。

- `create_project` / `list_projects` / `read_project`：登记与选择项目。
- `save_plan` / `edit_features`：保存规划、结构化增删改、采用选择及多层拆分；默认编辑只预览。
- `record_suggestions` / `preview_suggestions`：记录实际分析者的建议，用户选择后预览并保存。建议默认不采纳。
- `search_references` / `select_references`：初稿参考真实GitHub README，用户多选参考，不自动采用仓库代码。
- `prepare_source_review` / `submit_source_review`：最终核对固定提交源码，当前宿主分析并提交带文件行号的报告，不运行参考代码。
- `generate_ledger` / `save_ledger`：代码转换与保存，保留已有实施和审核历史，拒绝旧版本或伪造完成。
- `update_feature_progress`：更新状态和证据；完成需真实独立审核者、评分及证据。
- `history` / `export_project`：回看保存历史，导出当前或历史版本Excel/Markdown。
- `open_dashboard` / `stop_dashboard`：按需查看或停止只读网页，不影响聊天操作。

功能编号稳定，多层父子表示包含，依赖单列。采用与完成独立，完成率只统计最细未取消项。保存有版本校验、备份和历史，跨宿主/跨管理目录操作同一项目串行；冲突时重读，不覆盖。Excel是副本，编辑后不会回写Markdown。

网页每3秒重新读取文件，支持功能清单/文档、历史与嵌套状态卡片。旧网页POST写入与AI入口返回明确的退役提示，不能继续通过缓存页面写入。

## 从源码打开只读网页

需要Python 3.9+，不需要模型CLI或登录：

```sh
python3 scripts/serve_dashboard.py --workspace "$HOME/Documents/项目管理" --port 8765
```

访问输出的实际网址。端口被占用时自动选择空闲端口，不终止其他程序。关闭当前终端服务用Ctrl+C；插件启动的服务可在聊天调用stop_dashboard。兼容单项目查看：`python3 scripts/serve_dashboard.py /项目/功能执行情况.md --port 8765`。

## 验证与边界

```sh
python3 -m unittest discover -s tests -v
node tests/test_readonly_viewer.cjs
```

旧网页聊天/写入流程的测试保留在 `tests/legacy_web/`，不代表当前版本验收。当前回归覆盖MCP双宿主协议、项目隔离、修改/建议/台账/导出闭环、版本与源码绑定、并发写保护及只读网页。

独立审核按[技能规范](SKILL.md)执行，代码不能证明审核身份本身真实，宿主不得编造。真实Claude Code安装和模型会话的验证结果以[本轮报告](docs/test-reports/2026-11-10-host-chat-orchestration.md)为准，不用协议测试代替实机验收。
