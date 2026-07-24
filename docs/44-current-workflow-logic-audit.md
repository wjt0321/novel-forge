# 44. 现行工作流逻辑审计

日期：2026-07-24

## 审计目标

本轮审计只回答一个问题：系统是否始终服务于“把小说写完”，而不是让通用 Agent
把主要时间花在控制面、表格和恢复协议上。

当前默认流程只有一条：

`Lead 分发 -> Writer 暂存正文 -> Blind Reader -> Chapter Editor -> 必要时回写同一正文 -> 双审 -> Python 晋升 -> ready`

`docs/01`–`42` 是架构演进记录。当前默认行为以 `README.md`、`AGENTS.md`、两份
Novel Forge Skill、`docs/43` 和本文为准。旧文档中的仓库外日常 Capsule、审稿前
Generation、Lean 完整终态信封或强制分析表不再是默认要求。

## 正文与控制面所有权

| 阶段 | 唯一正文位置 | 创作角色允许写入 | Python 负责 |
|---|---|---|---|
| 初稿 | `.novel-forge/diff/chNN/writer/draft/正文.md` | Writer 只写该文件 | 最小规划、动作、快照 |
| 表面修订 | 同上 | Writer 继续修改同一文件 | 汇总 blocking、最多三轮 |
| 双审 | 同上 | 两个审稿角色各写一个简短 `result_file` | Capsule、哈希、结果规范化 |
| 文学修订 | 同上 | Writer 按合并 MUST 集中修订 | 冻结 `初稿.md`、立即生成 `修订.diff` |
| 双审通过 | `chapters/eXX/ch-XX/正文.md` | 无 | CAS 晋升、Generation、Review、Guardian、状态、Git |

双审通过前，正式章节、Generation、Guardian Receipt 和 draft Git checkpoint 都不得
出现。表面清理与文学修订都发生在同一个暂存文件，不复制第二份正文，不要求 Agent
填写技术证据。

## 审稿最小合同

Blind Reader 只提交：

- `verdict`
- 一次列全的 `must`
- `human_likeness`
- `reader_desire`
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
| Chapter Editor 运输失败 | 保留 Blind 结果，只换 Chapter Editor | 重跑 Blind 或 Writer |
| 审稿自动重试耗尽后用户继续 | 校验暂存正文哈希，恢复失败审稿角色 | 因尚无 Generation 而重写 |
| Writer 完成文学修订 | 新一轮双审的角色重试预算归零 | 继承旧正文的失败次数 |
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
