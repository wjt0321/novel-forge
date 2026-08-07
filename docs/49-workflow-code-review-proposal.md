# 49 — 工作流代码审查与改进方案（2026-08-07）

> 性质：只读审查 + 改进方案，**不含任何源代码改动**。审查方式为 5 路并行静态通读（`native_relay.py`、`workflow.py`、`book_project.py`、`guardian.py`、提示词/门禁/纹理模块、docs/43–48），关键结论已对行号交叉核验。所有"可复现性"基于代码路径推演，动手修前建议先写定向失败测试复现。

## 0. 总评

- 系统初衷（正文优先、控制面收进 Python、双审不放松、作者独享批准权）在架构上是成立的；44 号审计的 7 项缺陷、45 号 A–F、46 号 K1–K8 经 47 号全部落地，方向正确。
- 但当前仍有三类问题：**(a) 若干条失败/重试路径存在真实死锁与审查性漏洞**；(b) 每章约 25% 的输入 token 是可砍的重复/超发注入；(c) 对"修辞层 AI 味"（排比、情绪直陈、格言收尾、视角泄漏）事实上零拦截，门禁火力集中在机械符号层。
- 三个问题都可以在不改架构、不破坏既有规则单源的前提下解决。

---

## 1. 工作流漏洞与 bug（按严重度）

### P0-1：硬门禁失败在 lean 模式下无出口，章节死锁
- 5000-CJK/段落数硬门只在 `advance_state("surface_checked"/"ready")` 内抛出（`book_project.py:1132-1155, 1232-1238`），而 `complete_role` 的恢复异常元组不含 `BookProjectError`（`native_relay.py:2644`）。
- 后果链：state 停在 `awaiting_double_review` → `next-action` 误报"双审角色卡均已签发"（`native_relay.py:2171`）→ `retry` 要求 decision 态不可用 → 重跑 complete 触发恢复重签双审 → 门禁再炸 → 耗尽后进 `decision_required("native_role_failed")` → 该 kind 不在 `REVISION_DECISION_KINDS`（`workflow.py:77-82`），`authorize-revision` 拒绝。**短章（<5000 CJK）在 lean 下没有任何出路。**
- 同类死锁：`surface_revision_required`（`native_relay.py:3434-3446`）也不在可授权 kind 内；`git_checkpoint_failed` 的"A 保留草稿"选项没有任何命令实现（`workflow.py:2505`），作者除 `stop` 外无路可走。
- **方案**：把门禁失败路由为可授权决策（`literary_revision_required` 或新增 `hard_gate_failed` 加入 `REVISION_DECISION_KINDS`）；`complete_role` 的恢复元组纳入 `BookProjectError`；给三个死锁各写一条回归测试（短章、表面修订耗尽、checkpoint 失败）。

### P0-2：晋升先于审稿记录校验，违反"双审通过前不得创建正式章节"
- `_finalize_staged_chapter`（`native_relay.py:4517-4524`）先 `_promote_staged_writer`（写正式 `chapters/eNN/ch-NN/正文.md` + Generation + Guardian receipt + draft git checkpoint），**之后**才 `_record_native_review` → `record_review` 校验。校验失败时正文与证据已落盘。
- **方案**：调整顺序为"审稿校验通过 → 晋升"；或晋升先写临时区、校验通过后原子转正。

### P0-3：`uncertain+pass` 被硬拒，与文档/提示词契约直接冲突
- `book_project.py:646-654`：blind-reader `pass` 必须 `human_likeness=convincing`，`reader_desire` 必须 `continue`；代码错误文案写明"uncertain/synthetic 应给 needs_revision"。而 docs/43 与 `review_prompt.py:97` 说"uncertain 默认不触发修订"。
- 后果：Blind Reader 按提示词给出合法的 uncertain+pass → 校验拒绝 → 走 repair/重试循环，逼着审稿模型把不确定说成确定（反而奖励"敢下结论"，惩罚诚实）。
- **方案**：二选一并文档对齐——要么接受 uncertain+pass 放行（符合文档），要么把"uncertain 必须 needs_revision"写进提示词与 docs/43（符合代码）。考虑到"uncertain 豁免"本身就是放水口（见 §3），建议采后者并配合 §3-3 的"uncertain 必须给具体说明"。

