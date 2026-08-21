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

## 2026-08-07：修辞层 advisory 与 uncertain 契约（docs/49 §4）

1. lint 新增分句级检测：`mechanical-triplet` 扩展到逗号分句级（3 连以上同前缀复沓如“那些A，那些B，那些C”、≥2 字回环如“他沉默了，沉默得让人心慌”），新增 advisory 规则 `not-only-flip`（“不仅/不只是…而/更/而是”），`explanation-tic` 补入视角泄漏与成语化意象（“她不知道的是/没人知道/命运的(车轮|齿轮|轨迹)/时间仿佛(凝固|静止)/空气中弥漫着/说不清道不明”），`simile-density` 去掉 <500 字早退。全部 advisory，先观察一轮误报率。
2. lint advisory（`explanation-tic/rhythm-monotony/mechanical-triplet/simile-density`）按规则聚合为 ≤240 字，与 ≤160 字纹理提示合并为 Chapter Editor 的 `machine_diagnostics`（总 ≤400 字）；语义仍是低成本抽样、不作单独判错依据。Blind Reader 保持 prose-only，strict_audit 路径不变。
3. `uncertain` 契约以代码为准统一（取代 2026-07-31 节第 5 条的“uncertain 可以直接 pass”）：`uncertain` 不视为通过；pass 必须 `human_likeness=convincing` 且 `reader_desire=continue`；给 `uncertain` 必须附一句具体 `uncertain_note`（哪段像通用/工整/解释充分），说明为空则结果无效。校验在 `record_review`（`_review_validation_errors`），`review_outcome_preflight_errors` 同源同步。
4. 双审每条开放 MUST 的原文 `evidence` 也按 `_quote_matches` 逐字校验，编造引文判无效并走与 `evidence_quote` 相同的 repair 路径。
5. 集中 Patch 与局部 Patch 指令均加硬约束：新增因果必须落进动作/停顿/物件后果，禁止新增解释性段落。

## 2026-08-07：宿主真实会话与并行完成契约（docs/49 P1-1/P1-2/P1-3）

1. `complete-role` 必须用 `--session-id` 报告角色实际使用的宿主会话；合成 control id 只用于分发，不再充当完成会话。Writer 完成时 Python 把章节序列与 capsule control 重绑到该真实会话（prepared 态才可重绑，authorization 同步重签），Generation run_id、session-completions 与 Guardian 回执一律只携带真实会话；缺失时拒绝完成并报错。
2. 并行双审下 `complete-role` 按宿主会话匹配、`--role`、唯一未完成角色依次精确解析完成对象；多个未完成角色且无提示时拒绝猜测并报错。修复耗尽路径先持久化 `failed_review_role` 再恢复，重签恰好是绑定角色；合流/晋升段失败且无可重签审稿角色时直接路由作者决定。
3. 并行完成对 `state.json` 做 reload+合并写：review_session_ids、role_session_history、completed_review_roles 等列表去重合并，其余字段覆盖后单次原子写，后完成者不再覆盖先完成者的审稿字段（跨进程并发窗口仍为 reload+写，未加锁）。
4. 晋升后 Writer 技术重试若需要新正文版本授权（如第三版本门），`_recover_technical_failure` 捕获 GuardianError 并路由到作者 decision（`native_role_failed`），不再裸抛异常。

## 2026-08-07：审稿字段单源与动作快照 zip 收敛（docs/49 §2 轻量化）

1. 审稿字段清单收单源：`REVIEW_ANALYSIS_FIELDS`（blind-reader 8 字段 / chapter-editor 5 字段）从 `workflow.py` 移入 `planning_spec.py`，扁平别名 `BLIND_RECONSTRUCTION_FIELDS`、`EDITORIAL_DIMENSION_FIELDS` 由该 dict 派生；`workflow.py` 与 `book_project.py` 删除本地重复定义，改为统一导入，`native_relay` 沿用原导入名，判定结果逐字节不变。
2. 动作快照 zip 收敛：每次动作签发与完成的哈希比对（防改 `app/`、`tools/`、`tests/` 控制面）保持不变；字节备份 zip 只在 3 类节点生成——章节开始（首次签发）、晋升（ready）、进入作者决策（decision_required）。中间动作只写/更新哈希快照，不再打包 zip。
3. 章节开始由 state 内 `chapter_zip_issued` 标记判定（每章首签打一次，重启后不重打）；晋升与决策由完成观测的 `workflow_effect`（promotion/author_decision）驱动 refresh 打 zip。strict_audit 与 lean 共用同一代码路径。
4. 中间动作篡改仍按哈希比对检出并路由角色重试。字节恢复语义：当前动作自带 zip（章节开始、晋升、决策节点）或可回退到保留的章首基线 zip 时执行；lean 控制面层（`app/`/`tools/`/`tests/` 哈希）的中间动作仅检出不恢复字节。章首 zip 作为整章字节基线保留（章首动作完成时不再被自身消耗），由 `stop` 或下一章签发作废。并行双审下两角色共用观测上下文导致的 write-once 观测冲突不再阻断完整性 refresh，zip/快照照常写入。

## 2026-08-18：宿主适配层正文污染检测

`complete-role` 接受 Writer 完成前新增两类暂存正文来源校验（archive/history.md 2026-08-18 缺陷 1/2/6）：

