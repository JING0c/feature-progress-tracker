# 0.2.0 发布包独立审核

审核 Agent：`/root/release_package_review`。本报告针对待上传的三份本地 ZIP，不代替远端上传、Release 可下载性或宿主安装结果。

**结论：通过，96/100（40/29/18/9）。** 被测文档提交为 `7df8203`，产品修复来自 `d335776`。最终结果在 `final-audit.json`，初步 `preliminary.json` 是更新下载文档前的旧包记录，不能作为本次上传哈希。

## 实际执行

1. 对最终 Codex、Claude、完整市场三 ZIP 检查 CRC、重复成员、路径越界、符号链接、文件清单及 SHA-256。两个单包逐文件与 package-inventory.json 一致；运行代码、技能和文档与本地源文件逐字节一致。完整市场中的两个插件与单包逐字节一致，两个市场清单均解析到完整插件。
2. 包路径没有项目、规划历史、导出、测试、Git、缓存目录，也没有项目台账、规划书、项目列表、`.env`、私钥/证书、Python缓存。运行时所有文件均核对为仓库源文件；未复制用户测试数据。
3. 独立输出目录重新构建三 ZIP，与根 Agent 拟上传的三文件 SHA 全部相同，见 `reproducible.json`。
4. `python3 -B -m unittest discover -s tests -p test_plugin_packaging.py -v`：11 项全部通过，包含解压双宿主完整代码工具流程和只读网页服务启动/停止。日志完整保留。
5. 自写独立脚本用最终 ZIP 的 `.mcp.json` 实际启动 Python 进程，清空 PATH 以排除调用模型/Git，两个宿主各 8 次、共 16 次 tools/call；每次初始化返回 0.2.0，工具清单 18 项，所有进度单调至 100%，进程退出 0、stderr 为空。原始请求/应答保存在 `stdio-raw.jsonl`。
6. 每个隔离项目均实际完成新建→读当前版本→保存规划→生成候选→确认未提前写入→保存台账→读回→导出 Excel。目标保存正确；Excel 技术/准备独立，功能介绍没有再次包含这两个结构字段，真实备注和未知责任组保留。

以上测试不修改仓库产品文件、不推送、不发布；所有测试数据保存在本报告临时目录或 unittest 自行清理的临时目录。独立脚本不启动后台服务，打包测试内部服务已按测试收尾停止。

## 最终 SHA-256

- Codex：`a3f3547a034d4b05e769f9da14da82ab1c22750c0a172345e3bc5676533900a4`
- Claude Code：`cac96d0b7275ceb299fe1fa126c7ff4bd69680eed83194d14fd81a86b7e1765a`
- 完整市场：`cbc268a87ff7ec934d29f08a839b0860bcbae2a32a6544aa70735656b1a0ecb2`

## 评分与限制

- 功能/验收 40/40：发布物契约、实际解压启动、目标同步与字段导出均直接验证。
- 正确性/边界 29/30：清单、路径、符号链接、缺文件、拒绝覆盖无关目录均有检查；未穷举所有操作系统文件权限和解压器。
- 验证证据 18/20：可复现构建、日志、协议原始帧齐全；本 Agent 没有真实 Codex/Claude 宿主安装、真实模型会话、原生 Excel 和远端 Release 下载验证。
- 可维护性 9/10：无新增产品复杂性，复用已有构建器，独立脚本审计真实 ZIP；仓库既有构建/宿主包装仍需保持版本与文档同步。

发布需使用新的 `v0.2.0-preview.1`，保留旧版 `v0.1.0-preview.1`；两版交互模式不同，不能仅覆盖旧包而误导用户。新版下载文档已明确对话编排与只读网页，内部插件版本为规范的 `0.2.0`。

本报告只确认本地待发布 ZIP，不声称已上传。由根 Agent 核对远端目标提交及三个附件下载后再报告发布完成。


## 发布后的独立远端复核（最终结论）

通过公开 GitHub API 及标签网页，只读核对已发布的 [v0.2.0-preview.1](https://github.com/JING0c/feature-progress-tracker/releases/tag/v0.2.0-preview.1)：

- Release `draft=false`、`prerelease=true`，标签名正确。
- 解析 annotated tag 对象 `403c24140e4f9ff802d8a89cd89aa7a0b07e99a7`，其实际 commit 为 `7df820349f43c3a48fa0c9ab6d1e3eecbe482394`；不是仅相信 release.target_commitish 文本。
- 附件恰好四份，均为 `uploaded`：Codex ZIP 130942 字节、Claude ZIP 129591 字节、完整市场 ZIP 263502 字节、SHA256SUMS.txt 310 字节。每个附件的 API SHA-256 digest 和 size 都与本地待发布文件一致。
- 标签下 README.md 与 docs/plugins.md 的内容均与本地文件逐字节相同，两个 GitHub blob 网页均实际 HTTP 200，安装说明中包含本次版本下载链接。
- 原始公开响应和断言结果见 `remote-release.json`、`remote-tag-ref.json`、`remote-review.json`、`remote-doc-links.json`。

**最终发布审核通过，97/100（40/29/19/9）**，取代前述仅本地阶段的 96 分。新增了远端标签、附件摘要和安装说明的独立证据，验证证据项由 18 调整为 19。其余评分理由不变。

本 Agent 没有重复下载附件正文；实际下载字节核对由根 Agent 另行执行。本结论明确区分 GitHub API 的附件摘要匹配与独立下载匹配。真实宿主安装、模型会话和原生 Excel 仍不在本轮发布审核范围内。
