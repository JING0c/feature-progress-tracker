# 六项对抗性缺陷修复实施计划

> **For agentic workers:** 使用 subagent-driven-development 按独立文件分工实施，根 Agent 集成并最终请非实施者复验。

**Goal:** 修复审核报告 A01–A06，再以隔离数据重走新增功能、采纳建议、保存看板。
**Architecture:** AI 只做分析；字段同步、编号保护、候选版本绑定与异步操作约束在代码中执行。保留 Markdown 事实来源和既有审核历史。
**Tech Stack:** Python 标准库 HTTP 服务、原生 JavaScript、unittest 与 Node VM 事件测试。
**Spec:** docs/test-reports/2026-11-05-adversarial-planning-flow.md。

## 约束与审核重点

先修 A01–A03，随后 A04–A06；测试使用独立目录，不能写入正式业务项目。需求实质变化重新审核；元数据小改不冒充新验收。旧编号包括已从规划删除但仍在台账的条目和功能组。保存前重新核对规划、参考选择及源码；不启动 AI 或下载作为普通保存的副作用。异步失败必须保留草稿，取消后按钮恢复。

## 第一阶段：数据一致性

- [ ] A01：tests/test_planning_operations.py 增加未开始/已完成需求变更、历史保护和幂等反例并观察失败。修改 scripts/planning_operations.py 字段同步与历史快照；serve_dashboard.py 仅接受可验证的合法历史变更，拒绝伪造完成或篡改证据。需求字段改变后原验收失效。
- [ ] A02：tests/test_planning_suggestions.py 先覆盖“生成建议后台账占用编号”。apply/validate 接受 reserved_ids；serve 在生成及预览时读取最新台账的组/节点编号。当前已有功能更新仍允许。
- [ ] A03：新增 tests/test_ledger_commit_gate.py，在真实临时HTTP服务复现更换参考后旧候选保存。generate 返回 source_revision；页面传递；preview/save 重验当前资料并比较绑定。持有 planning→workflow→document 锁，避免参考写入穿过最终校验。
- [ ] 跑针对性 Python 反例，再提交严重问题修复。

## 第二阶段：异步交互

- [ ] A04：旧读取延迟至保存后返回，页面应保留新版本；给读取响应加失效/世代校验。
- [ ] A05：主动读取等待或替代在途读取，真正成功后才清理草稿；失败保留恢复信息。
- [ ] A06：生成/保存第一个 await 前锁定；重复点击只发一个操作，取消/错误必须释放。
- [ ] 将上一轮 VM 反例落为断言测试；跑全部 CJS 后提交。

## 交付验证

- [ ] 全量 unittest、全部 CJS 和 diff 检查。
- [ ] 启动独立交付副本，真实 Codex 两轮新增与建议、代码合并、预览保存、转换确认、看板核对；保存关键截图和前后Markdown。
- [ ] 非实施者独立重放六个反例及恶意变体，给评分；失败继续修复。
- [ ] 同步既有规划/台账，只有独立通过才恢复勾选；本地提交，不自行推送。
