# 宿主对话六项缺陷修复与对抗性复核

日期：2026-11-10。对应失败基线：[上轮复核](2026-11-10-host-chat-recheck.md)。用户要求先修前三项，再修完六项并重新进行对抗性复核。

最终结论：**R1–R6 均已修复并通过本轮独立对抗性复核，未发现新的可复现阻断问题。** 真实Claude Code宿主安装仍未验证，F11-01整体继续待审核；不把该旧限制当成已经完成。

## 修补范围

| 问题 | 修补 | 回归证据 |
|---|---|---|
| R1 历史指数膨胀 | 两类新快照都排除历史容器；原有档案及实施、审核证据原样保留 | `test_history_growth.py` 3项；公开MCP连续8轮保存，原第6轮2,503,357字符降为3,289字符，第8轮4,311字符 |
| R2 旧验收新标记完成 | 完成前对照当前采用子树及实质要求，写入前再次核对规划版本；备注、优先级及其他分支变化不阻断该功能 | `test_completion_plan_binding.py` 5项；旧验收/未采用/移除/新增子项/过程中外部修改拒绝写入，同步后可完成 |
| R3 父子重复计数 | 同一分组先读完整记录，再按编号建立父子关系，不依赖文件行序 | `test_hierarchy_order.py` 7项，含120种深层排列；实际采用→取消→恢复总数1→1→1，历史保留 |
| R4 待审核被替换 | 撤销旧审核后保留本次明确提交的合法状态；只改实施证据仍默认重开进行中 | `test_progress_requested_state.py` 4项；五种非完成状态、父项重开及公开MCP回读 |
| R5 依赖残留N编号 | 合并后对新旧行统一映射，再校验依赖；正式保存与台账转换拒绝未解析编号 | `test_feature_dependency_merge.py` 7项；前向/深层/中文相邻引用、无效引用、真实保存回读 |
| R6 旧市场升级不生效 | 补充原路径和换路径升级、失败即停及实际安装版本检查；区分Claude自身命令 | [隔离升级验证](host-chat-repairs/upgrade/README.md)，两个路线均0.1.0→0.2.0，实际安装缓存18工具 |

R1–R3 首批提交 `df53ec6`；R4–R5 提交 `12fc75c`；R6 文档与隔离验证提交 `f5eef1d`。各新增业务回归先确认原实现失败，再修改实现并运行转绿。一个旧测试原先要求新快照嵌套进度历史，改为只核对业务字段，仍断言实时记录保留全部旧进度历史。

## 根 Agent 验证

- `python3 -B -m unittest discover -s tests -p 'test_*.py'`：187项通过，16.273秒。
- 使用 `/Applications/ChatGPT.app/Contents/Resources/cua_node/bin/node` 运行全部7份顶层CJS：采用统计、看板轮询、Markdown、活动记录、历史竞态、规划表视图、只读查看器全部通过。
- `python3 -B scripts/build_plugins.py`：三个0.2.0 ZIP重建成功，业务代码不调用模型处理确定性操作。
- 全部业务测试写入独立临时目录，没有修改用户项目；本轮不推送GitHub、不发布Release、不改用户全局插件配置。

## 独立对抗性复核

三位未参与相应实现的审核者分别核对业务与制品，所有测试数据位于独立临时目录。

| 审核者 | 独立范围 | 评分（功能/正确性/证据/维护） | 结论 |
|---|---|---|---|
| `/root/adversarial_history_acceptance` | R1/R2 历史、当前验收与采用 | 97（40/29/19/9） | 通过 |
| `/root/adversarial_hierarchy_changes` | R3/R4/R5 层级、状态及依赖 | 98（40/30/18/10） | 通过 |
| `/root/adversarial_upgrade_packages` | R6 实际升级与最终ZIP运行 | 94（38/30/16/10） | R6及制品通过，真实Claude宿主未验收 |

