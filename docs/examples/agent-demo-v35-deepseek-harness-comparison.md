# DeepSeek 双 Harness 实验评鉴

## 实验边界

- 记录日期：2026-07-17
- 底层模型：用户声明均为 DeepSeek-V4-Pro
- `silent-era`：专职写作 Harness（Agent A）；Shell 因沙箱不可用，Agent 自行建立了最小目录和部分材料
- `reborn-1998`：专职编程 Harness（Agent B）；启用 Max 思考，连续生成两章
- 两组样本的题材、章节数、工具权限与思考模式不同，因此本实验比较的是 Harness 行为与工作流适配，不是模型能力排行榜
- 用户说明属于本轮实验的来源事实；样本内部自填的 provider/model/date 与用户说明冲突时，不采信样本自填值

## 样本指纹

### silent-era

- 项目文件：8 个，共 29,725 bytes
- 正文：`chapters/e01/ch-01/正文.md`
- SHA-256：`0ab90944bc85d2ab87ca2f1334729881c059d38ec86eb33015a0b89ea5c4b3fb`
- CJK：5,746
- 句子：418
- 平均句长：13.7
- 句长变异系数：0.648
- 对话占比：0.155
- 微段落占比：0.338
- 比喻密度：4.18 / 千字
- 分句复杂度：1.86
- quality gate：3 blocking，14 advisory
- narrative gate：10 blocking，2 advisory
- workflow integrity：blocked；缺少 chapter-state、generation 与正式审稿

### reborn-1998 / ch01

- 正文 SHA-256：`d31c2617b156490edfce0fa733fcd53f60a0061244327dd16f9aca19f5b07788`
- CJK：6,468
- 句子：295
- 平均句长：21.8
- 句长变异系数：0.623
- 对话占比：0.159
- 微段落占比：0.267
- 比喻密度：2.63 / 千字
- 分句复杂度：2.51
- quality gate：0 blocking，6 advisory
- narrative gate：0 blocking，0 advisory

### reborn-1998 / ch02

- 正文 SHA-256：`9d3e105d8857fd7f2fdb432bc180693626280efdcbdceaf8bad5c5575afdb253`
- CJK：7,103
- 句子：330
- 平均句长：21.5
- 句长变异系数：0.607
- 对话占比：0.183
- 微段落占比：0.170
- 比喻密度：1.13 / 千字
- 分句复杂度：2.41
- quality gate：0 blocking，13 advisory
- narrative gate：0 blocking，0 advisory

`reborn-1998` 项目共有 78 个文件、223,501 bytes。两章声音指纹未达到既有漂移阈值，但第二章的解释腔、清单式短段与结论性短句明显增加。

## Agent A：写作 Harness

### 保留优点

1. 在 Shell 不可用时仍完成了达到正式字数底线的正文，说明写作 Harness 能在工具退化时保住核心创作任务。
2. 视角贴近身体和可操作物：停表、剩水、军刀、饼干、楼梯呼吸声持续承担压力。
3. 人物认知有限，配角和环境保有独立目的；世界没有按顺序证明主角正确。
4. 场景冲突依靠行动、空间和资源推进，解释性总结很少。

### 保留缺点

1. 场景包声明在“打开防盗门、走进走廊”停止，正文却继续新增顾小满、尸体、陈叔势力与寻找护士任务，规划边界失效。
2. 房号发生硬冲突：门外称主角为 506，后文顾小满称其为 505。
3. 三处 `不是 X，是 Y` 命中 blocking。
4. 比喻达到 24 处，超过本书声音预算。
5. Agent 自建的是近似目录，不是可审计的 Novel Forge 项目；缺少状态、生成证据、审稿和 v3.5 场景字段。

### 结论

这是“降级环境下正文成功、正式流程失败”的样本。系统此前只有成功路径和错误路径，没有诚实的降级路径，迫使 Agent 要么停止，要么自行模仿目录结构。

## Agent B：编程 Harness + Max

