# Claude Code Repository Entry

编码任务遵守 `AGENTS.md`。小说写作、续写、审稿、修订或审计任务先读取并严格遵守
`.agents/skills/novel-forge/SKILL.md`；`.claude/skills/novel-forge/SKILL.md`
只是同一正本的镜像。

## 自动生产唯一入口

- 小说创作任务禁止先探索 `app/`、`tests/`、`docs/`、Git 历史或旧实验书。首个写
  操作必须是 `python tools/novel-workflow.py ... start`，随后只执行 Python 签发的
  `next-action`，等待宿主官方终态，再用 `complete-role` 回传。
- 没有命令 Backend 时 `start` 自动进入原生会话 Relay；宿主 Roles / Teams /
  Task Agent / Session 只负责上下文隔离、角色执行、等待和回传。
- Python 状态机决定下一步；宿主只负责创建、等待和回传。Lead 不写正文、审稿、
  evidence、状态或 ready，也不从缺失结果中补造完成态。
- 创作角色对项目仓库零写入：Writer 只写仓库外 capsule 的 `draft/正文.md`，
  规划和审稿只返回结构化结果。额外项目产物会被清理并换新会话。
- ACP 只用于事后取证和根因调查，不创建生产会话，不参与 Guardian、ready 或 Git。
- 新书先由确定性控制面通过 `init-novel-project` 初始化；创作角色不得直接写
  `books/`，不得自行创建正文、规划、审稿或 ready Git 恢复点。
- `NOVEL_FORGE_HARNESS_COMMAND` 只启用可选 headless 命令 Backend，不是交互式
  Skill 的前置条件，也不得成为用户选择题。
- 高权限只属于无模型推理的确定性控制面，用于 Guardian、状态、证据和 Git。
  Lead 只调度；Writer、Blind Reader、Chapter Editor 只产出各自角色产物。
- 必须使用宿主官方 wait / join 等到角色终态；创建成功、已接单、进度消息或文件暂时稳定都不算完成。
- 保存宿主返回的 `operation_handle.kind/value`，按 kind 使用对应官方结果通道；不得
  把 agent ID 猜成 task ID。`idle/available` 不是角色结果，completed 还必须带
  角色绑定的 `role_result`。结果缺失时换新同角色会话自动重试，不由 Lead 代填。
- 宿主无法创建或等待真实独立角色时立即停止，只向用户说明：
  “自动写作环境尚未就绪，本章未开始。”
- 小说创作任务中的 Lead 和角色不得创建、修改、修复、包装、安装或配置 Harness
  / SessionBackend；headless 缺失时不得自行设置命令桥，也不得向用户提供部署或配置 Harness 的选项。
- `degraded_exploration` 只有用户明确要求探索稿时才允许；不得因工具受限自行降级，
  不得把探索稿称为完成，也不得用单会话模拟三个角色。
- Writer 规划阶段可做最多 5 次题材常识、事实边界与书名/人名重名检索；不得借此
  阅读工作流源码。正文与两个审稿角色不得做开放式仓库探索。
- 默认 `formal_native` 由外置 Capsule、零项目写入、全仓前后快照和 Guardian
  构成；真实 OS 沙箱只会透明升级为 `formal_sandboxed`，不询问用户 A/B。
