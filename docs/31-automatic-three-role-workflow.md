# 自动三角色小说工作流

## 目标

本里程碑在现有 books/、Skill adapter、Guardian、章节序列、证据、状态机和每书
本地 Git 之上增加轻量编排层。它不建立平行正文源，也不让 Lead 代替 Writer、
Blind Reader 或 Chapter Editor。

用户只提交六项架构信息：书名、题材、主角、世界观、本章核心冲突和章末钩子。
`app.novel_forge.workflow.NovelWorkflowOrchestrator` 只负责编排、校验和落盘，不
创作规划内容，也不代填审稿结论。当前 Writer 会话先根据六项输入产出正式规划材料，
同一会话再进入隔离 capsule 写正文。随后执行：

`Writer -> machine gates -> Blind Reader -> Chapter Editor -> optional Patch Writer -> re-review -> ready -> sequence complete -> Git checkpoint`

## 会话与上下文

- 工作流核心是厂商无关的 `SessionBackend` 能力协议，不绑定 Claude Code、Codex、
  Teams、DeepSeek 或任何其他产品/模型。宿主只需提供“创建真实独立会话、运行角色、
  返回真实来源信息和标准 runtime”四项能力。
- `CommandSessionBackend` 与 `NOVEL_FORGE_HARNESS_COMMAND` 是通用命令桥参考实现，
  不是架构依赖；支持项目级 Skill 的宿主也可以直接实现同一能力协议。
- Writer、每次 Patch、Blind Reader 和 Chapter Editor 都由外部 Harness 创建新的
  原生会话；三个当前角色会话必须互不相同。
- 初始 Writer 先执行 `phase=planning`，返回允许列表内的 `worldbuilding.md`、
  `research-boundaries.md`、`story-engine.md` 和当前章 scene package。Orchestrator
  只校验路径、必需文件和非空内容后落盘，不补写人物欲望、错误模型、物象或主题。
  随后 sequence 基于这些真实规划生成 Writer Story Brief，并 claim 同一个 Writer
  会话。完整 Scene Package 是编辑控制面；Writer handoff 只保留边界、场景压力、
  在场者状态、Beat 因果、信息预算和场景余波，不传决策问题、替代解释、可证伪假设、
  因果归属或专业判断审计。
- Writer 只进入仓库外 capsule。默认 capsule 位于系统临时目录，也可由调用方传入
  明确位于仓库外的目录。
- Blind Reader 请求体只含当前正文。
- Chapter Editor 请求体只含当前正文、当前场景包、必要 Canon、本轮盲审结果；
  机器诊断只作为编辑定位信息；第 2 章起另含上一章末段，用于提交门禁要求的真实
  连续性引文。
- 两个审稿会话必须返回各自逐项分析、当前正文逐字引文和真实 verdict。Orchestrator
  只添加当前 binding 与会话来源字段，禁止用同一句正文替代九项盲读重建或五项编辑判断。
- 命令桥通过 `--request <path> --response <path>` 接收内部协议；这些 JSON 不向
  普通用户显示，也不规定模型选择、思考档位或宿主产品。
- 编排器只声明厂商无关的执行档位：规划和困难因果核验使用 `high`，正文与默认
  双审使用 `medium`。宿主负责把档位映射到自己的模型能力；没有对应档位时必须
  如实降级，不得伪造模型或 thinking 深度。

## 文学收敛

- Writer 把 Story Brief 当作后台义务，不得在正文中逐项证明规划。正文允许人物
  误判、遗漏、自欺和延迟反应；谜题不必在出现时立刻完成分类和解释。
- 高压对白按人物位置、身体受力、回应关系和权力变化判断。纯对白不是天然错误，
  不设置固定句数，也不为躲规则机械插入动作。
- Blind Reader 除空间、身体、限制、情绪、对白与可记忆画面外，还必须识别整齐
  问答、替代解释枚举、职业能力证明、控制面语言和局部修补接缝。谜题成立不等于
  真人愿意追读。
