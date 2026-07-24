---
name: novel-forge
description: Use when creating, planning, drafting, reviewing, repairing, auditing, or continuing a Novel Forge fiction project.
---

# Novel Forge

Novel Forge 的唯一主产品是**小说正文**。规划、表、哈希、Generation、Runtime、
Guardian、状态和 Git 都是服务正文的附属记录，不得反过来阻碍有效正文。

## 直接开始

创作任务不要先探索 `app/`、`tests/`、`docs/`、Git 历史或旧实验书。首个写操作只能是：

```bash
python tools/novel-workflow.py --root <绝对仓库根> start <slug> \
  --title ... --genre ... --protagonist ... --world ... --conflict ... --hook ...
```

Windows 下 `--root` 必须是绝对路径。Git Bash/类 Bash 中统一写成 `D:/mydev/s-black-novel`；
若使用反斜杠路径则必须整体加引号。禁止传入未加引号的 `D:\mydev\s-black-novel`，
因为 Bash 会吞掉反斜杠；CLI 会在创建任何资产前拒绝 `D:foo` 一类驱动器相对路径。

之后只循环：

```bash
python tools/novel-workflow.py --root <根> next-action <slug>
python tools/novel-workflow.py --root <根> complete-role <slug>
```

`next-action` 的首个 Lean Writer 动作直接是 `stage=draft`。Python 在后台生成最小的
连续性与场景材料；Writer 可以在自己的写作过程中思考规划，但不需要先回传规划表。
Writer 只写当前书 `.novel-forge/diff/chNN/writer/draft/正文.md`；两个审稿角色读取该
暂存正文，只把结论写入同章 diff 区的 `result_file`。Lead 等待宿主官方终态后执行
`complete-role`，无需填写技术表单、拼装会话 ID 或搬运正文。

## 默认模式

默认是 `lean_native`：

- Python 创建项目骨架并维护当前书的 diff 暂存区。只有两个审稿角色都通过后，Python
  才把暂存正文晋升到 `chapters/`，建立 Generation、绑定 Review、推进状态并建立每书
  Git 恢复点。
- Python 对 Writer Capsule 和当前书做确定性完整性检查，并轻量保护代码、测试、双 Skill
  与根入口规则、当前书 Guardian/本地 Git 账本；动作或 state 被修改时先恢复并重新
  加载可信状态。快照按仓库路径分区，角色不会靠改白名单或撞同名 slug 取得通过。
- 审稿 capsule 输入属于 Python 管理路径，由 manifest 哈希复核；合法刷新不算角色越界，
  但角色修改声明文件或新增额外文件仍会失败并重建当前审稿会话。
- provider、model、token、请求数、耗时或 thinking 深度取不到时保持
  `unknown` / `null`，只记录，不阻断正文、双审或 ready。
- 未知遥测保持 null；不得估算，也不得把未知值变成写作失败。
- 不要求 Lead 或创作角色填写 Runtime、Guardian、Generation、SHA-256、状态或 Git。
- 有效正文已经产生后，技术附属记录失败必须优先原地收尾，禁止无理由重写正文。

只有用户明确要求取证、基准或完整运行审计时，才在命令前加入 `--strict-audit`。
严格模式保留完整遥测、技术完成信封和全仓快照；它不是日常创作默认值。

## 通用宿主

本 Skill 不绑定 Claude、Kimi、Codex、OMP、Trae、Qoder、模型厂商或具体模型。

- 使用宿主已有的独立 Session、Teams、Task Agent、Role 或等价能力。
- `next-action` 的角色产物即使位于当前书允许路径，也只能由对应独立角色写；Lead 禁止亲自写正文或审稿 JSON。
- `control_run_id` 是 Python 内部恢复细节，不得出现在公开动作中，也不得由 Lead 猜测、拼装或回传。
- 不得创建、注册、修改或安装宿主专用 Agent 类型。
- 不得写入项目级或用户级 `.claude/agents`、自定义 Harness 或 SessionBackend。
- `NOVEL_FORGE_HARNESS_COMMAND` 只是可选 headless 命令桥，不是交互式创作前置条件。
- ACP 只用于事后取证，不参与生产调度。
- 宿主无法创建真实独立会话时停止并说明“本章未开始”，不得用单会话冒充三角色。