### 保留优点

1. 能完整铺设两章规划、动作稿、对白账本、状态、审稿和 generation 外观。
2. 两章都达到正式字数，硬 lint 为零。
3. 人物、竞赛队、电脑城、装机和域名计划在表层上形成连续的商业网文推进。
4. 场景目标明确，可读性和即时反馈较强。

### 保留缺点

1. 第一章已经写到同日傍晚，第二章却从同日下午三点重新开始；场景包和 consistency review 仍声称时间线自洽。
2. 配角持续经历“轻视主角、被主角证明、转为欣赏”，世界逐渐成为主角能力证明装置。
3. 第二章增加政策解释、成功履历、商业路线摘要和计划清单，Max 思考没有转化成更多反证。
4. 每章记录 4 条 generation，但同章四条全部绑定同一正文 SHA-256，且均为 `raw / review_round=1`；它们是重复证据，不是四代正文。
5. 十二份 review 同时存在 canonical 根目录版与章节子目录版，两套逐字相同。
6. generation 与 review 自填 `anthropic / claude-opus-4-5 / reasonix-executor / 2025-01-20`，与用户声明的 DeepSeek 自制 Harness 实验冲突。
7. Agent authority 的 generation 自称 `user_attested`，越过了来源权威边界。
8. blind-reader 引用正文不存在的“我靠”，chapter-editor 将解释性计划摘要误判为“展示而非讲述”。

### 结论

这是“工程产物丰富、过程证据失真”的样本。Max 思考被 Harness 导向了补齐文件与为成品辩护，而不是跨章反证、证据核验和失败搜索。

## 两类 Harness 的核心差异

| 维度 | Agent A | Agent B |
|---|---|---|
| 首要忠诚 | 完成正文 | 完成工程流程 |
| 工具失败反应 | 自建最小结构继续写 | 不适用 |
| 主要优势 | 场景、压迫感、有限认知 | 结构铺设、状态推进、两章产出 |
| 主要盲点 | 规划越界、流程缺失 | 形式主义、自证、重复证据 |
| 对 Token 的使用 | 集中在正文 | 大量消耗在规划、复制和同源审核 |
| 最需要的约束 | 降级协议与导入路径 | 来源锁定、语义去重、章际反证 |

## 固化的改造需求

1. generation 预算按不同正文 SHA-256 计数，不按证据文件数计数；同章同哈希重复登记必须拒绝。
2. Agent authority 不能声明 `user_attested`；来源置信度必须与 authority、metrics_source 和运行身份一致。
3. generation 记录增加 `run_id`、`agent_harness`、`reasoning_effort`、`sandbox_profile`、`tool_capabilities` 与 `tool_failures`。
4. 增加 `degraded_exploration` 模式：Shell/adapter 不可用时保留正文与最小运行报告，但禁止进入 ready 或 benchmark。
5. 第 2 章起场景包必须绑定上一章正文 SHA-256、章末证据、当前开场证据、时间关系、地点和动作交接。
6. 同日连续场景若本章开始时点早于上一章结束时点，narrative gate 阻断。
7. 第 2 章起 consistency-guard 与 chapter-editor 必须绑定上一章 SHA-256，并各提供上一章与当前章的可核验原文短引。
8. 关键审稿引用必须能在绑定正文中精确找到；不存在的引文不得记录为有效审稿。
9. `project-status` 报告非 canonical review 副本、重复 generation 组和来源不一致。
10. 下一次五章测试以 ch02-ch05 的章际交接、ch05 checkpoint arc audit 和正文版本链为主要验收面。

## 保留与清理决定

- 保留：本报告、同名 JSON、正文 SHA-256、CJK 与声音指标、门禁统计、具体错误证据、Harness 来源说明和改造需求。
- 不保留：三篇全文、两书规划、审稿、generation、工具副本、缓存和 Agent 自建目录。
- 删除目标：`books/silent-era`、`books/reborn-1998`。

