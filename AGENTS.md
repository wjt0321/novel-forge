# AGENTS.md

> 面向本仓库的编码 Agent。目标是维护 **S-Black Novel Forge**：一个可审计、可回滚、由作者最终决定的中文长篇小说生产系统。

## 先读这一页

- 正文 Markdown、`books/<slug>/` 的证据和导出 manifest 是长期事实；SQLite 只是可重建索引。
- 系统只验证流程与可定位证据，**不认证文学价值、市场表现、作者批准或发布资格**；`publication_eligibility` 必须为 `False`。
- 不实现真实 LLM 或联网抓取；外部角色只能通过工作流提交正文/审稿结论。
- 默认产品是 books/ 的 `lean_native` 流程；legacy `library/` 仅兼容维护，二者不得混用。
- 日常创作的完整规则见 `docs/43-fiction-first-lean-native-workflow.md`、`docs/44-current-workflow-logic-audit.md`；不要为理解日常一章而先读取历史里程碑文档。

## 运行与测试

本仓库不是可安装包。Python 3.12+，依赖只有 `fastapi`、`uvicorn`、`pydantic`、`pytest`。

```powershell
pip install -r requirements.txt
$env:PYTHONPATH='.'; python -m pytest tests/ -q
# 人类 CLI
$env:PYTHONPATH='app'; python -m novel_forge.cli init-novel-project my-novel --title '我的小说' --genre '都市'
# 面向用户的自动写作入口
python tools/novel-workflow.py --root D:/s-black-novel start <slug> --title ... --genre ... --protagonist ... --world ... --conflict ... --hook ...
python tools/novel-workflow.py --root D:/s-black-novel next-action <slug>
python tools/novel-workflow.py --root D:/s-black-novel complete-role <slug>
```

`next-action` 默认输出简明角色交接卡；仅宿主程序集成使用 `next-action --json`。后续章节可用 `start <slug> --chapter N` 复用已保存的书籍元数据。

## 代码地图

`cli/api/skill_adapter -> service -> repository -> db` 是 legacy 主链。books/ 前台工作流主要在：

- `native_relay.py`：日常原生会话接力、暂存正文、动作与恢复；
- `workflow.py`：编排器、用户 CLI；
- `guardian.py`：Writer capsule、CAS 晋升、回执；
- `book_project.py`、`book_gates.py`、`book_git.py`：状态、门禁、本地恢复历史；
- `book_memory.py`：每书 Markdown Canon 与可重建索引；
- `planning_spec.py`：章节状态、角色与场景包规则的唯一来源；
- `review_prompt.py`、`writer_prompt.py`：有字符预算的角色提示词；
- `workflow_iteration.py`、`workflow_observability.py`：P0/P1/P2 Writer 包、局部 Patch、能力/风险/预算策略与本地成本观测。

修改 books/ 状态、场景包、审稿角色或必填小节时，只改规则单源并补相应测试。代码注释/docstring 英文；面向作者的文档和两份 Novel Forge Skill 主要中文。

## 日常 Lean 工作流（唯一默认路径）

`Lead 分发 -> Writer 暂存正文 -> Blind Reader -> Chapter Editor -> 至多一次集中 Patch -> 双审 -> Python 晋升 -> ready`

