# 功能建议任务流程 Implementation Plan

> Inline execution with superpowers:executing-plans; independent review follows feature-progress-tracker.

**Goal:** 输入、讨论/建议、选择、预览、保存形成可理解可恢复的单一任务流程。
**Architecture:** 独立 planning-assistant.js 管理输入模式/草稿/反馈；建议模块报告状态；原页面保留生成、保存和项目隔离处理器。
**Tech Stack:** 原生HTML/CSS/JS、Python stdlib、现有Node VM与Python测试。
**Spec:** docs/superpowers/specs/2026-11-04-assistant-task-flow.md

## Constraints and review focus
- 不改真实项目内容；默认不采纳，Markdown为事实来源。
- 初始项目、程序化拆分不被建议模式截获；测试真实页面handler。
- 生成失败/超长保留输入；草稿按KEY隔离；测试模块存储失败与恢复。
- 未保存预览与编辑互斥保护；放弃失败不清理；测试页面handler。
- 建议过期/零建议/未选解释禁用原因；测试建议状态。

## Tasks
- [x] 写assistant模块行为测试（模式、空输入、dirty、busy、恢复、焦点），先确认失败。
- [x] 实现模块与页面接入：模式选择、一个主动作、持续标签、工具收纳、最近讨论。
- [x] 补建议状态/选择计数与预览bar，复用已有保存与恢复文件逻辑；新增回归。
- [x] 跑适当测试，独立临时workspace浏览器走输入→建议→勾选→预览→保存/放弃，检查窄屏与失败；不以mock证明模型质量。
- [x] 独立审核，记录证据与台账，提交本地，不推送。
