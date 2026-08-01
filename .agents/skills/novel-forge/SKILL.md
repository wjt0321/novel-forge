---
name: novel-forge
description: 在 S-Black Novel Forge 中以最小控制面完成通用、厂商无关的正式小说章节生产。
---

# Novel Forge：一眼可执行的日常流程

这是唯一主产品：`lean_native`。它不绑定模型、厂商或宿主；用宿主已有的独立 Session、Team、Task Agent 或 Role 即可。`--strict-audit` 只用于用户明确要求的审计/基准实验；`NOVEL_FORGE_HARNESS_COMMAND` 只是可选 headless，不是日常前提。

## 只记住这条链

`start -> Python/宿主适配器签发受限角色 -> complete-role -> 下一动作/作者决定`

```text
Writer 暂存正文
  -> Blind Reader
  -> Chapter Editor
  ->（有 MUST）Writer 在同一正文集中修订，再跑双审一次
  ->（双审 pass）Python 自动晋升为 ready
```

不要先探索仓库、读旧会话、调表、计算哈希、补状态、改 capsule 或配置 Harness。Python 创建项目骨架、动作、证据、状态和本地恢复点；Lead 只分发、等待和调用命令。

## 用户/Lead 的生产命令

```powershell
python tools/novel-workflow.py --root <绝对根目录> start <slug> --title ... --genre ... --protagonist ... --world ... --conflict ... --hook ...
python tools/novel-workflow.py --root <绝对根目录> next-action <slug>
python tools/novel-workflow.py --root <绝对根目录> complete-role <slug>
# 第二版仍有 MUST、停在作者决定时，由作者授权一次续修
python tools/novel-workflow.py --root <绝对根目录> authorize-revision <slug> --reference <作者决定依据>
```

作者需要查看成本时，另运行只读命令：

```powershell
python tools/novel-workflow.py --root <绝对根目录> cost-summary <slug> [--chapter N]
```

成本观测不进入角色上下文、不改变路由；未知 token/耗时保持 null，不能因此重做正文或审稿。

- `next-action <slug>` 默认是简明角色交接卡，不显示 JSON、哈希、Session 或 Guardian。只有宿主程序集成使用 `--json`。
- 每次只执行卡片上的一个角色。创建角色后必须使用宿主官方 wait/join/result 等到 `completed`、`failed` 或 `timed_out`；created、accepted、progress、idle、available 或文件稳定都不算完成。
- 所有角色（Writer/Blind Reader/Chapter Editor/Patch）一律经 Agent 子代理等独立会话执行；Lead 不得亲自写任何角色文件，包括 `draft/正文.md`、`local-patch/replacements.json` 和各 `result_file`。Lead 直接写出角色结果的章节按 `exploration` 处理，永远不能 formal ready。
- Writer 已产生合规正文但交付元数据缺失时，保留正文并由 Python 补记，**不重写正文**。审稿运输失败只重开该审稿角色。
- 第 N 章 ready 后，`next-action` 会告诉你 `start <slug> --chapter N+1`；后续章节会复用已保存元数据。本章未开始时才需要完整 `start` 参数。

## 角色卡如何执行

### Writer

只读取卡片给出的 capsule；只写 `draft/正文.md`（动作卡会列出只读文件，如 `控制面冻结稿.md`，禁止写入）。正式稿至少 5000 个 CJK 汉字。不得写脚本、规划表、状态、证据、审稿、runtime 或控制面；不得把提示词、技术表单、用户硬锚或审稿结论写进正文。

只读 capsule 的 `writer-context.md`；默认 P0/P1/P2 上限为 1500/850/450 CJK。按视角人物会注意什么来写，让私人欲望、关系摩擦和感知偏差进入动作。提交前全文检索并改掉破折号、省略号和“不是 X，而是 Y / 不是 X，是 Y”机械句，并在同一次调用内静默删去重复解释和最机械的一处重复反应。`literary-micro-rules/v5` 不要求数值风格目标或职业证明。

### Blind Reader

只读 capsule 的正文；只写卡片给定 result_file。给 `pass|needs_revision`、完整 MUST、`human_likeness`、`reader_desire`、情绪余味、下一章追读钩子、短摘要和一条逐字存在的引句。`uncertain` 默认不触发修订；若判 `synthetic`，必须给逐字证据、`needs_revision` 和恰好一条 `structural` MUST。

### Chapter Editor

只读 capsule；只写 result_file。独立核对逻辑，只在问题分布广、值得唯一一次修订时确认 Blind Reader 的结构问题。机器纹理提示只是核对线索，不是文学结论。给 `pass|needs_revision`、完整 MUST、短摘要和一条逐字存在的引句。不要输出分析矩阵、hard-anchor 表或技术字段。

## 自动处理与停止点

- MAY/advisory 不触发 Patch。第一次双审的 MUST 合并后只回 Writer 一次；第二版仍有 MUST，进入用户决定，禁止无限重试。用户选续修时执行官方 `authorize-revision <slug> --reference <依据>`（记录 author 决策后恢复一次集中修订 + 完整双审），不是无限 retry。
- 双审通过前，不能有正式章节、Generation 和两份 Review、Guardian Receipt 或 Git checkpoint；Python 晋升后才创建它们。
- `ready` 不等于作者批准，也不等于可以发布；不配置 remote。
- 未知遥测保持 null。不要伪造模型、token、Session、会话终态或作者授权。ACP 只用于事后取证。

## 不可越过的边界

创作角色只允许写当前书的动作允许路径；不得创建、注册、修改或安装宿主专用 Agent 类型，不得写 `.claude/agents`、Harness、SessionBackend、`NOVEL_FORGE_HARNESS_COMMAND`、代码、测试、Skill、状态、证据或其他书。不要直接编辑 `.local-guardian`、SQLite、章节序列、Guardian session 或不可变 evidence。

Canon 新信息先写 candidate，再经显式 promotion。每书 Git 仅本地恢复，禁止 remote/push。稳定叙事策略 ID：`no-deliberate-defects`、`single-winner-branch`、`model-score-not-approval`、`aesthetic-does-not-override-facts`、`exploration-not-ready`、`role-name-not-independence`、`world-not-protagonist-proof`、`expertise-must-be-executable`。需要细节时只打开当前书 capsule 和 `docs/43-fiction-first-lean-native-workflow.md` / `docs/44-current-workflow-logic-audit.md` 的相关段落。


## 45 号迭代默认规则

- Writer capsule 默认读 `writer-context.md` 最小 P0/P1/P2 包（1500/850/450 CJK，总计不超过 2800）；`full` 只作对照。Scene Package 的私人欲望、关系摩擦和感知偏差仍在原文件，不新增步骤。初稿/结构 Patch 写 `draft/正文.md`，局部 Patch 只写动作指定的 `replacements.json`。
- 仅当全部开放 MUST 都是 `local` 且唯一可定位时走局部 Patch；Python 精确替换后必须重跑完整硬门和 Blind Reader + Chapter Editor。
- 同卷固定主要 Writer 模型；切换先执行 `approve-writer-model` 记录作者小样校准。模型、Session、哈希与 runtime 仍不交给创作角色猜。
- `native-isolated` 与 `managed-relay` 可正式生产；`exploration` 只能保留暂存稿/双审结果，永远不能 formal ready。
- 高风险章双审通过后仍停在作者确认；硬预算只在追加 Patch/复审前断路并保留全部暂存上下文。任何确认都不等于发布批准，`publication_eligibility=False`。
