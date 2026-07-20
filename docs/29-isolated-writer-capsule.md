# 29. 隔离 Writer Capsule 与外置控制面

## 背景

v3.9-v4.3 已能在事后识别预算超限、来源不一致、伪造 `ready`、过期审稿和章节会话
复用，但它们仍默认写作 Agent 与 `books/<slug>/` 控制面共享文件系统。只要 Agent
同时拥有正文、状态、evidence、校验器源码与任意脚本执行权，自然语言规则就只能是
劝告，不能阻止 Agent 直接制造通过门禁所需的文件。

2026-07-20 的五章事故脱敏样本保存在：

- `docs/examples/agent-demo-v43-claude-deepseek-control-plane-bypass.md`
- `docs/examples/agent-demo-v43-claude-deepseek-control-plane-bypass.json`

具名产品只是该次观测元数据。v4.4 的整改对 provider、model、Agent/Harness、
Shell 和遥测传输方式保持通用。

## 安全目标

Formal Agent writer 不再拥有书项目控制面写权限。外部 Harness 负责落实操作系统级
文件系统边界，Novel Forge Guardian 负责准备有界工作区、导入结果和验证回执：

1. writer 看不到 `books/<slug>/planning`、`evidence`、章节序列、验证器源码、
   其他章节或每书 Git；
2. writer 只接收当前章有界 handoff；
3. writer 只能产出单一正文文件；
4. runtime 快照与隔离证明由外部 Harness 写入，不由 writer 自报；
5. 正文只有通过 Guardian 导入后才能成为当前章正式 generation 的候选；
6. compromised session 永久记入章节序列，不能删除违规文件后原地重试。

## 机器合同

新书包含 `evaluation/guardian-contract.json`。同一合同也可通过只读 adapter op
`guardian-contract` 获取。合同规定 capsule 必须位于仓库外，并只包含：

```text
capsule.json
guardian-contract.json
handoff.md
draft/
```

writer 运行后只允许新增：

```text
draft/正文.md
```

累计 runtime 不进入 capsule，也不由 writer 写。外部 Harness 在模型进程之外生成
`novel-forge-runtime/v1` 紧凑快照，并通过 `record-capsule-runtime` 写入
`.local-guardian/<slug>/runtime/` 外置 sidecar。快照必须包含：

```json
{
  "guardian": {
    "capsule_id": "cap-ch01-...",
    "workspace_mode": "isolated_writer_capsule",
    "filesystem_scope": "capsule_only",
    "book_control_plane_visible": false,
    "validator_source_visible": false,
    "reported_by": "external_harness"
  }
}
```

证明必须与准备记录中的 capsule ID 完全一致。它不是模型自评，而是负责启动 writer
进程的外部 Harness 对其实际文件系统配置的机器声明。Harness 无法落实该配置时必须
使用 `degraded_exploration`，不能生成 formal 回执。

## 操作顺序

章节序列签发当前章并绑定真实 session 后，由外部编排器执行：

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter \
  --root <仓库绝对路径> \
  --confirm prepare-writer-capsule \
  prepare-writer-capsule <slug> <sequence-id> \
  --session-id <session-id> \
  --capsule-dir <仓库外 capsule 绝对路径> \
  --target-path chapters/e01/ch-01/正文.md
```

Harness 将 writer 的工作目录与可见文件系统限制为返回的 capsule，等待 writer
完成正文。Harness 在 capsule 外生成累计 runtime 快照，然后先执行：

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter \
  --root <仓库绝对路径> \
  --confirm record-capsule-runtime \
  record-capsule-runtime <slug> <capsule-id> \
  --file <仓库外 runtime JSON 绝对路径>
```

runtime 记录成功后再执行：

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter \
  --root <仓库绝对路径> \
  --confirm ingest-writer-capsule \
  ingest-writer-capsule <slug> <capsule-id>
