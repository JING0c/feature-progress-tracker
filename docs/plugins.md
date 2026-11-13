# Codex 与 Claude Code 插件

0.2.0 将全部项目编排迁到宿主对话。分析使用当前 Codex 或 Claude Code 会话；插件只运行本机Python代码工具。网页只读，不再从网页启动模型CLI。

## 准备

- Python 3.9+，无需Python第三方依赖。
- 支持本地插件的Codex或Claude Code，按宿主自己的登录方式使用当前对话；插件不会另起模型进程或要求二次CLI登录。
- 用户自己的管理目录，与插件安装缓存分开。
- GitHub调研需要联网；准备参考源码时需要Git。

## 安装包与构建

当前成品版本0.2.0，下载发行标签为[v0.2.0-preview.1](https://github.com/JING0c/feature-progress-tracker/releases/tag/v0.2.0-preview.1)，包含台账目标同步和功能详情去重修复。直接下载安装包即可，无需自己构建：

- [双宿主完整市场包（推荐首次安装）](https://github.com/JING0c/feature-progress-tracker/releases/download/v0.2.0-preview.1/feature-progress-tracker-marketplace.zip)
- [Codex 单插件包](https://github.com/JING0c/feature-progress-tracker/releases/download/v0.2.0-preview.1/feature-progress-tracker-codex.zip)
- [Claude Code 单插件包](https://github.com/JING0c/feature-progress-tracker/releases/download/v0.2.0-preview.1/feature-progress-tracker-claude.zip)
- [SHA-256 校验文件](https://github.com/JING0c/feature-progress-tracker/releases/download/v0.2.0-preview.1/SHA256SUMS.txt)

旧[v0.1.0-preview.1](https://github.com/JING0c/feature-progress-tracker/releases/tag/v0.1.0-preview.1)保留为历史网页编排版。当前仍为预览版，实际验证和未验证范围见下文。若需要自行构建，运行：

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

首次安装时解压完整市场包，将下面路径替换成直接包含`.agents`、`.claude-plugin`和`plugins`的目录。源码构建时可使用`$PWD/build/plugin-marketplace`。已安装旧版请使用下一节的升级步骤。

```sh
codex plugin marketplace add "/绝对路径/feature-progress-tracker-marketplace" &&
codex plugin add feature-progress-tracker@jing0c-project-tools &&
codex plugin list --json
```

`&&` 表示前一步成功才执行下一步。任何一步报错都先停止处理；最后核对 `installed` 中该插件的 `version` 为 `0.2.0`。

若宿主版本只支持注册市场，重启桌面后在插件目录选择该市场安装。以本机`codex plugin --help`为准。独立Codex ZIP适用于加入已有本地市场，不能把单插件根目录误当市场。

## 在 Codex 升级到 0.2.0

以下两条路线针对本地完整市场包，已在 Codex CLI `0.166.0-alpha.6` 用隔离配置从 `0.1.0` 实测。先运行 `codex plugin marketplace list --json` 查看 `jing0c-project-tools` 当前注册的目录，再选择一条路线。项目管理目录应继续放在插件目录之外。

**保留原目录：**将旧市场目录移到备份位置，把新版完整市场重新解压到原来的绝对路径，确认其中直接包含 `.agents`、`.claude-plugin` 和 `plugins`。完整替换目录可避免仅覆盖文件留下旧内容；随后执行：

```sh
codex plugin add feature-progress-tracker@jing0c-project-tools &&
codex plugin list --json
```

**换到新目录：**先把新版完整市场解压到新位置，再移除旧市场注册并注册新位置：

```sh
codex plugin marketplace remove jing0c-project-tools &&
codex plugin marketplace add "/新的绝对路径/feature-progress-tracker-marketplace" &&
codex plugin add feature-progress-tracker@jing0c-project-tools &&
codex plugin list --json
```

同名市场已指向另一目录时，直接 `marketplace add` 会报错；此时继续安装可能仍安装旧目录里的 `0.1.0`。保留上面的 `&&`，报错后停止，不要跳过错误继续安装。当前 Codex 的 `marketplace upgrade` 只刷新 Git 市场，不负责替换本地 ZIP 内容。

两条路线最后都要检查 `plugin list --json` 的 `installed`：`pluginId` 为 `feature-progress-tracker@jing0c-project-tools`、`version` 为 `0.2.0`、`enabled` 为 `true`，且 `marketplaceSource.source` 指向本次选择的市场目录。只看到安装命令成功，或只看到 ZIP 内版本正确，都不能证明已升级。核对通过后开启新会话；如旧查看服务仍在运行，按[切换宿主与停止服务](#切换宿主与停止服务)重启查看服务。

## 在 Claude Code 安装

```sh
claude plugin marketplace add "/绝对路径/feature-progress-tracker-marketplace" &&
claude plugin install feature-progress-tracker@jing0c-project-tools &&
claude plugin list
```

也可以将单Claude ZIP解压后临时加载：

```sh
claude --plugin-dir "/绝对路径/feature-progress-tracker-claude"
```

这里面向Claude Code，不是Claude Desktop扩展。目前已验证两套解压安装包的实际 MCP 协议与本地工具流程；本机未安装 Claude CLI，Claude 的安装、升级及安装后对话全流程均未实测。

Claude 已安装用户可先用 `claude plugin marketplace list` 查看原目录，用 `claude plugin list` 记录原安装范围（Scope），完整替换原目录的市场包后更新插件。下例对应本页默认的用户范围；若原来是 `project` 或 `local`，在原项目目录中把 `--scope user` 改为实际范围：

```sh
claude plugin marketplace update jing0c-project-tools &&
claude plugin update feature-progress-tracker@jing0c-project-tools --scope user &&
claude plugin list
```

核对该插件的 Version 为 `0.2.0`、Scope 与原安装一致、Status 为启用后，再开启新会话。Claude 使用 `plugin update` 更新已安装插件，不能套用 Codex 的 `plugin add`。如果必须换市场路径，先记录该市场全部已安装插件及范围，再按官方说明移除市场、添加新路径并逐一重装：Claude 的 `marketplace remove` 会卸载该市场所有插件并移除它们的启用设置。命令与行为依据 [Claude 官方安装管理文档](https://code.claude.com/docs/en/discover-plugins#manage-marketplaces)及[命令参考](https://code.claude.com/docs/en/plugins/cli-reference#plugin-update)，以本机 `claude plugin --help` 支持的选项为准。

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

按规划生成台账时，项目目标也会同步到候选；后续修改规划目标后，重新生成并保存即可更新台账，预览不会提前写文件。其他头部信息和已有实施、审核历史保留；无法识别规划目标时保留原目标，不自动编造。功能清单的采用、技术、准备和备注分别展示，未知列继续保留为补充信息；网页和 Excel 使用相同的字段转换。

## 切换宿主与停止服务

两个宿主使用同一管理目录和相同Markdown。写工具共享workspace及项目锁，不需另开网页；同版本查看服务可共用。升级后旧查看服务不会偷偷热换代码，提示后在对话调用`stop_dashboard`再`open_dashboard`即可。

也可在终端停止已核验的插件服务（agent取实际启动者）：

```sh
python3 "/已安装插件/runtime/scripts/plugin_manager.py" stop --workspace "/绝对路径/项目管理" --agent codex
```

关闭浏览器不会停止后台查看服务，停止服务不删除项目文件，也不影响无需网页的聊天操作。不要按端口猜测并终止其他进程。

## 排查

- 工具仍只有打开/列表/读取：可能仍加载旧0.1.0；按本页升级步骤核对实际安装版本，再开启新会话。
- 工具未出现：确认安装成品而非源码模板，检查宿主MCP日志；不要改全局权限绕过错误。
- 版本冲突：重新读取项目，比较差异再操作，不重试旧内容强写。
- 源码核对失效：重新准备与分析，不能手改核对文件冒充有效结果。
- 提示记录保存失败：主操作结果与记录分别说明；保留现有文件并检查错误。
- 项目完成不能直接勾选：需要真实独立审核者、80分以上及验收证据；缺失保持待审核。

程序源码、管理目录和项目数据的对应位置见[项目文件说明](项目文件说明.md)。
