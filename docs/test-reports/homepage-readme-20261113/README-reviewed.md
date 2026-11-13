# Markdown 项目管理器

在 **Codex 或 Claude Code 对话中**完成项目规划、功能拆分、进度跟踪与验收。支持同时管理多个项目，把规划书、功能台账和操作记录保存成 Markdown，方便人和 AI 持续阅读、修改和接手。

**AI 负责分析，代码工具负责修改和保存。** 网页提供只读的项目总览、层级功能表与进度看板；项目操作在 Codex／Claude Code 对话中完成。

## 下载与安装

当前插件版本 **0.2.0**，发行标签 **v0.2.0-preview.1（预览版）**，已包含台账目标同步和功能详情去重修复。

| 安装包 | 适用场景 |
| --- | --- |
| **[双宿主完整安装包（推荐）](https://github.com/JING0c/feature-progress-tracker/releases/download/v0.2.0-preview.1/feature-progress-tracker-marketplace.zip)** | 首次安装；包含 Codex、Claude Code 插件及本地市场清单 |
| [Codex 单插件包](https://github.com/JING0c/feature-progress-tracker/releases/download/v0.2.0-preview.1/feature-progress-tracker-codex.zip) | 加入已有本地插件市场 |
| [Claude Code 单插件包](https://github.com/JING0c/feature-progress-tracker/releases/download/v0.2.0-preview.1/feature-progress-tracker-claude.zip) | 单独加载 Claude Code 插件 |

需要 **Python 3.9+** 和支持本地插件的 Codex 或 Claude Code。下载完整安装包，解压后按[安装与升级说明](https://github.com/JING0c/feature-progress-tracker/blob/v0.2.0-preview.1/docs/plugins.md)注册即可，无需自行构建或安装 Python 第三方依赖。

[发行说明](https://github.com/JING0c/feature-progress-tracker/releases/tag/v0.2.0-preview.1) · [SHA-256 校验文件](https://github.com/JING0c/feature-progress-tracker/releases/download/v0.2.0-preview.1/SHA256SUMS.txt) · [对应版本源码](https://github.com/JING0c/feature-progress-tracker/tree/v0.2.0-preview.1)

## 能做什么

| 能力 | 使用方式 |
| --- | --- |
| 多项目管理 | 新建或导入项目，各自保存规划、台账和历史；总览集中查看进度 |
| 规划与功能拆分 | 先梳理目标、范围和验收，再逐层拆成大功能、小功能和更细的功能点，记录技术与前期准备 |
| GitHub 项目参考 | 搜索相似项目，由用户多选参考；初稿参考 README，最终确认时结合固定版本源码核对 |
| 功能修改与建议采纳 | 在对话中新增、修改、拆分或调整采用范围；查看建议及差异后，按选择保存 |
| 进度与独立验收 | 记录执行者、状态、实现证据、问题和争议；完成需要另一位 Agent 独立审核、评分及证据 |
| 查看与导出 | 按需打开只读网页，查看嵌套功能和历史版本，导出 Excel 或 Markdown |

功能清单默认采用全部功能，可在对话中调整；**建议需用户选择后才采纳**。采用某项功能只表示纳入规划，不表示已经完成。

## 第一次使用

安装插件并开启新会话后，先指定一个用于保存项目资料的目录，例如：

> 用这个插件管理 /我的目录/项目管理。新建一个图书借阅项目，先搜索 GitHub 上的相似项目，再和我一起梳理功能清单。

接下来可以这样继续：

1. **确定范围：**“参考第 1、3 个项目。先做图书登记、查询和借阅，暂不做收费。”
2. **细化功能：**“在借阅管理下面增加预约功能，拆出子功能，并补充技术、准备和验收标准。”
3. **选择建议：**“让子智能体检查遗漏，展示建议。我选好后，先预览修改，再保存功能表。”
4. **保存台账：**“核对所选参考项目的源码，确认规划后生成并保存功能台账。”
5. **持续跟踪：**“打开这个项目的看板。”“登记图书已实现，记录这份证据并标为待审核。”“导出最新规划的 Excel。”

新增和采纳会先生成可检查的预览，保存后才更新项目文件。修改项目目标后，重新按规划生成并保存台账，目标也会同步；旧历史保留。

## 项目资料保存在哪里

项目资料保存在你指定的管理目录中，与插件安装目录分开。`项目列表.md` 登记项目，每个项目独立保存 `项目规划书.md`、`功能执行情况.md` 及操作和版本记录。导入项目保留已有文件位置。

**Markdown 是事实来源，Excel 是导出副本。** 可以让 AI 阅读和维护 Markdown，再通过网页查看；Excel 修改不会自动回写。聊天内容由当前宿主会话管理。

网页沿用粉绿配色，父功能包含多层子功能，以不同颜色和文字显示状态，点击可展开详情。查看服务只监听本机，按需开启；文件更新后网页自动重新读取。

## 文档与验证

| 想了解什么 | 文档 |
| --- | --- |
| 安装、升级、工具用法与常见问题 | [插件说明](https://github.com/JING0c/feature-progress-tracker/blob/v0.2.0-preview.1/docs/plugins.md) |
| 源码、安装包和项目资料的对应位置 | [项目文件说明](https://github.com/JING0c/feature-progress-tracker/blob/v0.2.0-preview.1/docs/项目文件说明.md) |
| AI 编排与独立验收规则 | [技能说明](https://github.com/JING0c/feature-progress-tracker/blob/v0.2.0-preview.1/SKILL.md) |
| 目标同步与详情去重的测试证据 | [修复复验报告](https://github.com/JING0c/feature-progress-tracker/blob/v0.2.0-preview.1/docs/test-reports/2026-11-12-goal-detail-repairs.md) |

当前为预览版。已验证两套插件包的实际工具协议、规划与台账保存、Excel 导出及只读网页；**Claude Code 的真实安装、升级和宿主内对话仍待完整验证**。独立审核只记录实际做过的检查，不用协议测试代替宿主验收。

<details>
<summary>开发者：从对应版本源码构建</summary>

请使用上方“对应版本源码”链接获取 `v0.2.0-preview.1`，进入该版本的源码目录后执行：

```sh
python3 scripts/build_plugins.py
```

生成的三份安装包位于 `dist/`，完整本地市场位于 `build/plugin-marketplace/`。源码中的 `plugins/` 是模板，安装请使用构建后的完整包。

```sh
python3 -m unittest discover -s tests -v
node tests/test_readonly_viewer.cjs
```

详细构建和使用方式见上方插件说明。

</details>
