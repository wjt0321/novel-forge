# 源码卫生与成本短路（v3.7）

> 本文保留 v3.7 的实验背景与设计记录。当前默认执行链已由
> [23-lean-literary-loop.md](23-lean-literary-loop.md) 的 v3.8 精简文学闭环取代。

## 问题

`books/yanshi-lu` 的五章连续实验暴露出一种 Markdown 源码污染：第 2 章开始在叙事正文中使用 `**...**`，随后格式被下一章场景包、正文和审稿引文继续模仿。Markdown 渲染会弱化视觉差异，但原始文件出现数千个强调分隔符，已经不是正常排版。

旧流程存在两个缺口：

1. `quality_check.py` 不检测 Markdown 强调标记，因此污染稿显示 `Blocking: 0`。
2. `surface_checked` 只是可推进状态，未在迁移时重跑机器门禁；六个同源审稿角色可以继续消耗上下文并把污染句当作通过证据。

## v3.7 规则

1. `markdown-emphasis` 成为 blocking lint。`正文.md` 除章节标题外必须保持纯叙事源码，禁止 `**粗体**` 与 `__强调__`。
2. 进入 `surface_checked` 时由状态机重跑 lint；任何 blocking 都拒绝迁移，并明确禁止启动后续审稿。
3. context-collector 只向 writer 交付去除模板格式的最小摘要，不复制规划标签的 Markdown 语法。
4. 上一章存在 source-hygiene blocking 时，不得准备下一章，阻断跨章格式自我复制。
5. 原始正文默认使用 standard/medium 推理。Max/长思考保留给写前反证、章际交接、因果归属、findings 合并或用户明确声明的推理强度实验。
6. 即使正文实验使用 Max，也不自动把 Max 复制给六个同源审稿角色。工具级 blocking 先于昂贵审稿，失败立即短路。
7. `project-status` 对旧 `ready` 章节复核当前门禁。规则升级后不再满足条件的章节保留历史状态，但会出现 `ready_with_blocking_gates` workflow integrity blocker。

## 成本判断

流程的结构复杂度不是 `**` 的直接成因；直接成因是规划材料的强调格式进入正文后，没有源码卫生门阻止它继续成为下一章上下文。复杂度放大了损失：一个低成本、可机械识别的问题穿过门禁后，触发了六角色全文读取、审稿落盘和后续章节上下文扩张。

因此本次优化不删状态、不增审稿角色，而是调整执行顺序：

`drafted → blocking source hygiene → surface_checked → expensive reviews`

系统仍保留可审计链，但把最便宜、确定性最高的检查放在最前面。

## 证据边界

本次 generation evidence 未记录 elapsed/token 指标，均为 `null` / `unknown`。用户报告 Claude Code 的五小时额度被耗尽，可以作为运行观察，但当前仓库无法据此还原精确 input/output token 分布。后续基准应优先从 Harness 写入真实 token、耗时、暂停和交互次数。
