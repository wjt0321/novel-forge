# 带类型角色结果与审稿恢复

## 事故

一次单章实验中，Writer、Blind Reader 和 Chapter Editor 都实际完成了工作，但 Lead
没有可靠取得子角色产物。Writer 回报了类 Unix 临时路径，真实宿主运行在 Windows；
Lead 又把团队成员 ID 交给只接受 task ID 的结果查询接口。两个审稿角色随后进入
idle，报告仍留在各自会话中，Lead 持续等待并最终给出虚假完成说明。

正文局部具有人味，但正式状态仍停在 planned，没有有效 Generation、Runtime Audit、
Guardian clean Receipt 或 Review。文学质量不能修复产物运输与来源证明。

## 通用协议

Novel Forge 不规定宿主产品，只规定两层语义：

1. `operation_handle = {kind, value}`。kind 由宿主定义，决定使用哪个官方 wait/join
   与结果读取通道。agent、team member、task 和 background job 的 ID 不得互猜。
2. completed 必须伴随 `novel-forge-role-result/v1`，包含准确的 `role` 与结构化
   `payload`。结果可经 inline、background output、mailbox 或 artifact 返回。

created、accepted、working、progress、idle、available 和文件稳定都不能代替以上
两项。句柄相同但 kind 不同也视为不同宿主对象。

## 路径所有权

Writer 只知道 capsule 内相对布局，正式结果只回报 `draft/正文.md`。宿主绝对路径、
临时目录映射和目标书路径都由确定性控制面掌握。Writer 返回绝对路径、越界路径或
其他文件名时，Guardian 保留 compromised 回执，废弃 Session/Capsule 并换新重试。

## 审稿恢复

Blind Reader 与 Chapter Editor 通过正式结果通道返回结构化判断，不直接修改
`reviews/`。控制面验证角色、正文引文、必填维度和 verdict 后才落盘。

- 结果未送达、角色不匹配或结构无效：废弃本次审稿 session；
- 创建新的同角色 session，重新读取该角色允许的完整上下文；
- 最多自动重试两次；
- Blind 成功后 Editor 故障，只重试 Editor；
- 重试耗尽才进入 A/B/C；
- `retry` 从当前 Generation 继续审稿，不因传输故障重写正文。

## 厂商无关性

Claude Teams、Codex task、Kimi role、OMP 自定义 role、命令桥或未来宿主都只需把
自己的生命周期与结果通道映射到上述协议。模型偏好仍由用户或宿主选择，正式来源只
记录终态实际 resolved model。协议不含任何默认厂商或模型组合。

## 证据

脱敏事故样本见：

- `docs/examples/agent-demo-v55-role-result-routing-and-path-ownership.md`
- `docs/examples/agent-demo-v55-role-result-routing-and-path-ownership.json`

样本不保留正文、书名、角色名、原始句柄、正文哈希、Guardian 私密材料或书级 Git。