### P1-1：控制面合成 session id 冒充真实宿主会话，会话隔离检查形同虚设
- `_control_session()`（`native_relay.py:1801`）生成 `relay-{role}-chNN-<uuid>` 合成 id；`complete_minimal`（`:995-1006`）只要 `control_run_id` 存在就**无条件覆盖宿主 CLI 传入的 `--session-id`**。
- 后果：三会话互异校验（`book_project.py:1216-1226`）、`_assert_fresh_session` 被合成 id 平凡满足——同一真实宿主会话跑 Writer+双审也能 `ready`；Guardian receipt / session-completions 全绑合成 id，无法与宿主真实会话对账。这违背"未知遥测保持 null"与 docs/43 的会话隔离语义，是**审查性漏洞**。
- 连带：patch 轮复用原 writer 的 `control_run_id`（`native_relay.py:4477`），两轮 Writer 在记录里不可区分。
- **方案**：`control_run_id` 只作控制面关联键，不进入 `session_id` 语义；宿主真实 `--session-id` 照常记录，缺失保持 null 而非合成填充。

### P1-2：并行双审的 repair/恢复路径可能选错角色、作废已完成审稿
- `_request_completion_repair` / `_recover_technical_failure` 在 `awaiting_double_review` 用 `_phase_role`（"第一个未完成的 pending 角色"）兜底；repair 次数耗尽路径不设置 `failed_review_role`（`native_relay.py:2753-2757`）→ 可能重签已完成的一方并 `discard` 其结论。
- 另有 `state.json` 读-改-写无锁竞态：两个并发 `complete_role` 可能丢失一方的 `blind_outcome`/`completed_review_roles`。
- **方案**：repair 计数与 repair 卡绑定具体角色（而非 phase 兜底）；`state.json` 写入前 reload-合并或加文件锁；`complete_minimal` 不领卡直接 complete 时强制要求 `--role`（现在会固定解析成 blind-reader，`native_relay.py:964-985`）。

### P1-3：Writer 晋升后技术重试会因缺授权直接炸
- target 已存在后 `prepare_writer_capsule` 按 patch 语义要求 `human_decision_reference`（`guardian.py:426-430`），而 lean 自动重签路径不设它（`native_relay.py:3336-3348`）→ 恢复处理器内部再抛 GuardianError，自动重试失效。
- **方案**：lean 重签区分"同版本重写"与"新版本 patch"，前者不需要作者授权；或自动重试失败时路由为作者决策而非裸抛。

### P2（低优先级，记录备查）
- Writer 完成不校验会话新鲜度（缺 `_assert_fresh_session`，`native_relay.py:3498-3504`）。
- 头less 路径与 lean 契约不一致：`CommandSessionBackend.run_review` 无 pass→`ready_for_editor_decision` 映射（`workflow.py:824-925`）；lean 集中修订在 guardian 层恒为 draft 语义、无 `no_content_change` 检查。
- 死代码/死配置：`workflow.py:3381` 的 stop 分支不可达；`planning_spec.py:212-219` 映射到不存在的 `specialist_reviewed` 状态；`SPECIALIST_REVIEW_ROLES` 无消费方。
- `retry` 文案与行为不符（只重发审稿卡，却报"正在重新生成本章"）。

---

## 2. 轻量化方案（保留现有逻辑）

**原则：砍冗余承载，不动状态机与门禁语义。**

1. **裁掉头less 编排链（最大减负项）**。`workflow.py` 的 `SessionBackend`/`CommandSessionBackend`/`_UnavailableBackend` 及 orchestrator 的 start/retry/authorize/stop 全套仅被 harness 测试使用（`NOVEL_FORGE_HARNESS_COMMAND`），lean 只借用其中约 15 个私有方法。这条链与 lean 存在上文 P2 所列契约漂移，维护成本大于收益。方案：把 lean 实际调用的私有方法下沉为独立 helper 模块，头less 链整体移入 legacy 或删除（连同 `role_completion.py`）。
2. **合并 native_relay 内的重复块**：三处"规划→序列→推进"逐行重复（`:2012-2036, :2380-2426, :3093-3121`）；四套角色契约/模板可合成一张表；`_request_staged_literary_patch` 与 `_prepare_lean_writer_action` 的 action 构造可抽公共 builder。预计 `native_relay.py` 可瘦身 15–20%。
3. **收敛快照频率**。`_write_action` 每次签发写全仓库快照+zip，每次 completion 又重做（`native_relay.py:676-692, 1522-1535`），一章 10+ 次全仓哈希+打包，而 app/tools/tests 在角色执行期不变。方案：每章一次控制面快照 + 动作间仅做哈希比对，zip 只在晋升与决策点打。
4. **去重复定义**：`workflow.py:205-223` 的 `REVIEW_ANALYSIS_FIELDS` 与 `book_project.py:92-112` 的字段清单重复，收到 planning_spec 单源。
5. **chapter_sequence 的多章能力**（`MAX_CHAPTERS_PER_SEQUENCE=4`，lean 恒为 1）可以保留接口但不再扩展；不建议现在删，避免牵动 47 号已落地的并行逻辑。

