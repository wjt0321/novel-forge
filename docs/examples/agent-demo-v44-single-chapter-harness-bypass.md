# 单章写作绕过 Harness 的脱敏样本

## 样本边界

- 日期：2026-07-21
- 书项目：`cracked-sky-roof`
- 运行组合：Claude Code + DeepSeek V4 Flash，用户要求 medium reasoning
- 本文件只保留流程结论、量化指标与哈希，不保留小说全文、原始提示词、思考链或完整会话。

## 观测结果

- 第一章正文：5084 CJK，SHA-256 `f04bbb2c6556dc1f76c5b89a7a9e474809b3a55f4cb8f9c0c37310b55fba5d9a`
- 规则 lint：0 blocking，3 advisory
- 每书本地 Git 最后提交：`ae8fe591fe1d66b9c7445b5d60ce4339eb6e1acc`，消息 `chapter: ch01 draft`
- 项目审计：`workflow_integrity.status=blocked`
- generation evidence：0
- runtime budget：unassessed
- 章节真实状态仍为 `planned`，但正文已经存在，触发 `content_present_while_planned`
- blind-reader 与 chapter-editor 均由 writer 同一会话模拟生成；两份记录均 stale 且 `validation_valid=false`
- 未建立 chapter sequence、session claim、Guardian capsule、外置 runtime sidecar 或签名 receipt

## 根因

普通 Claude ACP 会话从项目根目录启动，拥有正文与控制面的完整读写和 Shell 权限。项目虽有 Harness/Guardian 合同和事后校验器，但没有外部 Orchestrator 真正创建 capsule-only writer、记录模型外 runtime 并自动启动独立审稿会话。任务中的降级语句又允许在 formal 条件不足时继续产出可读草稿。

## 处置

完成本脱敏样本后，按用户明确授权将以下两项移入 Windows 回收站：

- `books/cracked-sky-roof/`
- `.local-book-git/cracked-sky-roof.git/`

本次未生成 `.local-guardian/cracked-sky-roof/`。样本不能用于认证文学价值、作者批准或模型排名。
