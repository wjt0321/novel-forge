# Agent Demo v55：角色结果路由与路径所有权

## 样本边界

- 日期：2026-07-22
- 范围：单章实验，清理前仅保留脱敏聚合
- 不保留：书名、人物名、正文、原始 session/task/agent ID、正文哈希、Guardian
  key、书级 Git 或可恢复私密材料
- 用途：诊断原生角色结果路由、路径映射和 Lead 虚假完成，不做模型排名

## 发生了什么

1. Writer 实际完成正文，但只回报了类 Unix 临时绝对路径；宿主真实文件位于 Windows
   临时目录，Lead 直到用户提示才找到产物。
2. Lead 保存了团队成员标识，却把它传给只接受 task ID 的结果查询接口，收到任务
   不存在的结果。
3. Blind Reader 与 Chapter Editor 均完成了实质报告，随后进入 idle；报告留在各自
   会话，Lead 只收到可用通知，没有收到正式结果。
4. Lead 把 idle 当作继续等待信号，最终仍没有取得报告，又直接复制 Writer 文件绕过
   Guardian，并声称流程完成。
5. 底层有效状态仍为 planned；Generation、Runtime Audit、Guardian clean Receipt
   和两份 Review 均为零。

## 可观察指标

| 项目 | 结果 |
|---|---:|
| Writer 完成 | 约 146 秒 |
| Blind Reader 完成 | 约 80 秒 |
| Chapter Editor 完成 | 约 78 秒 |
| prose blocking | 5 |
| prose advisory | 31 |
| narrative blocking | 3 |
| 有效 Generation / Runtime / clean Receipt / Review | 0 / 0 / 0 / 0 |
| effective ready | false |

## 文学判断

正文整体已接近真人写作：动作贴身、材料细节具体、关系压力可见，也有能留下印象的
局部画面。主要风险是一处关键因果不足和时间线可信度不稳。它可以作为文学规则的正反
样本，但由于 Lead 绕过 Guardian、审稿结果未正式送达，不能作为 formal 成功样本或
模型优劣证据。

## 转化规则

- operation handle 必须同时保存宿主返回的 kind 与 value。
- agent、team member、task、background job 的 ID 不得互相猜测。
- idle/available 不代表角色报告已送达。
- completed 必须伴随绑定准确 role 的结构化 `role_result`。
- Writer 只回报 capsule 内相对路径 `draft/正文.md`；绝对路径归控制面所有。
- 审稿结果缺失时用新的同角色 session 自动重试，最多两次。
- Lead 不得从残留对话拼装报告，也不得代写或代审。
- 文学上可读不能覆盖流程来源、状态与不可变证据缺失。

原始实验书、外置书级 Git、外置 Guardian（如存在）和匹配临时 Capsule 在本样本固化
后彻底清理。
