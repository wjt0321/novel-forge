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
  随后 sequence 基于这些真实规划生成 handoff，并 claim 同一个 Writer 会话。
- Writer 只进入仓库外 capsule。默认 capsule 位于系统临时目录，也可由调用方传入
  明确位于仓库外的目录。
- Blind Reader 请求体只含当前正文。
- Chapter Editor 请求体只含当前正文、当前场景包、必要 Canon、本轮盲审结果；
  第 2 章起另含上一章末段，用于提交门禁要求的真实连续性引文。
- 两个审稿会话必须返回各自逐项分析、当前正文逐字引文和真实 verdict。Orchestrator
  只添加当前 binding 与会话来源字段，禁止用同一句正文替代九项盲读重建或五项编辑判断。
- 命令桥通过 `--request <path> --response <path>` 接收内部协议；这些 JSON 不向
  普通用户显示，也不规定模型选择、思考档位或宿主产品。

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
`instructions.md`，只允许处理 MUST。

额外文件、路径逃逸、受保护输入变化、runtime sidecar 缺失或其他 compromised
结果都会触发同一恢复路径：保留失败回执，废弃失败 session，创建新 session 和新
capsule，重新执行。每个写作阶段最多自动重试两次；耗尽后才显示：

1. A. 保留草稿
2. B. 重新生成本章
3. C. 停止任务

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
