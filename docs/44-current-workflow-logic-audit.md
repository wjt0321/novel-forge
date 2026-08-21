# 44. 现行工作流逻辑审计

日期：2026-07-29

## 审计目标

本轮审计只回答一个问题：系统是否始终服务于“把小说写完”，而不是让通用 Agent
把主要时间花在控制面、表格和恢复协议上。

当前默认流程只有一条：

`Python/宿主适配器分发 -> Writer 暂存正文 -> Blind Reader -> Chapter Editor -> 必要时局部精确替换或一次集中 Patch -> 双审 -> Python 晋升 -> ready`

旧 01–42 里程碑已经压缩到 `docs/archive/history.md`。当前默认行为以 `README.md`、
`AGENTS.md`、两份 Novel Forge Skill、`docs/43`、本文和 `docs/45` 为准。历史要求中的
仓库外日常 Capsule、审稿前 Generation、Lean 完整终态信封或强制分析表不再是默认要求。

## 正文与控制面所有权

| 阶段 | 唯一正文位置 | 创作角色允许写入 | Python 负责 |
|---|---|---|---|
| 初稿 | `.novel-forge/diff/chNN/writer/draft/正文.md` | Writer 只写该文件 | 最小规划、动作、快照 |
| 表面修订 | 同上 | Writer 继续修改同一文件 | 汇总 blocking、最多三轮 |
| 双审 | 同上 | 两个审稿角色各写一个简短 `result_file` | Capsule、哈希、结果规范化 |
| 文学修订 | 同上 | 全部 local 且唯一可定位时只返回 replacements；否则 Writer 按合并 MUST 集中修订 | 冻结 `控制面冻结稿.md`、Python 精确替换或记录 `修订.diff` |
| 双审通过 | `chapters/eXX/ch-XX/正文.md` | 无 | CAS 晋升、Generation、Review、Guardian、状态、Git |

双审通过前，正式章节、Generation、Guardian Receipt 和 draft Git checkpoint 都不得
出现。表面清理与文学修订都发生在同一个暂存文件，不复制第二份正文，不要求 Agent
填写技术证据。

## 审稿最小合同

Blind Reader 只提交：

- `verdict`
- 一次列全的 `must`
- `human_likeness`（仅允许 `convincing` / `uncertain` / `synthetic`；0-10 分数由 Python 立即归一化）
- `reader_desire`（仅允许 `continue` / `conditional` / `stop`；0-10 分数由 Python 立即归一化）
- `emotional_residue`
- `next_chapter_pull`
- `summary`
- 一条 `evidence_quote`

Chapter Editor 只提交 `verdict`、`must`、`summary` 和 `evidence_quote`。通用
`verdict=pass` 由 Python 规范化为内部编辑通过状态。`analysis`、hard-anchor 矩阵、
Session、Runtime、Guardian、哈希和 Git 均不是 Lean 创作角色的表单。

## 恢复矩阵

| 故障 | 恢复动作 | 不得发生 |
|---|---|---|
| Writer 结果运输缺失但正文有效 | Python 补记或复用同一正文 | 重写正文 |
| Blind Reader 运输失败 | 只换 Blind Reader | 重跑 Writer |
| Chapter Editor 运输失败 | 保留已绑定的 Blind 结果，只换 Chapter Editor | 重跑 Blind 或 Writer |
| Python 发现 Blind result_file 摘要已变化 | 重新解析并替换同 capsule/session 的缓存副本 | 使用过时 `state.json` 继续晋升 |
| 审稿自动重试耗尽后用户继续 | 校验暂存正文哈希（必要时回退正式正文）并恢复失败审稿角色 | 因尚无 Generation 而重写 |
| Writer 完成文学修订 | 清除已解决 MUST；新一轮双审的角色重试预算归零 | 继承旧正文的 finding 或失败次数 |
| Python 合法刷新 review capsule | 接受新 descriptor，并逐文件验哈希 | 归责为角色越权并循环重建 |
| 角色修改 review capsule | manifest 或文件哈希失败，退役该审稿角色 | 接受被篡改输入 |
| 角色新增未声明文件 | 清理并退役当前角色 | 把额外文件视为 Python 管理路径 |
| 角色修改代码、测试或 Skill | 恢复受保护文件并退役当前角色 | 靠改规则取得 pass |

技术重试按当前角色执行计数。Writer 修订产生新的正文后，Blind Reader 和 Chapter
Editor 都从零开始计算运输重试。文学结论的第二版仍有 MUST 时进入用户决定，不用
技术重试伪装文学收敛。

