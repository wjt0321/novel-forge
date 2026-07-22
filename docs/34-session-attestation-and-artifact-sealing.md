# 会话完成凭证与不可变证据封印

## 目标

v4.8 修复一种已在真实实验中出现的失败：Lead 没有创建独立角色会话，却用三个不同
字符串补写 Writer、Blind Reader 和 Chapter Editor 记录；随后原地修改 Generation、
Runtime Audit 或 Review，并在 Sequence 尚未完成时留下 ready Git 提交。

协议仍然厂商无关。Novel Forge 不选择 Claude、Codex、DeepSeek 或其他模型，只要求
宿主 Backend 提供可验证的原生会话身份。

## 双重会话身份

`SessionIdentity` 同时包含：

- `session_id`：宿主公开的会话 ID，用于 Generation、Review 和 Runtime 绑定；
- `session_instance_id`：Backend 拥有的底层上下文实例 ID，不能由角色名代替，也不能
  在 Writer、Blind Reader、Chapter Editor 之间复用。

编排器在角色工作完成后，将角色、上下文范围、provider、model、Harness、两类 ID、
章节、当前 Generation、当前正文 SHA-256、角色产物路径与产物 SHA-256 写入
`.local-guardian/<slug>/session-completions/`。记录使用本地 HMAC 签名，不进入
Writer Capsule，也没有 adapter 操作允许写作 Agent 自行生成。写入还要求活动
Orchestrator 持有不可序列化的进程内 capability；普通 adapter、Shell 命令或手工 Python
调用不能补造正式完成凭证。

formal Agent 稿进入 ready 时必须验证：

- Writer completion 的范围为 `writer_capsule_only`；
- Blind Reader completion 的范围为 `prose_only`；
- Chapter Editor completion 的范围为 `full_review_context`；
- 三个 `session_id` 和三个 `session_instance_id` 都不复用；
- Review 中的 provider/model 与完成凭证一致；
- 三份凭证绑定同一当前 Generation 和正文，Review 凭证还绑定当前审稿文件字节。

正文或 Review 改变后，旧 completion 不会被改写，也不能换绑新内容。新正文必须新建
Generation，并由新的 Blind Reader 与 Chapter Editor 会话创建新 completion。

## 内容封印

`record-evidence`、`record-session-audit` 和 `record-review` 成功落盘时，会为精确文件
字节创建仓库外签名 seal。seal 以书内相对路径和内容 SHA-256 定位。Review 当前指针可
随新审稿更换；Generation、Runtime Audit 和 Review History 同一路径一旦封印，不能
用不同内容重新封印。

状态复核不信任文件中的自报 `verified`：

- Generation 文件被改写后，当前字节找不到原 seal，状态变为 inconsistent；
- Runtime Audit 被改写后，即使内部仍写 `provenance_status=verified` 也会失败；
- Review 当前文件或历史记录被改写后，审稿校验失败；
- Guardian Receipt 继续使用原有外置权威副本与签名校验，不改写旧回执。

## Patch 与 Ready 顺序

Patch Capsule 的输出哈希若等于输入正文哈希，Guardian 记录
`no_content_change` compromised 回执并拒绝导入。系统不会为无变化正文创建新
Generation，也不会用相同正文刷新两份 Review。

自动完成章节的顺序为：

1. 完整验证 Generation、Runtime、Guardian、三角色 completion、双审和 gates；
2. 活动 Orchestrator 让正在运行的 Sequence 见证精确 Writer、Generation 与正文候选；
3. 使用同一进程内 capability 暂时写入 ready，但不创建 Git checkpoint；
4. 执行 `advance-chapter-sequence` 并复核 `effective_status=complete`；
5. 最后创建 `chapter: chNN ready` Git checkpoint。

Sequence 收尾失败时，章节回退到 `editorial_reviewed`，不会留下 ready 提交。
`project-status` 仍保留 declared status 供审计，但用户与自动入口只读取
`effective_status`，任何 blocker 都会把声明的 ready 显示为 inconsistent。

## 来源真实性与无 Backend 停止

`writer_type=human` 只能与 human provider/model 和直接人类来源一致。Claude Code、
Kimi Code、DeepSeek、Codex 或其他 Agent Harness 不能通过
`authority=human_delegate` / `provenance_confidence=user_attested` 逃过 Runtime 与
Guardian。

自动入口在创建书目录前先要求 Backend 返回真实 Writer session。Backend 未配置或不可用
时立即停止，不创建半成品项目，也不自动降级为手工 formal。

## 文学规则 v3

完整解释见 `docs/35-literary-rule-manual.md`。日常只注入按角色压缩的四类短规则：

- 可以写：主动选择、关系摩擦、具体私人代价、可变化物件和允许出错的专业行动；
- 慎写：完美证据链、装饰性精确、职业证明、连续同主语和过度高效的巧合回报；
- 允许：误判、留白、迟疑、纯对白、不整齐节奏和暂时未闭合的机制；
- 绝对禁止：控制面翻译、硬锚漂移、旧 Review 换绑新正文和 Lead 代做角色。

这些规则帮助角色发现问题，但不能替代会话凭证、内容封印或状态机。

本里程碑的脱敏证据见：

- `docs/examples/agent-demo-v51-literary-success-and-formal-bypass.md`
- `docs/examples/agent-demo-v51-literary-success-and-formal-bypass.json`