- Chapter Editor 每轮都重新完成因果、人物能动性、对白信息流、句子肌理和连续性
  五项审查，不得只核对上一轮 finding 是否被删除。
- MUST 会被编译成“位置、原文证据、读者效果、修订意图”四段式 Patch 指令。Patch
  必须最小但因果完整，保留未受影响的有效正文；不得把 finding 直接改写成解释段。

## 不可变记录

- generation 继续经 `record_evidence` 原子落盘；相同正文不能重复记 generation。
- runtime audit 继续以 writer 原生 session ID 为不可变文件名。
- Guardian clean/compromised receipt 继续同时写入书内公开副本和
  `.local-guardian/<slug>/` 外置权威副本，失败回执不得改写为 clean。
- 每次 `record_review` 都先写入 `reviews/history/review-*.md` 不可变历史，再更新
  顶层 canonical review 投影。`project-status.review_history` 根据当前正文与规划
  绑定计算 stale，不修改旧记录。

## 自动修订与故障恢复

两份审稿的开放 MUST 会合并为一次有界 Patch。章节序列把通过 Guardian 的初稿
writer 正常记为 retired，再要求新的 Patch Writer session；Patch 指令写入受保护
`instructions.md`，只允许处理 MUST。Patch 后必须重新全文运行两份审稿，不得只
检查旧 finding。

额外文件、路径逃逸、受保护输入变化、runtime sidecar 缺失或其他 compromised
结果都会触发同一恢复路径：保留失败回执，废弃失败 session，创建新 session 和新
capsule，重新执行。每个写作阶段最多自动重试两次；耗尽后才显示：

1. A. 保留草稿
2. B. 重新生成本章
3. C. 停止任务

第二份不同正文仍有 MUST 时，系统退役 Patch Writer 并持久化真实
`decision_required`。用户选择 B 本身构成明确回炉决定；系统为第三版创建新的 Writer
session，签发绑定当前章节、该 session 和前两版正文的 regeneration authorization，
再执行完整双审。用户没有选择 B 时不得自动产生第三版。

## 成本边界

- 默认每章一次规划、一次正文、每轮两次审稿。
- 自动文学修订最多一次集中 Patch；不会为每条 MAY 或 advisory 单独调用模型。
- 默认审稿不增加第四、第五角色；只有 Chapter Editor 指出具名专业风险时才按需
  调用一个专业角色。
- 第三版必须经过用户明确选择，因此不会在无人确认时继续消耗生成预算。
- Guardian、哈希、状态、Git 和证据校验全部在本地执行，不占模型上下文。

## 宿主接入

支持 Novel Forge Skill 的 Agent/Harness 应直接复用本书的 Skill、adapter、
Harness Contract、Guardian Contract 和 `SessionBackend` 语义，使用宿主自己的
原生新会话能力。模型和工具由宿主或用户选择，工作流不作枚举，也不保存默认组合。

仅当宿主需要进程桥时才设置：

```powershell
$env:NOVEL_FORGE_HARNESS_COMMAND = "your-harness-command"
```

## 用户入口

```powershell
python tools\novel-workflow.py --root D:\mydev\s-black-novel start demo `
  --title "书名" `
  --genre "题材" `
  --protagonist "主角" `
  --world "世界观" `
  --conflict "本章核心冲突" `
  --hook "本章结尾钩子"

python tools\novel-workflow.py --root D:\mydev\s-black-novel status demo
python tools\novel-workflow.py --root D:\mydev\s-black-novel retry demo
python tools\novel-workflow.py --root D:\mydev\s-black-novel stop demo
```

命令行只输出“正在写作”“正在自动审稿”“发现问题，正在自动修订”“写作会话异常，
已自动换新会话重试”和章节完成/人工选择提示。内部异常不会直接显示 JSON、哈希、
会话 ID、Guardian、Git 或 traceback。

`ready` 仍不代表作者批准、文学价值认证或发布许可。