| 第二版仍有 MUST 后作者选择续修 | `authorize-revision <slug> --reference <依据>` 记录 author 决策并恢复一次集中修订 + 完整双审 | 伪造 receipt 或无限自动回炉 |
| 作者选择重新生成（retry） | Lean 下显式 author 决策通过 `require_body_history=False` 授权第三版，写 authorization 记录 | 自动重试无 author 签名时绕过两个正文版本的门槛 |
| decision 等待期误调 `complete-role` | 报错并列出当前决策的可达命令（authorize-revision / continue-budget / approve-high-risk / retry / stop） | 用技术表单补交掩盖未决决策 |
| 审稿引文逐字不匹配 | 去空白/标点规范化或前缀窗口逐字差异 ≤ 15 匹配；失败给出首个不匹配位置 | 无理由重跑审稿角色 |
| 并行双审某一角色失败 | 按 `failed_review_role` 从 issued/completed 重新排队该角色并重签发角色卡（不写主卡避免跨角色快照误报）；消费后清除该字段 | 重跑另一已完成角色或整章 |
| 并行角色结果文件缺失/非法 | 自动重签该角色（recover），不卡死在 `awaiting_double_review` | 停在无下一步的中间态 |
| 技术重试/重新生成 | 只清理可再生成的 capsule 辅助文件，`draft/正文.md` 晋升前永不清除 | 丢弃有效暂存正文 |
| 角色动作卡被篡改 | 角色卡 SHA-256 与状态记录比对失败即恢复并重签该角色 | 篡改卡扩大写入范围 |
| 正文硬门失败（如不足 5000 CJK） | Writer 完成时先对暂存正文跑正式文本门禁，进入有界表面修订轮；耗尽后停在可授权的 `surface_revision_required` 决策 | 带缺陷正文进入双审/晋升后死锁 |
| 晋升/收尾阶段 BookProjectError | 路由为可授权的 `hard_gate_failed` 决策（一次集中修订 + 完整双审，或停止） | 裸抛到 CLI 顶部，或耗尽重试停在不可授权的 `native_role_failed` |
| 章节 Git checkpoint 失败 | 停在 `git_checkpoint_failed` 决策；`authorize-revision` 保留已晋升草稿与双审证据，只重试 ready/checkpoint 尾段 | 重放已完成的双审与序列推进，或除 stop 外无路可走 |
| 暂存正文是宿主完成回执，或 mtime 早于本次 Writer 派发且摘要与派发前一致 | 判技术运输失败并有界重试，重开 Writer；以 `output:false` 派发新 Writer 重写 | 把回执 JSON 当正文跑文本门禁，或 Lead 亲手改写正文 |
| 门禁失败前 capsule 已 imported | `authorize-revision` 明确拒绝不安全的暂存修订重放并提示停止 | 静默空转的重试循环 |
| 双审结论未通过 record_review 同源校验 | 晋升前先用 `review_outcome_preflight_errors` 校验，失败路由为作者决策且无正式章节/Generation/Receipt/checkpoint | 先晋升后校验，失败时正式副作用已落盘 |

## 完整性边界

Lean 不使用全仓快照。它同时维护两个小边界：

1. 当前书快照：只允许动作声明的正文或审稿结果文件，以及 Python 管理并经 manifest
   校验的 review capsule 输入。
2. 控制面快照：保护 `app/`、`tools/`、`tests/`、两份 Novel Forge Skill、
   `AGENTS.md`、`CLAUDE.md`、`README.md`、根配置入口、当前书 `.local-guardian`
   与 `.local-book-git`。动作和 state 恢复后必须重新加载，不能继续使用恢复前的内存值。

仓库外快照目录使用仓库绝对路径 SHA-256 前缀加 slug 分区；不同仓库中的同名小说不会
共享活动 action、结果或恢复备份。

其他书和普通仓库文件的并发变化不会让当前角色失败。Strict audit 仍保留全仓快照，
只用于明确的取证或基准实验。

## 本轮发现与修复

1. review capsule 合法刷新曾被当前书 delta 误归责为角色修改，造成
   `control_plane_mutation` 自触发循环。现在 Python 管理路径与角色写入分开归责，
   capsule 内容仍逐文件验哈希。
2. `_reset_active_retry` 过去只做 `setdefault`，没有真正清零。现在新一轮角色执行明确
   从零计数。
3. `修订.diff` 过去在双审通过后才生成。现在 Writer 修订通过表面检查后立即生成，
   再启动复审。
4. Lean 审稿动作仍残留“完整官方终态”措辞。现在动作与提示都明确只写紧凑
   `result_file`，Lead 只负责等待宿主终态并调用 `complete-role`。
5. 审稿重试耗尽后的恢复曾错误依赖 `generation_id`。由于 Lean 有意延后 Generation，
   这会丢弃有效暂存正文。现在恢复依据暂存正文 SHA-256，不再重跑 Writer。
6. Lean 过去只检查当前书，无法阻止创作角色修改代码或测试。现在增加轻量控制面保护，
   不恢复全仓 Harness 的高成本与并发误伤。
7. 旧快照目录只按 slug 分区，不同仓库的同名实验书可能互相看见活动快照。现在加入
   仓库路径命名空间，并保护 action/state 与外置账本，白名单篡改不能扩大写入范围。

## 不变量