1. `start` 初始化项目并由 Python/宿主适配器签发当前唯一角色动作；Lead 只发起任务、展示薄状态和转交作者决定，不读取或解释状态机。
2. 初稿/结构修订 Writer 只写 `books/<slug>/.novel-forge/diff/chNN/writer/draft/正文.md`；局部 Patch Writer 只写动作指定的 `local-patch/replacements.json`，Python 做精确替换。Writer 默认只读 capsule 的 `writer-context.md` P0/P1/P2 包；正式章节至少 **5000 个 CJK**。正文禁止提示词、工作流标记、控制面语言、破折号、省略号与否定翻转机械句。
3. Blind Reader 只读当前暂存正文，写紧凑结论；必须给 `human_likeness`、`reader_desire`、余味、追读钩子和原文引句。Chapter Editor 只写 `pass|needs_revision`、完整 MUST、摘要和引句。
4. 审稿角色只能写动作给定的 `result_file`；Lead 等待宿主官方 completed/failed/timed_out，再执行 `complete-role`。创建、accepted、progress、idle、available 或文件出现都不等于完成。
5. 全部开放 MUST 都是 `local` 且可唯一定位时，优先局部 replacement；否则回到同一暂存正文集中修订。两条路径都在修订后重跑全章硬检与双审；第二版仍有 MUST 时进入用户决定，禁止无限循环。技术运输失败只重开当前角色，Writer 已产生的合规正文不得因元数据或遥测缺失而重写。
6. 双审通过前不得创建正式章节、Generation、Guardian Receipt、Review History 或 draft Git checkpoint。Python 才能 CAS 晋升、记录证据、推进 `ready`、创建本地 Git checkpoint。
7. `ready` 不等于作者批准。第 N 章完成后，`next-action` 会明确交接到第 N+1 章；不得把“没有角色动作”解释成自行改 state 或补造证据。

8. 同卷 SHOULD 固定主要 Writer 模型；`--writer-model` 变化必须先由作者用 `approve-writer-model` 记录小样校准。`native-isolated`/`managed-relay` 可正式生产；`exploration` 永远不能 formal ready。卷首卷末、重大转折、角色生死和核心揭示在双审通过后仍需 `approve-high-risk`。硬预算只阻断后续自动追加 Patch/复审调用，不取消首轮双审或放过质量问题。

日常角色只需要作品任务和 capsule 路径。模型、Session、Guardian、Runtime、Git、哈希、表格与技术表单属于 Python 控制面；未知遥测保持 `null`，不得让创作角色猜测、补填或绕过它们。`--strict-audit` 只用于明确审计/基准实验。

## 文件与安全边界

- 禁止直接修改 `data/novel-forge.db`、`library/<slug>/manuscript/revisions/`、`books/<slug>/.novel-forge/index.sqlite3`、`planning/chapter-sequences/*.json`、`planning/guardian-sessions/*.json`、`.local-guardian/`、不可变 `evidence/`。通过 `NovelForgeService`、`book_project`、Guardian 或 `skill_adapter` 操作。
- `books/<slug>/.novel-forge/diff/chNN/` 是唯一临时区；正式 `chapters/eNN/ch-NN/正文.md` 只能由 Python 晋升。Canon 新信息先 candidate 后 promotion。
- 创作角色禁止修改 `app/`、`tools/`、`tests/`、根规则、两份 Skill、其他书、控制面或 Harness；不得创建、注册、修改或安装宿主专用 Agent 类型、`.claude/agents`、SessionBackend 或 `NOVEL_FORGE_HARNESS_COMMAND`。
- 不提供硬删除；若用户要求彻底删除实验书，先保存允许保留的脱敏聚合证据，再一起删除 `books/<slug>/`、`.local-book-git/<slug>.git`、`.local-guardian/<slug>/` 三个已验证绝对路径。
- 每书 Git 只做本地恢复，禁止 remote/push；主仓库未经用户明确要求不得 commit/push。
- API 与 adapter 不返回正文全文；adapter 的 `--root` 必须为绝对路径，变更操作需要 `--confirm`。

## 测试与文档

- 从根目录使用 `PYTHONPATH=.` 跑 pytest；修改状态机、门禁、提示词或 recovery 必须写回归测试，并先跑定向测试再跑全量测试。
- `books/` 工具必须是 `lint.py`/`book_gates.py` 的薄壳；模板不得复制规则。
- 当前行为变化优先同步 `docs/43-*`、`docs/44-*`、`docs/45-*` 或三份聚焦 reference；不要再为每次里程碑新增编号文档。完成的一次性计划/实验只把耐久结论补入 `docs/archive/history.md`。`.agents/skills/novel-forge/SKILL.md` 是 canonical，`.claude/skills/novel-forge/SKILL.md` 必须逐字节镜像。