1. 暂存正文可解析为宿主子代理完成回执（`state: done|error`、`status: completed` 且带 `session`，或带 `operation_handle`）时，判为适配层运输污染；
2. 暂存正文 mtime 早于本次 Writer 动作签发时间、且摘要与派发前快照一致时，判为非本次 Writer 会话产出。

两类都按技术运输失败走有界重试并重开 Writer；恢复路径是以 `output:false` 重新派发 Writer 由其重写正文，Lead 不得亲手写 `draft/正文.md`。内容相对派发前快照已变化但 mtime 异常时放行，避免误伤原地重写的合规正文。


## 2026-08-21：全仓代码审查修复（终态守卫、审稿 TOCTOU、并发锁与规则单源收敛）

本轮为全仓代码审查后的集中修复，全部为既有承诺的强制化，不改变日常一章的角色顺序。回归测试集中在 tests/test_review_fixes.py。

1. 终态守卫：complete-role / complete_minimal / _recover_technical_failure 对 stopped、complete、decision_required 三种终态直接返回当前 status 结果，不再把迟到的宿主回传路由进恢复分支重签 Writer；作者决定卡不会因迟到回传而不可达。
2. 审稿落盘 TOCTOU：record_review 改为把已校验文本原子写入 canonical（等价内容则跳过重写，避免作废已登记的会话凭证），不再从磁盘重读源文件后封印；读取时统一 CRLF 归一化，修复 history 文件被写成 CR-CR-LN 的既有缺陷。
3. Patch 指令预算单源：writer_prompt 的指令上限由总预算推导（patch_directive_budget），超限报错给出实际上限；lean 路径超限时路由作者 decision 卡而非裸异常。
4. 异常分类学：completion 的 role_result 非 dict、evidence_quote 为空列表不再抛 AttributeError/IndexError；ChapterSequenceError 与 ArtifactIntegrityError 纳入 complete-role 技术失败恢复路由。
5. slug 校验单源：models.SLUG_RE（ASCII 字母数字连字符下划线）接入 book_project/book_evidence/book_memory/native_relay/service/skill_adapter/autonomous/project_templates 全部路径派生点，路径穿越面收口。
6. 并发：complete_role 与 complete_minimal 以跨进程状态锁串行（O_EXCL 锁文件位于系统临时目录，带陈旧锁破坏）；并行双审下先完成者保留共享快照与字节基线，由最后完成者消费，兄弟角色不再被误判技术失败而重签。
7. 局部 Patch 完成后补跑全章硬检（_staged_hard_gate_findings），删文导致 CJK 不足在局部修订环内暴露为 local_patch_hard_gate_failed 决策，而不是推迟到晋升段。
8. 开放 MUST 缺原文引文判结果无效走 repair（与编造引文同路径）；已关闭 MUST 不受影响。
9. adapter 契约收紧：lint 与 review 属于变更操作，需要 --confirm；所有失败路径退出码改为 1（stdout JSON 信封不变）。
10. 规则单源收敛：CJK 计数统一到 planning_spec.count_cjk_chars（含 U+3007/Ext-A/兼容区），门禁、lint 计数、密度分母、状态展示共用；CLAUDE.md 模板的 5000 CJK 与场景包 0b 标题改由 planning_spec 常量注入；删除 project_templates 中 399 行无引用的 agent 定义死代码。
11. legacy 链修复：export_book 的 pandoc 子进程移出数据库事务（转换失败不再出现磁盘有产物而 exports 表无痕）；init_db 错误路径关闭连接并备份前 WAL checkpoint；CLI 捕获 schema 版本与 sqlite 错误；audit limit 下界校验。
12. 低危批次：证据层容忍单条损坏记录并在 evidence-status 输出 invalid_records；memory fact.valid_from/promise.planted_chapter 拒绝 null；review capsule 路径拒绝反斜杠并校验 resolve 包含关系；book_git 用 shutil.which 解析 git 绝对路径；book_project 状态写入原子化；capsule 重置不跟随符号链接；深夜 N 点时间排序回绕；序列完成判定要求非空 run_id。

## 2026-08-21（二）：审查遗留项收尾

1. 死代码清理：_complete_review 中 strict 分支后不可达的 lean patch 派发块、两处 strict-only 路径上的恒死三元式（writer-planning 角色卡）、恒真 elif 均已移除；顺带修复 _complete_review 内遗漏的 role_result 非 dict 解析加固。
2. strict_audit 下 .git 元数据纳入快照：snapshot_workspace 新增 git_meta 参数，覆盖 HEAD/ORIG_HEAD/config/index/packed-refs 与 refs/** 的 sha 标记（不含对象库，成本有界）。.git 变更只检出并路由作者决定，不做自动删除或恢复（避免程序化改 .git）；字节备份 zip 仍排除 .git。
3. 双审观测按角色归属：_write_action 为 blind-reader / chapter-editor 各存独立观测上下文（state.role_call_observations），complete-role 按 completion 角色取对应上下文；并行双审下先完成者的遥测不再记到后签发卡片名下，也不再因 write-once 冲突被丢弃。
4. legacy 链 N+1 查询收敛：list_books 用单条 GROUP BY 取每书章节数与 approved 数；list_chapters 以三条批量聚合替代每章三次查询；API get_chapter 改用单连接的 chapter_detail（原先一次请求开约六个连接）。响应形状不变。
