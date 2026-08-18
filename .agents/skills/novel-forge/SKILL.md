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
python tools/novel-workflow.py --root <绝对根目录> complete-role <slug> --session-id <宿主真实会话 ID>
# 第二版仍有 MUST、停在作者决定时，由作者授权一次续修
python tools/novel-workflow.py --root <绝对根目录> authorize-revision <slug> --reference <作者决定依据>
```

作者需要查看成本时，另运行只读命令：

```powershell
python tools/novel-workflow.py --root <绝对根目录> cost-summary <slug> [--chapter N]
```

成本观测不进入角色上下文、不改变路由；未知 token/耗时保持 null，不能因此重做正文或审稿。

## 宿主子代理派发合同

- 派发到 pi-subagent 类宿主时 `output` 参数必须保持 `false`（或指向非 canonical 临时路径）；`output` 指向 `draft/正文.md` 会被宿主当作完成回执槽位覆写，complete-role 会把该文件判为运输污染并重开 Writer。
- workflowScript 的长 task 文本用字符串数组 `.join('\n')` 构造；不要在反引号模板字面量里内嵌带引号的 shell 命令。
- 角色子代理只写动作允许路径；禁止运行 pytest、lint、git 或 canonical 产物路径之外的任何命令。
- complete-role 提示正文不是本次 Writer 产出时：用 `output:false` 派发新 Writer 读 capsule 重写；前一位 Writer 的 transcript 是恢复来源，Lead 不得亲手写 `draft/正文.md`。
- Windows 上 stop 子代理后 `.local-book-git` 可能残留锁定句柄；物理删除失败时先重命名 canonical 路径，`docs/examples/book-workflow-samples/` 的脱敏聚合目录是持久记录。

- `next-action <slug>` 默认是简明角色交接卡，不显示 JSON、哈希、Session 或 Guardian。只有宿主程序集成使用 `--json`。
- 每次只执行卡片上的一个角色。创建角色后必须使用宿主官方 wait/join/result 等到 `completed`、`failed` 或 `timed_out`；created、accepted、progress、idle、available 或文件稳定都不算完成。
- 所有角色（Writer/Blind Reader/Chapter Editor/Patch）一律经 Agent 子代理等独立会话执行；Lead 不得亲自写任何角色文件，包括 `draft/正文.md`、`local-patch/replacements.json` 和各 `result_file`。Lead 直接写出角色结果的章节按 `exploration` 处理，永远不能 formal ready。
- Writer 已产生合规正文但交付元数据缺失时，保留正文并由 Python 补记，**不重写正文**。审稿运输失败只重开该审稿角色。
- 第 N 章 ready 后，`next-action` 会告诉你 `start <slug> --chapter N+1`；后续章节会复用已保存元数据。本章未开始时才需要完整 `start` 参数。

## 角色卡如何执行

### Writer

只读取卡片给出的 capsule；只写 `draft/正文.md`（动作卡会列出只读文件，如 `控制面冻结稿.md`，禁止写入）。正式稿至少 5000 个 CJK 汉字。正文在晋升前永不被清除：技术重试、重新生成或审稿都不会删除已写的暂存正文。不得写脚本、规划表、状态、证据、审稿、runtime 或控制面；不得把提示词、技术表单、用户硬锚或审稿结论写进正文。

只读 capsule 的 `writer-context.md`；默认 P0/P1/P2 上限为 1500/850/450 CJK。按视角人物会注意什么来写，让私人欲望、关系摩擦和感知偏差进入动作。提交前全文检索并改掉破折号、省略号和“不是 X，而是 Y / 不是 X，是 Y”机械句，并在同一次调用内静默删去重复解释和最机械的一处重复反应。`literary-micro-rules/v5` 不要求数值风格目标或职业证明。

### Blind Reader

只读 capsule 的正文；只写卡片给定 result_file。给 `pass|needs_revision`、完整 MUST、`human_likeness`、`reader_desire`、情绪余味、下一章追读钩子、短摘要和一条逐字存在的引句。`uncertain` 不视为通过：pass 必须 `convincing`+`continue`；给 `uncertain` 必须附一句具体 `uncertain_note`（哪段像通用/工整/解释充分），说明为空则结果无效。若判 `synthetic`，必须给逐字证据、`needs_revision` 和恰好一条 `structural` MUST。每条开放 MUST 的原文 evidence 必须与正文逐字匹配，编造引文会被判无效。

### Chapter Editor

只读 capsule；只写 result_file。独立核对逻辑，只在问题分布广、值得唯一一次修订时确认 Blind Reader 的结构问题。机器纹理与 lint 抽样提示只是核对线索，不是文学结论，不得据此单独判错。给 `pass|needs_revision`、完整 MUST、短摘要和一条逐字存在的引句；每条开放 MUST 的原文 evidence 必须与正文逐字匹配。不要输出分析矩阵、hard-anchor 表或技术字段。

## 自动处理与停止点

- MAY/advisory 不触发 Patch。第一次双审的 MUST 合并后只回 Writer 一次；第二版仍有 MUST，进入用户决定，禁止无限重试。用户选续修时执行官方 `authorize-revision <slug> --reference <依据>`（记录 author 决策后恢复一次集中修订 + 完整双审），不是无限 retry。正文硬门失败、表面修订耗尽与 checkpoint 失败也会停在可授权 decision；checkpoint 失败时 authorize-revision 只重试 checkpoint 并保留已晋升草稿。
- Lean 双审并行：Writer 完成后一次签发 Blind Reader 与 Chapter Editor 两张卡（`next-action` 领取，可并行委派、完成顺序不限）；并行完成时用 `complete-role <slug> --role blind-reader|chapter-editor` 指明角色。Editor 无 Blind 结论时独立审稿。
- 双审通过前，不能有正式章节、Generation 和两份 Review、Guardian Receipt 或 Git checkpoint；晋升前 Python 先按 record_review 同源规则校验双审结论，校验失败不产生任何正式副作用；Python 晋升后才创建它们。
- `ready` 不等于作者批准，也不等于可以发布；不配置 remote。
- 未知遥测保持 null。不要伪造模型、token、Session、会话终态或作者授权。ACP 只用于事后取证。

## 不可越过的边界

创作角色只允许写当前书的动作允许路径；不得创建、注册、修改或安装宿主专用 Agent 类型，不得写 `.claude/agents`、Harness、SessionBackend、`NOVEL_FORGE_HARNESS_COMMAND`、代码、测试、Skill、状态、证据或其他书。不要直接编辑 `.local-guardian`、SQLite、章节序列、Guardian session 或不可变 evidence。

Canon 新信息先写 candidate，再经显式 promotion。每书 Git 仅本地恢复，禁止 remote/push。稳定叙事策略 ID：`no-deliberate-defects`、`single-winner-branch`、`model-score-not-approval`、`aesthetic-does-not-override-facts`、`exploration-not-ready`、`role-name-not-independence`、`world-not-protagonist-proof`、`expertise-must-be-executable`。需要细节时只打开当前书 capsule 和 `docs/43-fiction-first-lean-native-workflow.md` / `docs/44-current-workflow-logic-audit.md` 的相关段落。


## 45 号迭代默认规则

- Writer capsule 默认读 `writer-context.md` 最小 P0/P1/P2 包（1500/850/450 CJK，总计不超过 2800）；`full` 只作对照。Scene Package 的私人欲望、关系摩擦和感知偏差仍在原文件，不新增步骤。初稿/结构 Patch 写 `draft/正文.md`，局部 Patch 只写动作指定的 `replacements.json`；两条 Patch 路径都禁止新增解释性段落，新增因果必须落进动作/停顿/物件后果。
- 仅当全部开放 MUST 都是 `local` 且唯一可定位时走局部 Patch；Python 精确替换后必须重跑完整硬门和 Blind Reader + Chapter Editor。
- 同卷固定主要 Writer 模型；切换先执行 `approve-writer-model` 记录作者小样校准。模型、Session、哈希与 runtime 仍不交给创作角色猜。
- `native-isolated` 与 `managed-relay` 可正式生产；`exploration` 只能保留暂存稿/双审结果，永远不能 formal ready。
- 高风险章双审通过后仍停在作者确认；硬预算只在追加 Patch/复审前断路并保留全部暂存上下文。任何确认都不等于发布批准，`publication_eligibility=False`。
