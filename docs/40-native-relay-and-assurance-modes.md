# v5.1 原生会话 Relay 与双保证模式

## 问题

此前 Skill 文档虽然声明交互式宿主可使用原生 Roles，但命令入口在缺少
`NOVEL_FORGE_HARNESS_COMMAND` 时仍直接停止。高思考模型因此会探索仓库、寻找或
尝试修复 Harness，并向用户提出 formal / exploration / OS 沙箱选择。机械控制面与
创作会话边界不一致，既浪费 Token，也诱发越权。

## 原生 Relay

`tools/novel-workflow.py start` 现在始终是唯一入口：

1. 有可信仓库外命令 Backend 时，保留原有同步 headless 闭环。
2. 没有命令 Backend 时，Python 创建项目并在 `.local-guardian/<slug>/native-relay/`
   签发 `novel-forge-native-action/v1`。
3. 宿主运行 `next-action`，只创建或复用动作指定的真实独立 Session。
4. 宿主使用原 typed operation handle 等待官方终态，把真实 Session、模型、
   `role_result` 与 Runtime Snapshot 写入仓库外临时 JSON。
5. `complete-role` 校验终态并由 Python 完成规划落盘、Guardian、Generation、
   Runtime Audit、双审、Patch、状态和每书 Git，再签发下一动作。

Lead 不再需要理解 Sequence、SHA-256、Guardian 或 Git，也不允许从文件出现、idle
通知或角色名猜测完成。

## 保证模式

默认 `formal_native` 不冒充 OS 沙箱。它由以下可验证措施构成：

- Writer Capsule 位于仓库外；
- 规划和审稿只经结果通道回传；
- 创作角色对项目仓库零写入；
- 每个动作签发后保存全仓快照，终态回传前复核；
- Capsule 清单、CAS、Runtime、Session 与角色终态由 Guardian 绑定；
- Generation、Runtime Audit、Receipt、Review 与 Session Completion 不可覆盖。

宿主确实提供文件系统级隔离时，可透明使用 `formal_sandboxed`。两者是控制面的保证
级别，不是创作任务中的用户选项；模型、CLI、IDE 或供应商都不是协议边界。

## 成本与探索

创作任务不读取 `app/`、`tests/`、`docs/`、Git 历史或旧实验书。Python 的下一动作
已经携带角色所需的短指令和最小上下文。只有 Writer 规划阶段可做最多 5 次题材常识、
事实边界及书名/人名重名检索；正文与审稿角色不进行开放式仓库探索。

默认模型调用仍是 Writer 规划、Writer 正文、Blind Reader、Chapter Editor。只有
真实 MUST 增加一次新 Session 的集中 Patch 和两次全文复审；第二版仍有 MUST 时停止
并请求用户决定，避免整章无限重打。

## 失败恢复

额外产物、路径逃逸、保护输入变化或项目写入不会被改写为 clean。Python 保留失败
Receipt，退役当前 Session，签发新 Session/Capsule，并最多自动重试两次。完成信封
字段错误不属于 Guardian compromise：系统保留同一 Session/Capsule/正文，要求宿主
按动作模板补交同一终态。封存 Review Capsule、按角色独立重试与现有 Generation 的
审稿恢复见 `docs/41-completion-repair-and-sealed-review-capsules.md`。