---

## 3. Token 压缩方案（可量化）

每章 happy path 基线约 **34K tokens**（输入 ~26K + 输出 ~8K，实测口径：5000 CJK ≈ 6200 chars ≈ 0.75 char/token）。压缩点按收益排序：

| # | 位置 | 现状 | 方案 | 每章省 |
|---|---|---|---|---|
| A | Editor 的 canon 注入（`native_relay.py:2842-2845`） | 原始记录文件拼盘后 `[:12000]` 截断，单条 535 chars（439 是 JSON 元数据），且按文件名截断会切掉最新的、往往最相关的事实 | 复用已存在的 `build_context_packet` 压缩行格式（单条 75 chars，7.1x），装 hard/active + 到期承诺 | **~7.7K** |
| B | Editor 的 scene_package（`:2813-2815`） | 全量无界注入，含 1d/1e/3c/5b 编辑审计节（提示词明令不得作证据） | 复用 `WRITER_VISIBLE_SCENE_SECTIONS`（`planning_spec.py:110-121`）只给对照节 | ~0.8K |
| C | Editor 的上一章结尾（`:2863-2870`） | 最后 20%（~1300 chars） | 最后 10–12%（~700 chars），连续性核对只需末段行动与钩子 | ~0.45K |
| D | story-contract 与 scene 0a 逐字重复（`:2838-2841`） | 双份 440 chars | 二选一 | ~0.15K |
| E | Writer P0 的 0b 节带上一章 SHA/路径 | ~150 chars，写作者用不到 | 只留 48 字引句 | ~0.1K |

**合计 ~9.2K tokens/章，约占全章 25%、输入侧 35%。** 且每多一轮复审/技术重试，Editor 输入的 ~10K 就重复一次，实际节省随重试放大。

另外两个结构性问题：

- **风险敞口 F（不省当前 token，消最坏情况）**：minimal 模式下 handoff.md（≤28K chars）仍随 Writer capsule 落盘（`guardian.py:501`），指令虽要求只读 writer-context.md，但模型一旦误读，单次 Writer 调用膨胀 ~18K tokens——是 A–E 总和的 2 倍。方案：minimal 模式 handoff.md 移出 capsule 目录，Guardian 校验改指原路径哈希。
- **P1 "直接 Canon" 是空槽**：`workflow_iteration.py:198` 读 `memory/characters.md`/`memory/canon.md`，但模板（`project_templates.py:1593-1598`）从不创建这两个文件——真正的 canon 记录完全没给 Writer。要么换源注入 hard/active 压缩视图（顺带修复"Writer 看不到 canon"的质量问题），要么删掉空槽。
- **观测层无需动**：`record_call_observation` 只存标量与哈希，无正文全文，不回流路由，是干净的。

IO 侧（不花 token 但拖慢每章）：`project_status` 每次全量 `run_gates` + `analyze_serial_style`，ready 路径上重复 4–6 次，累计 O(N²) 随章节数恶化；可加章节级缓存（输入哈希不变则复用结果）。

---

## 4. 回归初衷：降低 AI 味的方案

实测构造一段集齐典型 LLM 网文特征的文本（"她不知道的是""命运的齿轮""时间仿佛凝固""不仅是…更是…""那些A，那些B，那些C""说不清道不明的复杂情绪""所有的相遇都是久别重逢"），`lint_text` **0 blocking、0 advisory**，`literary_texture` 判 low risk。即：**机械层（破折号/省略号/否定翻转/元数据泄漏）拦截有效，修辞层拦截近乎为零。**

