# 30. 编译 Writer Prompt 与提示词来源证明

## 背景

2026-07-20 的五章事故说明了两个不同问题：

1. 简陋用户提示词可能没有把范围、输出和停止条件说全；
2. 即使自然语言规则完整，拥有控制面与脚本权限的 writer 仍可能绕过 Harness。

v4.4 用隔离 capsule 解决第二个问题。v4.5 不把责任重新推回用户，而是让 Harness
把简短的一章式意图编译成固定、完整、可验证的 writer 指令。

## 用户入口

日常 formal 写作一次只做一章。用户提示可以保持简短，例如：

```text
按当前规划写第 3 章正式稿。
```

用户不需要重复粘贴 Skill、门禁、证据字段、脚本禁令或 token 预算。Orchestrator
负责章节序列、session claim 与上下文准备；Guardian 负责生成最终
`instructions.md`。

## 模板合同

首个模板 ID 为 `formal-writer/v1`，由 `app/novel_forge/writer_prompt.py` 单源定义。
模板不超过 1200 字符，并固定包含：

- 当前只负责哪一章；
- 初稿只读取 `handoff.md`；集中 patch 还读取预置的 `draft/正文.md`；
- 写出有压力、选择、后果和停止点的完整章节；
- 正式正文不少于 5000 CJK；
- 唯一输出为 `draft/正文.md`，其中只含章节标题和小说正文；
- 禁止脚本、状态、evidence、review、runtime 与控制面访问；
- 输入冲突、能力不足或无法满足 formal 条件时停止并返回阻断原因。

模板不包含 provider/model 名称，不包含完整 Skill、验证器源码、旧审稿全文、多章
上下文或句长、对白率等数值风格目标。

同一模板根据 capsule operation 编译两种任务文本：`draft` 要求一次完成完整章；
`patch` 要求按审稿结论集中修订、保留未受影响正文，并禁止借 patch 重写整章。

## Capsule 与证据绑定

`prepare-writer-capsule` 生成：

```text
capsule.json
guardian-contract.json
instructions.md
handoff.md
draft/
```

`instructions.md` 被列入受保护输入。Guardian 将以下字段写入 capsule manifest、
控制记录、clean/compromised 回执和 adapter 返回：

```json
{
  "prompt_template_id": "formal-writer/v1",
  "prompt_sha256": "<instructions.md SHA-256>"
}
```

formal agent 的 generation evidence 必须记录同一对字段。进入 `ready` 时，系统会
复核 generation、签名外置回执与 imported 控制记录完全一致；缺失、篡改或错配都会
成为 Guardian workflow integrity blocker。

## Token 原则

v4.5 的节省来自减少重复上下文，而不是降低完整性：

- writer 每章新会话，只注入一份短指令和一页有界 handoff；
- 不把完整 Skill、ACP transcript、验证器源码或旧工具输出回灌给 writer；
- prompt 哈希、文件清单、预算和回执校验全部由本地 Python 完成；
- 规划与困难因果检查可用 high，正文和默认审稿仍用 standard/medium；
- 初稿一次完整 Write，最多一次集中 patch。

因此，简短提示词不再意味着简陋规则；完整规则也不再意味着每章重复消耗大量模型
上下文。

## 通用性边界

`formal-writer/v1` 不绑定任何模型、Agent 产品、ACP 实现或 Shell。外部 Harness
只需实现机器合同：创建新原生 writer session、限制 capsule-only 文件系统、传入
编译指令与 handoff、在模型外记录 runtime，然后调用 Guardian 导入。

ACP 仍可用于事故调查，但不是 formal 生产依赖。提示词模板解决“给 writer 什么”，
Guardian 隔离解决“writer 能碰什么”；两者缺一不可。