## 三角色

### Writer

日常 Lean 的首个 Writer 动作直接写正文。Python 已在后台准备最小的连续性与场景材料；
Writer 可自行思考必要规划或做最多 5 次题材常识、事实边界、重名检索，但不回传规划表，
也不增加独立规划回合。遇到 MUST 时，Patch Writer 优先复用当前 Writer 宿主会话；
宿主无法复用时才创建新的独立 Writer Session。

Writer 只读取动作签发的当前书 Writer Capsule，初稿和集中修订始终写同一文件：

`.novel-forge/diff/chNN/writer/draft/正文.md`

Python 会把首次通过表面检查的版本冻结为 `.novel-forge/diff/chNN/初稿.md`。审核提出
MUST 时，Writer 直接修改原暂存正文；不得复制新正文、修改 `chapters/` 或填写任何
Generation、Runtime、Guardian、状态、哈希、Session、Review、Git 表格。

正式章至少 5000 个 CJK 汉字。正文不得出现提示词、工作流、Agent、状态、哈希、
Generation、Guardian、Git 或审稿信息。

### Blind Reader

必须使用不同于 Writer 的新 Session，只读取封存 Capsule 中的当前完整正文。
禁止读取规划、Canon、Writer 会话、其他章节或未来剧情。

必须独立判断：

- 是否像真人写作；
- 是否自愿继续下一章；
- 空间、身体、动作、限制和情绪能否重建；
- 对白与信息释放是否自然；
- 至少三个可记忆画面；
- 阻止继续阅读的 MUST 与可选 MAY。

只有 `human_likeness=convincing` 且 `reader_desire=continue` 才能 pass。
Lean 只写动作指定的简短 `result_file`，不填写完整终态、哈希、Session、Runtime、
Guardian、Git 或分析矩阵。

### Chapter Editor

必须在 Blind Reader 正式记录后创建第三个新 Session。只读取：

- 当前完整正文；
- 当前场景包与用户硬锚；
- 必要 Canon 和上一章末段；
- Blind Reader 结果；
- strict audit 下的有界机器诊断；Lean 不要求这张附属表。

独立检查因果、主角主动选择、私人代价、物理连续性、人物知识来源、职业行动、
对白、句子节奏、核心冲突与章末钩子。不得照抄 Blind Reader，也不得直接改正文。

Lean 只返回 `verdict=pass|needs_revision`、一次列全的 `must`、简短 `summary` 和一条
`evidence_quote`。不填写 `analysis`、`hard_anchor_coverage`、哈希、状态或 Session 表；
Python 会把通用 `pass` 规范化为内部通过状态，并自动修复常见的正文引号未转义问题；
旧角色误写的纯文本 hard-anchor 说明在 Lean 中直接忽略。strict audit 才使用完整编辑表。

## 自动闭环

1. Python 初始化项目，并直接签发 Writer 的 `draft` 动作。
2. Writer 在当前书 diff 区写本章正文。破折号、省略号和“不是 X 而是 Y / 不是 X，是 Y”
   是 AI 机械语言硬门；起草时就必须禁用，提交前全文检索。若仍有命中，Python 一次
   汇总全部位置，复用同一 Capsule 和暂存正文集中修订，最多三轮才请求用户决定。
3. Lead 签发 Blind Reader 审稿；Blind Reader 只读当前暂存正文并给出结论。
4. Blind 记录成功后，Lead 签发 Chapter Editor；Chapter Editor 结合必要场景材料复审。
5. 两审通过时，Python 自动把暂存正文晋升为 `chapters/eXX/ch-XX/正文.md`，再创建
   Generation、Guardian Receipt、Review 绑定、`ready` 状态和本地 Git 恢复点。
6. 任一审稿给出 MUST 时，Lead 直接把合并问题发回 Writer 的 `patch` 动作，优先复用
   当前宿主 Writer 会话。
