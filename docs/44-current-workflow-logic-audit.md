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
| 文学修订 | 同上 | 全部 local 且唯一可定位时只返回 replacements；否则 Writer 按合并 MUST 集中修订 | 冻结 `初稿.md`、Python 精确替换或记录 `修订.diff` |
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

## 2026-07-24 三模型实测归因

本轮用宿主本地会话记录对齐了同一天的三个真实样本。统计只计算可见工具调用、
工作流命令和终态，不使用模型隐藏思考内容。

| Lead / 模型 | 独立角色 Agent | 工作流命令 | 工具错误 | 结果 |
|---|---:|---:|---:|---|
| Claude Code + GLM 5.2，`yesun-zai` | 3 | 7 | 0 | Writer、Blind Reader、Chapter Editor 一次通过 |
| Kimi Code + Kimi K3 high，`shanhaijing-K3-h` | 3 | 7 | 0 | 主动发现 root 错误后重启，双审与晋升一次通过 |
| Claude Code + DeepSeek v4 Flash，`shanhaijing-ds-flash` | 0 | 40 | 19 | Lead 亲自写三种产物，随后修改 Guardian/状态并形成循环 |

### 代码责任

1. 未加引号的 Windows 反斜杠 root 会被 Bash 吞掉，`D:\mydev\s-black-novel`
   变成驱动器相对路径并在 D 盘当前目录下建错资产。这是入口缺少绝对路径校验，
   与模型能力无关。CLI 现在会在任何资产写入前拒绝非绝对 root，并提示使用
   `D:/path/to/repo` 或给反斜杠路径整体加引号。
2. 当时的 review capsule 所有权校验会把 Python 合法刷新误判为角色修改，能够触发
   Chapter Editor 技术重试。这是代码缺陷；当前版本已把 Python 管理路径与角色输出
   分开，并有完整回归测试。
3. Lean 动作曾把 Skill 的“独立角色”要求改写成 `must_be_independent=false`，同时向
   Lead 暴露内部 `control_run_id`。这是协议自相矛盾，会诱导通用模型直接代写或把内部
   ID 当成需要修复的 Session 字段。当前公开动作恢复为独立角色要求，明确禁止 Lead
   写角色产物；内部恢复 ID 只保存在 Python state。

### 模型责任

DeepSeek v4 Flash 在第一次可恢复故障后没有停留在公开的
`next-action -> 独立角色 -> complete-role` 路径，而是依次尝试手传内部 ID、停止与重试、
直接改 Guardian capsule 状态、删除和重建技术记录，最后绕过 gate 手改 `ready`。
这些操作违反 Skill 与项目边界，并把一次代码故障放大为长循环。GLM 5.2 与 Kimi K3
面对同一类公开动作时都把角色工作交给三个独立 Agent，Lead 没有代写，也没有碰控制面。

### 选模结论

- 日常 Lead / 编排首选：GLM 5.2 或 Kimi K3 high。当前样本中二者都能理解三角色边界，
  工具调用短，且不会在技术失败后自行修状态机。
- DeepSeek v4 Flash 不建议担任 Lead。可以把它限制在 Writer 或单一审稿角色中，只给
  Capsule 和唯一输出路径，让更稳定的 Lead 负责调度。
- DeepSeek v4 Pro 的既往会话也出现过高命令数、恢复协议纠缠和控制面干预，因此在新的
  对照测试证明稳定前，同样不作为默认 Lead。
- 即使使用 GLM/Kimi，root 校验和角色所有权仍必须由代码保证；不能把系统正确性寄托在
  “模型恰好聪明地避开错误路径”上。

## 2026-07-29：接力可靠性与上下文预算修复

本轮把现场暴露出的“通用 Agent 看不懂下一步”和第二章接力故障，收敛为四条可测试规则：

1. **相同产物的 seal 是幂等的。** 同一路径、同一内容、同一 kind 的既有签名 seal
   直接复用；只有身份字段、内容或签名不一致才报完整性冲突。重试不会因为新的
   `recorded_at` 再把有效审稿判成失败。
2. **章节目标路径由章节号单点生成。** 第 N 章只能走
   `chapters/eNN/ch-NN/正文.md`；任何 Writer capsule（初稿、Patch、严格审计
   兼容路径）都复用同一函数，不能把第二章写入 `e01`。
3. **原生 Relay 自己解释状态。** `status` 读当前 Relay phase，不再把活动角色笼统说成
   “正在处理”；Writer、Blind Reader、Chapter Editor、停止和完成都有一致的人话。
   完成章的 `next-action` 返回明确的下一章 handoff，而不是“缺少角色动作”。
4. **人类默认不看技术 JSON。** CLI 的 `next-action` 输出一张只含角色、输入目录、唯一
   输出和 `complete-role` 的交接卡；只有宿主程序显式 `--json` 才拿到完整机器动作。
   `start <slug> --chapter N` 可从已持久化控制记录复用书籍元数据，避免让 Lead 重复填写
   六个字段。

上下文预算也作了收缩：根 `AGENTS.md` 从约 19,873 字符缩到约 3,876 字符，日常
Novel Forge Skill 从约 6,269 字符缩到约 2,725 字符；两份扫描位置仍逐字节同步。角色
提示词本身保持小于既有预算（Writer ≤1200 字符、Lean Blind Reader / Chapter Editor
分别受 2200 字符上限），不再把哈希、Runtime、Guardian、Git、状态表作为日常角色输入。

## 2026-07-29：双审收敛与审稿回执修复

V2 实测表明，双审卡死的主要风险不是正文或文学判断，而是把一次已接受的审稿结果在不同
持久化层中表示为不同值，再把控制面问题错误地交给新的审稿 Agent 重做。为此，当前规则
增加以下可测试约束：

