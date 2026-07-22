# 会话完成凭证与不可变证据封印

## 目标

v4.7 修复一种已在真实实验中出现的失败：Lead 没有创建独立角色会话，却用三个不同
字符串补写 Writer、Blind Reader 和 Chapter Editor 记录；随后原地修改 Generation、
Runtime Audit 或 Review，并在 Sequence 尚未完成时留下 ready Git 提交。

协议仍然厂商无关。Novel Forge 不选择 Claude、Codex、DeepSeek 或其他模型，只要求
宿主 Backend 提供可验证的原生会话身份。

## 双重会话身份

`SessionIdentity` 同时包含：

- `session_id`：宿主公开的会话 ID，用于 Generation、Review 和 Runtime 绑定；
- `session_instance_id`：Backend 拥有的底层上下文实例 ID，不能由角色名代替，也不能
  在 Writer、Blind Reader、Chapter Editor 之间复用。

编排器在角色工作完成后，将角色、上下文范围、provider、model、Harness 和两类 ID
写入 `.local-guardian/<slug>/session-completions/`。记录使用本地 HMAC 签名，不进入
Writer Capsule，也没有 adapter 操作允许写作 Agent 自行生成。

formal Agent 稿进入 ready 时必须验证：

- Writer completion 的范围为 `writer_capsule_only`；
- Blind Reader completion 的范围为 `prose_only`；
- Chapter Editor completion 的范围为 `full_review_context`；
- 三个 `session_id` 和三个 `session_instance_id` 都不复用；
- Review 中的 provider/model 与完成凭证一致。

## 内容封印

`record-evidence`、`record-session-audit` 和 `record-review` 成功落盘时，会为精确文件
字节创建仓库外签名 seal。seal 以书内相对路径和内容 SHA-256 定位，支持同一路径的
Review 当前快照随新审稿更换，同时保留每个历史内容的不可变封印。

状态复核不信任文件中的自报 `verified`：

- Generation 文件被改写后，当前字节找不到原 seal，状态变为 inconsistent；
- Runtime Audit 被改写后，即使内部仍写 `provenance_status=verified` 也会失败；
- Review 当前文件或历史记录被改写后，审稿校验失败；
- Guardian Receipt 继续使用原有外置权威副本与签名校验，不改写旧回执。

## Patch 与 Ready 顺序

Patch Capsule 的输出哈希若等于输入正文哈希，Guardian 记录
`no_content_change` compromised 回执并拒绝导入。系统不会为无变化正文创建新
Generation，也不会用相同正文刷新两份 Review。

自动完成章节的顺序调整为：

1. 完整验证 Generation、Runtime、Guardian、三角色 completion、双审和 gates；
2. 暂时写入章节 ready 状态，但不创建 Git checkpoint；
3. 执行 `advance-chapter-sequence`；
4. 复核 Sequence `effective_status=complete`；
5. 最后创建 `chapter: chNN ready` Git checkpoint。

Sequence 收尾失败时，章节回退到 `editorial_reviewed`，不会留下 ready 提交。
`project-status` 仍保留 declared status 供审计，但用户与自动入口只读取
`effective_status`，任何 blocker 都会把声明的 ready 显示为 inconsistent。

## 文学规则 v2

脱敏样本同时补充四条短规则，不加载样本全文：

- 精确数字必须改变动作、限制、风险、后果或必要结构；
- 私人代价必须落到具体的人、关系、记忆或物件；
- 灯、门、按键、工具和位置按状态连续核对；
- 正文抽象化具体代价或越过停止点时，Chapter Editor 必须明确裁决。

这些规则帮助角色发现问题，但不能替代会话凭证、内容封印或状态机。
