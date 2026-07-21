# 自动三角色小说工作流

## 目标

本里程碑在现有 books/、Skill adapter、Guardian、章节序列、证据、状态机和每书
本地 Git 之上增加轻量编排层。它不建立平行正文源，也不让 Lead 代替 Writer、
Blind Reader 或 Chapter Editor。

用户只提交六项架构信息：书名、题材、主角、世界观、本章核心冲突和章末钩子。
`app.novel_forge.workflow.NovelWorkflowOrchestrator` 自动补齐最小正式规划材料，
然后执行：

`Writer -> machine gates -> Blind Reader -> Chapter Editor -> optional Patch Writer -> re-review -> ready -> sequence complete -> Git checkpoint`

## 会话与上下文

- Writer、每次 Patch、Blind Reader 和 Chapter Editor 都由外部 Harness 创建新的
  原生会话；三个当前角色会话必须互不相同。
- Writer 只进入仓库外 capsule。默认 capsule 位于系统临时目录，也可由调用方传入
  明确位于仓库外的目录。
- Blind Reader 请求体只含当前正文。
- Chapter Editor 请求体只含当前正文、当前场景包、必要 Canon 和本轮盲审结果。
- `NOVEL_FORGE_HARNESS_COMMAND` 指向厂商无关 Harness 命令。命令通过
  `--request <path> --response <path>` 接收内部协议；这些 JSON 不向普通用户显示。

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

## 用户入口

```powershell
$env:NOVEL_FORGE_HARNESS_COMMAND = "your-harness-command"
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