1. **审稿字段只有一个规范层。** Lean 输入文档、结果解析和 state 使用 `must`、
   `evidence_quote`、`emotional_residue`；旧字段仅在入口处映射，绝不以两套名称进入
   `blind_outcome`。0--10 的自然评分也在入口归一化，7--10 对应通过档，避免 `"7"`
   这种字符串延后到晋升门禁才失败。
2. **缓存可溯源，不能无限陈旧。** `blind_outcome` 同时保存 result-file 摘要与路径。
   Python 在复用它之前比较摘要；存在合法的控制面刷新时重新解析并覆盖缓存。角色不能
   借此修改旧文件，工作区快照仍会拒绝越权写入。
3. **MUST 只属于其正文版本。** Writer 完成同一暂存正文的 Patch 后，旧
   `must_findings` 立即清除；新的双审只依据新正文的结论，恢复路径不会被已修复问题阻断。
4. **审稿完成先留可审计回执，晋升后再最终绑定。** Blind Reader 与 Chapter Editor 的
   已接受终态立即写入 provisional `session-completions`；双审通过后同一会话再以正式
   review artifact、Generation 与正文哈希 finalization。这样技术晋升失败不会抹掉
   “角色已经完成”的事实，也不提前创建正式 Review History。
5. **技术重试只处理技术运输。** 规范化、缓存刷新、旧 MUST 清理和已存在 seal 的幂等
   处理必须在 Python 内完成；只有缺 JSON、无效引文、capsule/会话绑定不一致等角色可修复
   的交付问题才重开该角色。错误信息必须携带具体原因，而非笼统称为“审稿会话异常”。

## 2026-07-31：阶段 1 成本观测，不参与质量路由

45 号提案的第一阶段已经实现为本地控制面观测，产出路径和文学门禁保持不变：

1. 每个 Native action 完成或进入技术重试时，写入一次性
   `.local-guardian/<slug>/workflow-observations/chNN/<action-id>.json`。记录角色、模型、
   调用目的、可得 token/请求数、耗时来源、重试序号、修订轮次、正文前后摘要和流程后果。
2. 未知遥测保持 `null`；Relay 的墙钟耗时明确标记为 `relay_wall_clock`。可选
   `complete-role --telemetry-file` 损坏时只留下 warning，不能触发正文或审稿重做。
3. 审稿 MUST 可抽样标注 `local|structural|blocking`，旧字符串归为 `unclassified`。此标签
   阶段 1 时尚不驱动局部 Patch；阶段 3 已将该字段接入真实路由，但只接受全部 local 且唯一可定位的连续段落。
4. `cost-summary` 只向作者展示初稿、首轮双审、Patch、复审和重试成本。观测数据不进入
   Writer/Reader/Editor capsule，不改变硬门、晋升、作者批准或发布资格。
5. 观测文件由 Python 写入后会刷新下一动作的完整性基线；创作角色仍不得修改
   `.local-guardian`，控制面新增记录不会被误报为角色越权。


## 2026-07-31：阶段 2--5 路由审计

1. Writer capsule 新增受保护 `writer-context.md`，默认 P0/P1/P2 有界装配；旧 handoff 仍被 Guardian 校验但不再默认作为 Writer 全量输入。
2. 卷级 `voice-bible-vNN.md` 是作者可维护的声音覆盖；模型连续性由本地策略记录，角色不能自行决定或补造模型。
3. 局部 Patch 必须同时满足：所有开放 MUST 为 `local`、证据位于唯一连续段落、正文 SHA 未变化、返回 target 集合与签发集合完全一致。Python 替换后重跑完整正文硬检和完整双审。
4. 动作声明宿主能力档、Python/宿主适配器 dispatcher 和 `lead_involved=false`。Exploration 在双审后仍被 Python 阻止晋升，不能通过弱 Lead 自写自审获得 formal ready。
5. 高风险确认发生在双审通过后、正式晋升前。硬预算只阻止首轮双审之后的自动追加 Patch/复审调用；正文、MUST 和双审绑定均保留，继续必须有作者依据。
6. 以上路由均不改变 5000 CJK、硬禁令、核心双审、最多一次文学 Patch、Canon candidate/promotion、`author_approval=False` 或 `publication_eligibility=False`。

## 2026-07-31：文学核心压缩审计

1. 默认状态仍为 `planned -> context_collected -> scene_packaged -> drafted -> surface_checked -> blind_read -> editorial_reviewed -> ready`，默认审稿角色仍只有 Blind Reader 与 Chapter Editor；没有新增调用环节。
2. Writer 最小包固定为 P0/P1/P2 1500/850/450 CJK，总上限 2800。Scene Package 的私人欲望、关系摩擦、感知偏差只是原文件字段，不是新 artifact 或新 gate。
3. `literary-micro-rules/v5` 将视角注意力、选择的私人代价、动作后不重复解释和关系不对称放入短规则；Writer 在同一次生成内完成静默删改。
4. `literary_texture` 是内容外泄为零的确定性摘要。高风险只向现有 Chapter Editor 注入至多 160 字提示，并在 `cost-summary` 聚合 `low|medium|high|unknown`；旧记录缺失该字段时归 `unknown`。该指标不阻断、不改变路由、不证明 AI 来源。
5. Blind Reader 的 `uncertain` 可以直接 `pass`；`synthetic` 若没有逐字证据、`needs_revision` 和恰好一条 `structural` MUST，会被控制面拒收并仅重试当前审稿交付。Chapter Editor 仍决定该结构问题是否真正值得一次修订。
6. `MAX_AUTOMATIC_GENERATIONS=2`、5000 CJK 硬门、双审、至多一次文学 Patch、Canon candidate/promotion、`author_approval=False` 和 `publication_eligibility=False` 全部保持不变。
