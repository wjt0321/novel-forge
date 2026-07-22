# Claude Code Repository Entry

编码任务遵守 `AGENTS.md`。小说写作、续写、审稿、修订或审计任务先读取并严格遵守
`.agents/skills/novel-forge/SKILL.md`；`.claude/skills/novel-forge/SKILL.md`
只是同一正本的镜像。

## 自动生产唯一入口

- 用户要求写作、续写或给出六项小说架构时，首个写操作只能是仓库根目录的
  `python tools/novel-workflow.py ... start`；不得先运行 `init-novel-project`。
- 自动入口未成功启动前，不得自行创建正文、规划、审稿或 ready Git 恢复点。
- 缺少 SessionBackend、独立会话或隔离能力时立即停止，只向用户说明：
  “自动写作环境尚未就绪，本章未开始。”
- `degraded_exploration` 只有用户明确要求探索稿时才允许；不得因工具受限自行降级，
  不得把探索稿称为完成，也不得用单会话模拟三个角色。