第一位审核者通过公开 MCP 交替修改父子实施、审核与验收24轮，全部保存成功；文件从1,112字节增至93,799字节，第二轮后每轮增加约3,865–3,872字节。旧嵌套历史经12轮仍精确保留。验收、说明、依赖、技术、准备五类变化均拒绝旧完成，失败时台账字节不变；采用取消/恢复、父子整体恢复和新增子项也守住审核边界。独立7组组合场景及8项已有定向测试通过；把同一脚本跑到旧版ec3157a，6组失败、1组通过。

第二位审核者独立13项通过，完整走过多层新增→记录建议→选择预览→保存规划→生成并保存台账→进度更新；覆盖四层倒序、多次取消/重新采用、五种非完成状态、多个N前向引用、中文相邻引用、旧编号保留、过期候选和历史篡改拒绝。基线ec3157a的三个核心反例分别重现原错误。根 Agent 将两份脚本归档后再次运行，7组和13项均通过。

两位审核时HEAD为f5eef1d，其业务代码与12fc75c相同。没有新增可复现阻断问题；F12-01、F12-03据此恢复验收，原失败证据保留。评分扣分主要来自未做超大历史、长期并发、真实宿主/浏览器实测及跨模块保护的维护成本。

第三位审核者直接取当前dist中的待交付ZIP，在独立Codex配置中复跑两条升级路线，安装缓存的完整文件集合及35个文件摘要与包一致，实际MCP返回0.2.0、18工具。同名市场路径冲突时，真实shell的`&&`阻止后续安装。三个ZIP与临时重建制品逐字节相同。

两种单插件在源码目录外、去除PYTHONPATH/PYTHONHOME的环境中分别完成新建、规划、新增、建议采纳预览/保存、空参考源码绑定、台账生成/保存、状态、历史和Excel全流程：共56次JSON-RPC请求、16种工具、30次HTTP检查。实际只读看板数据包含新增功能及新验收；旧聊天和写入POST返回410，前后Markdown摘要不变；MCP与HTTP导出的Excel结构和预期内容通过。测试服务均已停止。该证据是两个实际安装包的运行证据，不冒充真实Claude Code宿主或模型对话。

- [R1/R2独立脚本](host-chat-repairs/history_acceptance_audit.py)、[结构化证据](host-chat-repairs/history-acceptance.json)、[旧版负对照](host-chat-repairs/history-acceptance-baseline.log)
- [R3/R4/R5独立脚本](host-chat-repairs/adversarial_r345_review.py)、[当前输出](host-chat-repairs/r345-current.log)、[旧版负对照](host-chat-repairs/r345-baseline.log)
- [重建安装包摘要](host-chat-repairs/artifacts.json)
- [最终制品独立报告](host-chat-repairs/packages/REVIEW.md)、[实际升级输出](host-chat-repairs/packages/upgrade-evidence.json)、[协议与HTTP证据](host-chat-repairs/packages/stdio-final-evidence.json)

在仓库根目录可重跑：

```sh
python3 -B docs/test-reports/host-chat-repairs/history_acceptance_audit.py
python3 -B docs/test-reports/host-chat-repairs/adversarial_r345_review.py
```

脚本只使用各自临时项目。R1/R2脚本保留并打印其证据目录；审核字段均为明确测试夹具。已验收树新增子项时仍要求先撤销旧验收，不能通过转换候选改写已验收树的历史。

`packages/`中的制品审核脚本按原样归档，内含当次源目录和临时构建路径；它们是历史证据，复跑前应按其报告准备新的隔离目录及调整路径，不能直接把仓库文档目录当测试工作区。

## 限制

已有嵌套档案保留原始内容，本次防止后续递归复制，没有自动压缩旧文件；已超过文档大小上限的历史文件不在此次自动修复范围。真实Claude Code宿主安装仍需具备该CLI的环境验证；双包stdio协议测试不等同于真实Claude对话。测试中的实施者与审核字段为显式夹具，不是对测试项目实际业务实现的验收。
