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
- 小说正文是唯一主产品；规划、审稿、Generation、Runtime、Guardian、状态和 Git
  都是服务正文的附属记录，不得因为遥测未知或技术字段缺失要求重写有效正文。
- Python 状态机决定下一步并自动计算哈希、stale、证据绑定和 Git；宿主只负责创建或
  复用独立会话、等待官方终态，并让角色写动作指定的当前书 diff 产物。
- 默认完成命令为 `complete-role <slug>`。日常 Lean 的首个 Writer 动作直接写
  Capsule 内正文；两个审稿角色把简短 JSON 写入动作给出的 `result_file`。Lead 无需
  填写技术表单、拼装会话 ID、Generation、Runtime、Guardian、token、请求数、哈希或 Git 字段。
- 创作角色只允许写当前书 `.novel-forge/diff/chNN/` 内动作指定的单一文件：Writer
  写 `writer/draft/正文.md`，审稿角色写各自 `result_file`。额外书内产物会被清理；
  修改 `app/`、`tools/`、`tests/`、双 Skill、根入口规则、当前书 Guardian/本地 Git
  账本或动作白名单会被恢复并换新会话。
- ACP 只用于事后取证和根因调查，不创建生产会话，不参与 Guardian、ready 或 Git。
- 新书先由确定性控制面通过 `init-novel-project` 初始化；创作角色不得修改书内控制面，
  不得自行创建正式章节、规划、证据、审稿记录或 ready Git 恢复点。只有 Python 在双审
  通过后把 diff 暂存正文晋升到 `chapters/`。
- `NOVEL_FORGE_HARNESS_COMMAND` 只启用可选 headless 命令 Backend，不是交互式
  Skill 的前置条件，也不得成为用户选择题。
- 高权限只属于无模型推理的确定性控制面，用于 Guardian、状态、证据和 Git。
  Lead 只调度；Writer、Blind Reader、Chapter Editor 只产出各自角色产物。
- 必须使用宿主官方 wait / join 等到角色终态；创建成功、已接单、进度消息或文件暂时稳定都不算完成。
- `idle/available` 不是角色结果；必须等待官方 completed/failed/timed_out 终态。
  working/progress 时继续等待，禁止短超时后由 Lead 越权代做。结果文件缺失时换新
  同角色会话自动重试，不由 Lead 代填文学结论。
- 不得创建或注册宿主专用 Agent 类型，不得写入项目或用户级 `.claude/agents`；
  直接使用宿主提供的通用独立 Session、Teams、Task Agent 或 Role 能力。
- 宿主无法创建或等待真实独立角色时立即停止，只向用户说明：
  “自动写作环境尚未就绪，本章未开始。”
- 小说创作任务中的 Lead 和角色不得创建、修改、修复、包装、安装或配置 Harness
  / SessionBackend；headless 缺失时不得自行设置命令桥，也不得向用户提供部署或配置 Harness 的选项。
- `degraded_exploration` 只有用户明确要求探索稿时才允许；不得因工具受限自行降级，
  不得把探索稿称为完成，也不得用单会话模拟三个角色。
- Writer 可在写作过程中做最多 5 次题材常识、事实边界与书名/人名重名检索；不另开
  规划回合、不回传规划表，也不得借此阅读工作流源码。正文与两个审稿角色不得做开放式仓库探索。
- 默认 `lean_native` 由当前书 diff Capsule、书内精确写入检查、轻量代码控制面保护和
  Python 自动记账构成。角色不填 Runtime、哈希、token、请求数或 Git；未知遥测保持
  null。只有明确传入 `--strict-audit` 才启用仓库外一次性 Capsule、完整技术完成信封
  和全仓快照。