```

只有 clean 导入才会原子替换目标 `正文.md`。Guardian 同时在
`.local-guardian/<slug>/receipts/` 写入 HMAC 签名权威回执，并在
`evidence/guardian-receipts/<capsule-id>.json` 写入相同的可审阅副本。公开副本
不能单独证明导入成功；`ready` 与 `project-status` 会复核签名、外置账本、
imported 控制记录、章节、`run_id`、目标路径和当前正文 SHA-256。

初稿导入后若审稿要求一次集中 patch，再次运行 `prepare-writer-capsule` 会把当前
正文预置到新 capsule 的 `draft/正文.md`，writer 仍在隔离目录内局部修改。第三个
潜在正文版本默认在 capsule 创建前返回 `human_decision_required`。可信控制面先
执行 `authorize-regeneration`，记录绑定当前 chapter、sequence、session 与前两份
正文哈希的 author/human_delegate 决定；随后把返回的 authorization ID 传给
`prepare-writer-capsule --regeneration-authorization-id <id>`。授权是外置签名、
单次使用的控制面凭证，导入时会再次复核，不能用 prepare 参数里的自报布尔值代替。

同一章/session 新建 capsule 会把更早的 prepared capsule 标为 `superseded`。
patch capsule 还使用 `input_body_sha256` 做 compare-and-swap；目标正文在准备后发生
变化时，旧 capsule 不得覆盖新内容。

## Compromised 条件

以下任一情况都会写入 compromised 回执，并自动调用章节会话失效逻辑：

- capsule 中出现脚本、额外目录或任何未声明文件；
- 出现软链接、路径逃逸或 capsule 位于仓库内/仓库父目录；
- `capsule.json`、合同或 handoff 被修改；
- 正文或外置 runtime sidecar 缺失，正文不是 UTF-8；
- runtime 不是标准累计快照、scope 不是一章、session 不匹配；
- runtime 预算观测不完整或已经超限；
- 外部 Harness 隔离证明缺失、字段不完整或 capsule ID 不匹配。
- patch 基线正文发生变化，或第三份正文缺少有效签名授权。

失效后的 session ID 仍保留在 `used_session_ids` 与 `invalidated_sessions`，不能再次
claim。编排器必须创建新的原生 writer session 和新的 capsule。

## Token 与速度

v4.4 不要求 ACP、完整会话导出或全文审计回灌。Guardian 的清单、哈希、JSON、
预算和回执校验全部在本地 Python 中执行，不占模型上下文。模型只读取一次有界
handoff；runtime 只保存累计计数和来源元数据，不保存 prompt、正文、思考链或工具
返回。

这是一种同时节约 token 和缩小攻击面的优化。以下做法仍被禁止：

- 为节省 token 复用上一章 writer session；
- 跳过修订后的全文复审；
- 让 writer 读取验证器源码后自行修 evidence；
- 把多章正文、旧工具日志或完整 transcript 塞回新章上下文；
- 通过降低隔离、来源、审稿新鲜度或文学门禁换取速度。

## ACP 边界

ACP、产品 JSONL 或其他事件流可以在事故调查时由外部工具读取，也可以先转换为
`novel-forge-runtime/v1` 再交给现有审计入口，但 Novel Forge 不要求内置 ACP
importer。Formal 链路只依赖标准 runtime、外部 Harness 隔离证明和 Guardian 回执。

## 信任边界与限制

Novel Forge 不负责启动具体厂商模型，也不能仅靠 Python 文件清单替代操作系统级
sandbox。外部 Harness 是负责落实 capsule-only 文件系统的可信控制面；writer 是
不可信数据面。若二者由同一主体模拟、或 Harness 允许 writer 访问主仓库，则该运行
不满足 formal 条件，即使正文质量看起来合格也不能进入 `ready`。

`.local-guardian/<slug>/` 与 `.local-book-git/<slug>.git` 一样是主仓库忽略的
本地控制面资产。彻底删除实验书时，在保留允许推送的脱敏聚合样本后，必须同时删除
`books/<slug>/`、`.local-book-git/<slug>.git` 和 `.local-guardian/<slug>/`。
