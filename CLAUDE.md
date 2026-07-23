# Claude Code Repository Entry

编码任务遵守 `AGENTS.md`。小说写作、续写、审稿、修订或审计任务先读取并严格遵守
`.agents/skills/novel-forge/SKILL.md`；`.claude/skills/novel-forge/SKILL.md`
只是同一正本的镜像。

## 自动生产唯一入口

- 默认使用当前宿主原生的独立 Roles / Teams / Task Agent / Session，Lead 按 Skill
  调度、等待并回收产物；原生角色可用时不得因命令 Backend 缺失而停止。
- Python 状态机决定下一步；宿主只负责创建、等待和回传。Lead 不写正文、审稿、
  evidence、状态或 ready，也不从缺失结果中补造完成态。
- 创作角色对项目仓库零写入：Writer 只写仓库外 capsule 的 `draft/正文.md`，
  规划和审稿只返回结构化结果。额外项目产物会被清理并换新会话。
- ACP 只用于事后取证和根因调查，不创建生产会话，不参与 Guardian、ready 或 Git。
- 新书先由确定性控制面通过 `init-novel-project` 初始化；创作角色不得直接写
  `books/`，不得自行创建正文、规划、审稿或 ready Git 恢复点。
- `python tools/novel-workflow.py ... start` 是可选 headless 命令入口；
  `NOVEL_FORGE_HARNESS_COMMAND` 只用于可选 headless，不是交互式 Skill 的前置条件。
- 高权限只属于无模型推理的确定性控制面，用于 Guardian、状态、证据和 Git。
  Lead 只调度；Writer、Blind Reader、Chapter Editor 只产出各自角色产物。
- 必须使用宿主官方 wait / join 等到角色终态；创建成功、已接单、进度消息或文件暂时稳定都不算完成。
- 保存宿主返回的 `operation_handle.kind/value`，按 kind 使用对应官方结果通道；不得
  把 agent ID 猜成 task ID。`idle/available` 不是角色结果，completed 还必须带
  角色绑定的 `role_result`。结果缺失时换新同角色会话自动重试，不由 Lead 代填。
- 宿主无法创建、隔离或等待真实独立角色时立即停止，只向用户说明：
  “自动写作环境尚未就绪，本章未开始。”
- 小说创作任务中的 Lead 和角色不得创建、修改、修复、包装、安装或配置 Harness
  / SessionBackend；headless 缺失时不得自行设置命令桥，也不得向用户提供部署或配置 Harness 的选项。
- `degraded_exploration` 只有用户明确要求探索稿时才允许；不得因工具受限自行降级，
  不得把探索稿称为完成，也不得用单会话模拟三个角色。