7. Writer 在原暂存正文上修订；表面检查通过后 Python 立即生成 `修订.diff`，再启动
   新一轮双审。两个审稿角色都必须重读修订后的完整正文。
8. 第二版仍有 MUST 时才停止自动回炉并让用户选择，不无限循环。

Lead 不写正文、不审稿、不代填结论、不选择模型来源真相，也不直接操作
Generation、Review、状态或 Git。日常流程只调度写作、双审与一次必要修订，
不为技术表单额外开回合。

## 等待与恢复

- 创建成功、accepted、progress、working、idle、available 或文件出现都不是完成。
- 必须使用宿主官方 wait/join/result 机制等待 completed、failed 或 timed_out。
- 角色仍在 working/progress 时继续等待，禁止因 Lead 短超时而越权代做。
- 结果文件缺失、Session 异常或角色实质失败时废弃该 Session，创建同角色新 Session，
  最多自动重试 2 次。
- 失败 Receipt 保留原样，禁止改成 clean；退役 Session 的晚到产物无效。
- Writer 已产生合规正文而交付元数据缺失时，保留正文并由 Python补记；不得重跑 Writer。
- 审稿运输或结果丢失只重开对应审稿角色，不重写正文。
- Python 合法刷新审稿 capsule 时不得记为 `control_plane_mutation`，也不得因此消耗重试预算。
- Writer 修订后的新一轮双审重新从 0 计算各角色技术重试，不继承旧正文的运输失败次数。
- 审稿重试耗尽后，用户选择继续时先校验暂存正文哈希，再恢复失败的审稿角色；即使
  Generation 尚未创建，也不得因此重新调用 Writer。
- 两次技术重试耗尽后才向用户显示：
  A. 保留草稿
  B. 重新生成本章
  C. 停止任务

用户界面只显示：

- 正在写作。
- 正在自动审稿。
- 发现问题，正在自动修订。
- 写作会话异常，已自动换新会话重试。
- 第一章完成，是否继续第二章？

不得向用户展示原始 JSON、哈希、Session、Guardian、Git、Runtime 或 Traceback。

## 文学短规则

日常只加载 `literary-micro-rules/v4`，不加载样本全文。

- 可以写：人物在具体压力下主动选择并付出私人代价；劳动、身体、物件、位置和关系
  持续改变下一步行动。
- 慎写：术语、精确数字、比喻、母题和完美证据链；只有改变决定、限制、风险或后果
  时才保留。
- 允许：误判、迟疑、沉默、反应迟半拍、不对称对白、未解释余波和不整齐节奏。
- 绝对禁止：把规划、审稿、主题或因果清单翻译成说明段；机械三连、连续否定翻转、
  控制面语言、职业证明循环、解释性修补和用户硬锚漂移。

机器门只拦高置信破绽，不认证文学价值。MAY 和 advisory 不自动触发 Patch。

## 长篇连续性

Canon、开放承诺、上一章末段、Voice exemplar 与当前场景包由 Python 组成有界
handoff。不得把全书 Canon、旧审稿全文、旧会话 transcript 或验证器源码回灌 Writer。

新连续性信息先进入 candidate，再晋升 Canon。正文、记忆和审稿只属于当前书，不得
跨书复制。

## 不可变与安全

- 稳定策略 ID：`no-deliberate-defects`、`single-winner-branch`、
  `model-score-not-approval`、`aesthetic-does-not-override-facts`、
  `exploration-not-ready`、`role-name-not-independence`、
  `world-not-protagonist-proof`、`expertise-must-be-executable`。
- 双审通过并晋升后才创建 Generation 和两份 Review；暂存区内的一次集中修订不创建
  中间 Generation。正式正文再次改变时必须新建 Generation，旧记录变 stale。
- Guardian Receipt、Runtime Audit、Generation 和 Review History 创建后不可覆盖。
- 外置 Guardian 只在 `<root>/.local-guardian/<slug>/`；禁止在书目录内创建。
- 每书 Git 只做本地恢复，不配置 remote，不代表作者批准或发布许可。
- `ready` 代表工作流通过，不代表用户批准。
- 未经用户明确要求，不得 commit、push 或删除实验书。
