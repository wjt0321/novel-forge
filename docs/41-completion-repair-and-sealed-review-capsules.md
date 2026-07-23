# v5.2 完成信封补交与封存审稿输入

## 事故

一次原生 Relay 压力测试中，前三次 Writer 都完成了正文。前两次正文并没有文件越界、
额外产物或控制面修改，但 Lead 把 `runtime_snapshot` 写成 `runtime`，随后又漏填隔离
证明字段。Relay 把完成信封错误与 Guardian 完整性事故合并处理，生成 compromised
回执、退役 Session，并要求新 Writer 重写整章。

第三版正文成功导入后，Lead 又把第一版旧稿手工粘贴给 Blind Reader。正式引文校验
阻止了错误 Review 落盘，但 Writer 已消耗的全局技术重试次数被 Blind Reader 继承，
第一次审稿失败便直接耗尽机会。结果是有效正文停在 `surface_checked`，用户只能看到
任务失败，却不知道系统为何重写、审错稿和停止。

## 失败分类

Relay 现在把失败分成两类：

1. **完成信封可补交**：字段缺失、字段名错误、operation handle 或 Session 绑定没有
   按动作模板装配、Runtime Snapshot 结构不完整。保留同一 Session、Capsule 和正文，
   不创建 Guardian 失败回执，不重新调用模型；宿主只需按 `completion_template`
   补交同一官方终态。
2. **角色或完整性真实失败**：额外文件、路径逃逸、保护输入变化、项目控制面写入、
   正文缺失、审稿实质结果无效或 Capsule 被篡改。此时才退役当前角色 Session，
   保留不可变失败记录，并为同角色签发新 Session。

补交最多两次。补交次数不计入创作角色的技术重试预算；无法恢复的终态才转入对应角色
的失败恢复。

## 完成模板

每个 `novel-forge-native-action/v1` 都包含完整的 `completion_template`。模板固定：

- 当前 `action_id` 与角色；
- Session、typed operation handle 和结果通道位置；
- `novel-forge-role-result/v1` 的角色 payload 结构；
- Writer 所需 `runtime_snapshot` 及 Guardian 隔离字段；
- 审稿所需 `review_capsule_id`。

Lead 只填宿主返回的真实值，不重新设计 JSON，不搜索源码，也不把字段从记忆中拼出。

## Review Capsule

Python 为每次审稿创建仓库外、内容寻址的 `novel-forge-review-capsule/v1`：

- Blind Reader：`instructions.md`、当前 `prose.md`；
- Chapter Editor：以上内容加 Scene Package、用户硬锚合同、必要 Canon、已正式落盘
  的 Blind Review、机器诊断；第 2 章起可加上一章末段。

动作 JSON 不再内嵌正文。Lead 只把 `review_capsule.path` 交给新 Session，禁止读取、
复制、粘贴或重组正文。manifest 绑定角色、当前正文 SHA-256、每个文件的 SHA-256 与
字节数；回传前再次验证。任何变化都会废弃本次审稿 Session，并从当前正式正文创建
新的 Review Capsule。

## 独立重试

`writer-planning`、`writer`、`blind-reader`、`chapter-editor` 与 `patch-writer`
分别计数。Writer 的历史失败不占用 Blind Reader 的机会，Blind Reader 成功后 Editor
从零开始，Patch Writer 也有独立预算。

当当前 Generation、Runtime Audit 和 Guardian clean 回执已经有效，而任务因审稿
运输失败进入 `decision_required` 时，`retry` 保留正文与 Generation，从未完成的
Blind Reader 或 Chapter Editor 继续。文学 MUST 的用户重生成决定仍走新 Patch 或
授权 Generation，不与运输恢复混用。

## 用户可见状态

补交期间只显示“正在确认角色结果。”；审稿真实失败时显示“审稿会话异常，已自动换新
会话重试。”；只有对应角色两次自动重试都失败后才显示 A/B/C。用户界面不暴露 JSON、
Session、Guardian、哈希、Git 或 Traceback。