以下按性价比排序，全部不动架构：

1. **分句级排比/复沓检测（最高性价比）**。`mechanical-triplet` 目前只作用于段首句子级（`lint.py:346-388`），扩展到逗号分句级，抓"那些A，那些B，那些C""X了，X得让人Y"；`not-is-flip` 正则补"不仅/不仅仅/不只是…而/更/而是"变体（`lint.py:110` 现只匹配"不是X而是"）。要求 3 连以上触发，误报可控。
2. **让 advisory 真正进审稿输入**。现在 lint advisory 只躺在 CLI 报告里，Editor 只收到 160 字 texture hint 且被提示词明令"不得据此单独判错"。方案：把 `explanation-tic/rhythm-monotony/mechanical-triplet/simile-density` 聚合压缩成 ≤400 字注入 Chapter Editor，语义沿用"不作单独判错依据，但需核对是否遍布全章"——与 Editor 现有职责天然契合。Blind Reader 保持 prose-only 不变（隔离是双审互补的根基）。
3. **收紧 uncertain 豁免**。配合 §1 P0-3 的契约统一：uncertain 允许存在，但 pass 必须 convincing；且 uncertain 必须用一句具体说明（"哪段像通用/工整"）支撑，说明为空则结果无效。零循环风险，只逼出理由，堵死"好读但平庸可无限期 uncertain"的灰色地带。
4. **补漏规则（小成本正则）**：explanation-tic 或新 advisory 加入"她不知道的是/没人知道/命运的(车轮|齿轮|轨迹)/时间仿佛(凝固|静止)/空气中弥漫着/说不清道不明"；`simile-density` 去掉 <500 字早退（`lint.py:612`）；`literary_texture` n-gram 窗口下探到 2–3 字（抓"沉默……沉默"式复沓）。
5. **MUST 的 evidence 逐字校验**：复用 `_quote_matches`（`native_relay.py:4104`）对每条 MUST 的原文证据做存在性检查，堵编造引文（现在只校验主 evidence_quote）。
6. **压制"为过关补解释段"**：实验记录中 Editor 自曝补丁稿出现"为关闭审稿问题而补写的解释段"。在 patch 指令加一条硬约束：新增因果必须落进动作/停顿/物件后果，禁止新增解释性段落（`writer_prompt.py:52-58` 已有雏形）。

需要坦白的一点：规则层能把"修辞层 AI 味"从零拦截提升到"有抓力"，但双审仍是同类模型自评，`human_likeness` 本质是自报字段，门禁只能校验"报告形态自洽"而非"判定属实"。真正兜底仍是作者——这与系统"作者是唯一最终批准者"的初衷一致，不应假装机器能替代。

---

## 5. 落地优先级建议

| 阶段 | 内容 | 理由 |
|---|---|---|
| 第一步 | §1 的 P0-1/P0-2/P0-3 三个死锁与顺序漏洞，各配一条先失败的回归测试 | 用户真实踩中即丢章或死局，且修法局部 |
| 第二步 | §3 的 A（Editor canon 压缩视图）+ F（handoff 移出 capsule） | 收益最大、复用已有格式，无新设计 |
| 第三步 | §4 的 1/2/3（排比检测、advisory 注入 Editor、uncertain 收紧） | 提示词/规则层改动，不碰状态机 |
| 第四步 | §1 的 P1（session id 语义、并行 repair 健壮性） | 审查完整性，需要更谨慎的测试设计 |
| 第五步 | §2 轻量化（头less 链裁撤、快照收敛） | 收益是维护性，可与日常开发穿插 |

每步遵循仓库惯例：先定向测试复现 → 最小改动 → 定向测试转绿 → 全量 pytest → 同步 docs/43/44 与 AGENTS.md（若触及规则单源）。

## 6. 明确不做的

- 不改 `publication_eligibility=False`、`author_approval=False`、≥5000 CJK、双审、至多一次集中 Patch 等不变量。
- 不引入"模型分析自动写 canon"；不新增启发式实体一致性检测器（46 号已评估，误报风险大于收益）。
- 不把 `authorize-revision` 扩成无限重试。
- 不为省 token 默认跳过复审（45 号已明确的非目标）。
