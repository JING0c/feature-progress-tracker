# Codex 与 Claude Code 插件

0.2.0 将全部项目编排迁到宿主对话。分析使用当前 Codex 或 Claude Code 会话；插件只运行本机Python代码工具。网页只读，不再从网页启动模型CLI。

## 准备

- Python 3.9+，无需Python第三方依赖。
- 支持本地插件的Codex或Claude Code，按宿主自己的登录方式使用当前对话；插件不会另起模型进程或要求二次CLI登录。
- 用户自己的管理目录，与插件安装缓存分开。
- GitHub调研需要联网；准备参考源码时需要Git。

## 安装包与构建

当前本地成品版本0.2.0。此前发布的[v0.1.0-preview.1](https://github.com/JING0c/feature-progress-tracker/releases/tag/v0.1.0-preview.1)是旧网页编排版，不包含本次改动。新版源码可运行：

```sh
python3 scripts/build_plugins.py
```

生成：

```text
build/plugin-marketplace/                 可安装的完整本地市场
  .agents/plugins/marketplace.json        Codex市场清单
  .claude-plugin/marketplace.json         Claude Code市场清单
  plugins/codex/                          Codex完整插件
  plugins/claude/                         Claude Code完整插件
dist/feature-progress-tracker-marketplace.zip  完整双宿主市场（推荐）
dist/feature-progress-tracker-codex.zip        单Codex插件
dist/feature-progress-tracker-claude.zip       单Claude Code插件
```

ZIP包含运行代码、技能和文件说明，不包含用户项目、密钥或测试数据；package-inventory.json列出每个文件的SHA-256。源码中的plugins目录只是模板，不能直接当成品安装，也不能把源码GitHub地址注册为市场后期待自动构建。

## 在 Codex 安装

解压完整市场包，将下面路径替换成直接包含`.agents`、`.claude-plugin`和`plugins`的目录。源码构建时可使用`$PWD/build/plugin-marketplace`：

```sh
codex plugin marketplace add "/绝对路径/feature-progress-tracker-marketplace"
codex plugin add feature-progress-tracker@jing0c-project-tools
```

若宿主版本只支持注册市场，重启桌面后在插件目录选择该市场安装。以本机`codex plugin --help`为准。独立Codex ZIP适用于加入已有本地市场，不能把单插件根目录误当市场。

## 在 Claude Code 安装

```sh
claude plugin marketplace add "/绝对路径/feature-progress-tracker-marketplace"
claude plugin install feature-progress-tracker@jing0c-project-tools
```

也可以将单Claude ZIP解压后临时加载：

```sh
claude --plugin-dir "/绝对路径/feature-progress-tracker-claude"
```

这里面向Claude Code，不是Claude Desktop扩展。目前已验证两套解压安装包的实际 MCP 协议与本地工具流程；尚未在真实 Claude Code 安装后的对话内完成全流程。

## 在对话中使用

安装后开启新会话并选择插件，直接说：“用 /绝对路径/项目管理 管理项目，先列出已有项目”。无需打开网页才能创建或操作。

| 任务 | 工具 |
|---|---|
| 列表、新建/导入、读取 | list_projects、create_project、read_project |
| 初始规划保存、增删改与采用 | save_plan、edit_features |
| 记录实际分析者建议、预览用户选择 | record_suggestions、preview_suggestions |
| 搜索GitHub与确认多选参考 | search_references、select_references |
| 准备固定源码、提交宿主分析 | prepare_source_review、submit_source_review |
| 生成候选、保存功能台账 | generate_ledger、save_ledger |
| 状态、实施证据和独立审核 | update_feature_progress |
| 操作记录、历史功能表、Excel/Markdown导出 | history、export_project |
| 可选只读网页、结束查看服务 | open_dashboard、stop_dashboard |

每个操作显式指定workspace，涉及项目的操作再指定project_id。修改使用最近读取的revision。新增功能采用临时N编号由代码分配稳定编号，编辑/采纳默认仅预览，保存后才更新文件；用户已经明确确认的修改可以连续执行，不增加重复确认。建议预览携带suggestion_id，防止同一规划重新分析后选错建议。

初稿参考README；最终核对由工具克隆/读取固定源码，再由当前会话分析实际节选并提交report。无证据如实写未找到，不能执行参考代码或把核对当实现验收。台账候选绑定规划、参考和源码报告，过期必须重新生成。

导出返回项目`exports/`中的完整文件路径，给用户可点击文件链接；Excel修改不回写。操作记录保留实际差异、失败及未保存状态。完整聊天属于宿主会话，不写入浏览器存储。

## 切换宿主与停止服务

两个宿主使用同一管理目录和相同Markdown。写工具共享workspace及项目锁，不需另开网页；同版本查看服务可共用。升级后旧查看服务不会偷偷热换代码，提示后在对话调用`stop_dashboard`再`open_dashboard`即可。

也可在终端停止已核验的插件服务（agent取实际启动者）：

```sh
python3 "/已安装插件/runtime/scripts/plugin_manager.py" stop --workspace "/绝对路径/项目管理" --agent codex
```

关闭浏览器不会停止后台查看服务，停止服务不删除项目文件，也不影响无需网页的聊天操作。不要按端口猜测并终止其他进程。

## 排查

- 工具仍只有打开/列表/读取：安装的是旧0.1.0，需更新0.2.0包并开启新会话。
- 工具未出现：确认安装成品而非源码模板，检查宿主MCP日志；不要改全局权限绕过错误。
- 版本冲突：重新读取项目，比较差异再操作，不重试旧内容强写。
- 源码核对失效：重新准备与分析，不能手改核对文件冒充有效结果。
- 提示记录保存失败：主操作结果与记录分别说明；保留现有文件并检查错误。
- 项目完成不能直接勾选：需要真实独立审核者、80分以上及验收证据；缺失保持待审核。

程序源码、管理目录和项目数据的对应位置见[项目文件说明](项目文件说明.md)。
