# 插件安装包发布验证

日期：2026-11-10。需求：上传已构建的 ZIP 到 GitHub，供用户下载后直接安装。

- [GitHub Release：v0.1.0-preview.1](https://github.com/JING0c/feature-progress-tracker/releases/tag/v0.1.0-preview.1)，标为预览版。
- 制品源码与标签提交：`d261fda608e42ef30904218c39bf72c107411616`。
- 推荐首次安装下载 `feature-progress-tracker-marketplace.zip`，包含两宿主插件及市场清单。
- 原打包与宿主验证见[插件报告](2026-11-10-dual-host-plugins.md)和[项目文件说明报告](2026-11-10-project-files-docs.md)。

## 实际检查

通过 GitHub 网页上传三个 ZIP，并观察正式发行页显示全部附件。公开 API 可读发行版与附件；从正式下载地址重新下载到系统临时目录，对比本地文件 SHA-256，并逐个运行 ZIP CRC 检查，全部一致。

| 文件 | 字节数 | SHA-256 |
|---|---:|---|
| feature-progress-tracker-codex.zip | 156903 | `54849a5e64356ac0b123801a9e58a3ef2e3e23d1b75d659caebbb838fbc1bd2d` |
| feature-progress-tracker-claude.zip | 155465 | `f22073310dd70c94c76c0c7a3eb044d3a11a6cd44d882f2d14de0b334ec846bb` |
| feature-progress-tracker-marketplace.zip | 315511 | `64b54bd0df0c92c1cc391c35a4714b6071066a254e8668076965a7df880ed440` |

GitHub 网页最初创建的 `v0.1.0` 标签误指旧 main。核对后新建固定提交的 `v0.1.0-preview.1` 标签，并将同一发行版改绑到新标签，附件保持原始字节。最终以本报告的预览版地址下载；没有强制移动或删除旧 Git 标签。

本次发布后的 README 和安装说明新增直接下载入口，属于后续文档提交；已发布 ZIP 保持与 d261fda 对应，不悄悄重建替换。

## 独立发布审核

审核 Agent：`/root/release_zip_check`；结论：本轮发布通过，98/100（功能40、边界30、证据19、维护9）。

独立核对公开发行版非草稿且为预览版，Release ID为441192358；公共Git ref API与`git ls-remote`均确认标签指向d261fda。三个附件名、字节数、API提供的digest与本地一致；发行说明中的两个固定标签文档链接均返回HTTP200。发布前还独立核对ZIP全部inventory SHA及包内文件与d261fda一致。审核者没有重新下载安装或执行真实Claude，下载内容比对由实施者独立完成后记录在上节。

GitHub的Release元数据`target_commitish`仍显示main；已存在标签的实际提交以Git ref为准，已独立验证，无需改写标签历史。

## 验证边界

本轮没有更改程序或执行新的模型分析。下载完整性不代表所有宿主功能均已验收；Claude Code 真实安装和模型调用继续待验证，原台账39/43及未完成项保持。
