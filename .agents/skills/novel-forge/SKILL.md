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

之后只循环：

```bash
python tools/novel-workflow.py --root <根> next-action <slug>
python tools/novel-workflow.py --root <根> complete-role <slug> \
  --session-id <宿主返回的真实会话ID>
```

`next-action` 已给出角色、上下文 Capsule、输出位置和停止条件。规划或审稿角色把
简短 JSON 写入动作的 `result_file`；Writer 只写 Capsule 内的 `draft/正文.md`。
Lead 等待宿主官方终态后只回传真实 session ID，不搬运正文，不拼装技术 JSON。

## 默认模式

默认是 `lean_native`：

- Python 创建项目骨架，计算正文与规划哈希，建立 Generation，标记旧记录 stale，
  绑定 Review，推进状态并建立每书 Git 恢复点。
- Python 对 Writer Capsule 和当前书做确定性完整性检查；角色不得写项目控制面。
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
- 不得创建、注册、修改或安装宿主专用 Agent 类型。
- 不得写入项目级或用户级 `.claude/agents`、自定义 Harness 或 SessionBackend。
- `NOVEL_FORGE_HARNESS_COMMAND` 只是可选 headless 命令桥，不是交互式创作前置条件。
- ACP 只用于事后取证，不参与生产调度。
- 宿主无法创建真实独立会话时停止并说明“本章未开始”，不得用单会话冒充三角色。

## 三角色

### Writer

每章使用新的真实 Writer Session。第一轮 Writer 可在同一 Session 内先完成必要规划，
再写正文；规划只是附属产物，不是第四个角色。Writer 可做最多 5 次题材常识、事实
边界或重名检索，不得借此探索仓库实现。

Writer 只读取动作签发的 Writer Capsule，正文只写：

`draft/正文.md`

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

### Chapter Editor

必须在 Blind Reader 正式记录后创建第三个新 Session。只读取：

- 当前完整正文；
- 当前场景包与用户硬锚；
- 必要 Canon 和上一章末段；
- Blind Reader 结果；
- 有界机器诊断。

独立检查因果、主角主动选择、私人代价、物理连续性、人物知识来源、职业行动、
对白、句子节奏、核心冲突与章末钩子。不得照抄 Blind Reader，也不得直接改正文。

## 自动闭环

1. Python 初始化项目并签发 Writer 规划动作。
2. Lead 创建一个可写的独立 Writer Session，等待规划终态。
3. 同一 Writer Session 复用到外置 Writer Capsule，写出本章正文。
4. Python 导入正文，自动建立技术记录并跑机器门。
5. Python 签发 Blind Reader 动作；Lead 创建新 Session 并等待终态。
6. Blind 记录成功后，Python 才签发 Chapter Editor 动作；Lead 再创建新 Session。
7. 两审都通过时，Python 核验当前正文、三会话隔离、Review、状态和本地 Git，
   然后推进 `ready`。
8. 有开放 MUST 时，Python 合并为一次集中 Patch，创建新的 Patch Writer Session。
9. Patch 只处理 MUST；正文改变后 Python 新建 Generation、标记旧证据 stale，
   再创建两份新的完整双审。
10. 第二版仍有 MUST 时停止自动回炉并让用户选择，不无限循环。

Lead 不写正文、不审稿、不代填结论、不选择模型来源真相，也不直接操作
Generation、Review、状态或 Git。

## 等待与恢复

- 创建成功、accepted、progress、working、idle、available 或文件出现都不是完成。
- 必须使用宿主官方 wait/join/result 机制等待 completed、failed 或 timed_out。
- 角色仍在 working/progress 时继续等待，禁止因 Lead 短超时而越权代做。
- 结果文件缺失、Session 异常或角色实质失败时废弃该 Session，创建同角色新 Session，
  最多自动重试 2 次。
- 失败 Receipt 保留原样，禁止改成 clean；退役 Session 的晚到产物无效。
- Writer 已产生合规正文而交付元数据缺失时，保留正文并由 Python补记；不得重跑 Writer。
- 审稿运输或结果丢失只重开对应审稿角色，不重写正文。
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
- 正文改变必须新建 Generation 和两份 Review；旧记录变 stale，不得改写旧哈希。
- Guardian Receipt、Runtime Audit、Generation 和 Review History 创建后不可覆盖。
- 外置 Guardian 只在 `<root>/.local-guardian/<slug>/`；禁止在书目录内创建。
- 每书 Git 只做本地恢复，不配置 remote，不代表作者批准或发布许可。
- `ready` 代表工作流通过，不代表用户批准。
- 未经用户明确要求，不得 commit、push 或删除实验书。