- 小说正文是主产品；表、状态、证据和 Git 是附属品。
- Lead 不代写、不代审、不手填技术证据。
- Python 合法控制面行为不消耗创作角色重试预算。
- 有效暂存正文不会因为遥测、Session 字段或审稿运输问题被重写。
- 两个审稿角色都通过前，正文不会进入 `chapters/`。
- `ready` 只表示工作流通过，不表示作者批准或发布许可。

## 变更日志（压缩版）

逐项叙述见 Git 历史中本文档的旧版本；以下保留每轮的耐久结论。

- **2026-07-24 三模型实测归因**：Lead 首选 GLM 5.2 / Kimi K3 high；DeepSeek
  v4 Flash/Pro 暂不作 Lead。root 绝对路径校验、capsule 所有权分离、独立角色
  协议由代码保证，不依赖模型自觉。
- **2026-07-29 接力与预算**：同产物 seal 幂等；章节目标路径由章节号单点生成；
  Relay status 讲人话；人类默认交接卡、宿主 --json 才拿机器动作；根 AGENTS 与
  Skill 已按预算瘦身。
- **2026-07-29 双审收敛**：审稿字段单一规范层（旧名仅入口映射）；blind_outcome
  缓存带摘要溯源；MUST 只属于其正文版本；provisional session-completions 先行
  留证，晋升后 finalization；技术重试只处理技术运输。
- **2026-07-31 成本观测与路由（docs/45 阶段 1--5）**：观测写 .local-guardian，
  不参与质量路由；writer-context.md 按 P0/P1/P2 有界装配；局部 Patch 四条件 +
  替换后全量硬检双审；exploration 永不能 formal ready；高风险确认在晋升前；
  硬预算只挡首轮双审后的自动追加调用。
- **2026-07-31 文学核心压缩**：状态链与角色集不变；literary-micro-rules/v5；
  literary_texture ≤160 字 advisory 进编辑诊断；synthetic 需逐字证据 + structural MUST。
- **2026-08-07（docs/49，已归档）**：分句级 advisory 规则与 machine_diagnostics
  ≤400 字抽样；uncertain 不视为通过且必须附 uncertain_note；开放 MUST 引文逐字
  校验；complete-role 必须真实宿主会话；并行完成 reload+合并写；审稿字段单源
  REVIEW_ANALYSIS_FIELDS；字节 zip 只在章首/晋升/决策三节点。
- **2026-08-18**：暂存正文污染检测——宿主回执或派发前旧文件判技术运输失败，
  以 output:false 重开 Writer 重写。
- **2026-08-21 全仓审查修复**：终态守卫、record_review 原子化与 CRLF 归一、
  patch 指令预算单源、异常分类学、models.SLUG_RE 单源、跨进程状态锁、局部
  Patch 后补硬检、adapter 变更操作需 --confirm 且失败退出码 1、count_cjk_chars
  单源、legacy 导出移出事务等（回归见 tests/test_review_fixes.py）。
- **2026-08-21（二）遗留收尾**：死代码清理；strict 下 .git 元数据纳入快照
  （detect-only，不自动恢复）；双审观测按完成角色归属；legacy N+1 收敛。
- **2026-08-21（三）风格语料库 style-corpus/v1**：8 条正例基因 + 14 条 AI 味
  反例单源 style_corpus.py；接入 voice-bible 与三条 lint advisory
  （emotion-label / connective-tic / role-playing-tic）。
- **2026-08-21（四）token 精简 A1--A3 + B1/B3**：交接包总预算自动推导 =15,200
  （原 28k）；规划卡改嵌有界摘录（PLANNING_*_SECTIONS）并附来源路径；语料移入
  create-only memory/style-reference.md；book_repeat.py 跨章重复三类 advisory；
  voice-bible anchor 标记 + memory/voice-seed.md 冷启动。用法见
  literary-quality-reference「Book-scale quality features」。
- **2026-08-21（五）B2/A4/A5**：book_arcs.py 弧线账本（作者直维护 Markdown 单源，
  Python 只读摘要进 handoff/规划上下文；场景包第 6 节「弧线位置」ch02 起
  advisory）；CANON_DIGEST_MAX_CHARS=6000 单源；规则文本审计结论=已单源化，
  无需重构。
- **2026-08-21（六）文档收敛**：46-blockers/47/49/46-token-diet 四个已完成
  一次性文档归档删除（结论并入 archive/history.md）；全书尺度特性用法收进
  literary-quality-reference。

## 当前 token 预算单源速查

全部位于 app/novel_forge/planning_spec.py：WRITER_CONTEXT_BUDGETS P0/P1/P2 =
1500/850/450；MAX_HANDOFF_MEMORY/SCENE_PACKAGE/PREVIOUS_TAIL/VOICE_EXEMPLAR =
6000/5000/1600/1200，MAX_HANDOFF_TOTAL_CHARS 由各部分之和 + 脚手架余量自动推导
（现值 15,200）；CANON_DIGEST_MAX_CHARS = 6000。弧线摘要上限在 book_arcs.py
（ARC_DIGEST_MAX_CHARS = 1200）。调整任何数值必须留在单源并跑
tests/test_chapter_sequence.py 的预算回归测试。
