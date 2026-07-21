# 文学生产闭环与控制面隔离

## 问题

自动三角色闭环解决了会话、证据、状态和恢复，但实验显示，流程完整并不自动等于
正文有人味。最典型的失败是：机器门禁为零、盲读者能够重建谜题，正文仍像一份
漂亮的推理报告。角色会把规划里的替代解释、因果检查和专业审计逐项搬进人物思考；
Patch 又把审稿意见直接改写成解释段。

根因不是某个模型弱，也不能靠绑定 Claude、Codex、DeepSeek 或 Sol 解决。问题来自
上下文职责混淆：编辑控制面进入 Writer 上下文，审稿角色又缺少识别这种泄漏的明确
任务。

## 控制面分层

完整 Scene Package 继续作为权威规划材料，供 Chapter Editor 校验。但 Writer Capsule
中的 `handoff.md` 只包含 Story Brief：

- 章节边界与停止点；
- 场景压力、目标、阻力、选择和代价；
- 在场者状态；
- Beat 因果链；
- 信息账本与信息预算；
- 人物性呼吸段和场景余波；
- 必要 Canon、上一章末段与 Voice exemplar 功能。

以下内容保留在编辑控制面，不进入 Writer handoff：

- 决策问题；
- 观察、假设、替代解释和可推翻证据；
- 规划反证与常识检查；
- 因果归属账本；
- 专业判断审计。

这些材料仍然必须存在，因为它们能帮助编辑发现逻辑问题；不交给 Writer，是为了避免
正文逐项证明检查表。

## 三角色任务

Writer：

- 将规划视为后台故事义务，不把规划措辞写进正文；
- 允许人物误判、遗漏、自欺、延迟反应和不完整表达；
- 让专业能力通过操作条件、风险和后果显形，不写履历证明；
- 让对白改变计划、权力、认知或关系，不按固定句数插动作。

Blind Reader：

- 仍然只读正文；
- 区分“谜题可以重建”和“真人愿意继续读”；
- 检查整齐问答、替代解释枚举、职业证明、清单化节奏、控制面语言和修补接缝；
- 只有 `convincing + continue` 才能 pass。

Chapter Editor：

- 读取正文、完整 Scene Package、必要 Canon、Blind Reader 和机器定位信息；
- 每轮完整重审因果、能动性、对白、肌理、连续性；
- 检查人物可替换性、控制面泄漏和解释性 Patch；
- 不把固定对白行数、句长或比例当成文学达标线。

## Patch 协议

开放 MUST 合并为一次集中 Patch，每条义务包含：

1. 位置；
2. 原文证据；
3. 读者效果；
4. 修订意图。

Patch Writer 使用新的真实 session 和新的 Capsule。它只修改 MUST 影响的因果范围，
保留其他有效正文，不得直接增加“因为……所以……”式解释段。Patch 后两位审稿角色
都使用新会话重读完整正文。

## 生成预算

默认成本不增加：

- 规划一次，建议 high；
- 正文一次，建议 medium；
- Blind Reader 与 Chapter Editor 各一次，建议 medium；
- 有 MUST 时最多一次自动 Patch，再各复审一次；
- MAY 和 advisory 不自动触发额外生成；
- 第三版必须由用户明确选择 B 后签发人工回炉授权。

执行档位是厂商无关的意图，不是模型绑定。宿主可以选择任何 provider、model 或 Agent
产品，只需保证真实独立会话、最小上下文、来源记录和 Capsule 隔离。

## 状态真实性

第二轮仍有 MUST 时：

1. 保存当前 Generation、Runtime、Guardian Receipt 和两份 Review；
2. 将旧记录按正文绑定计算为 stale，不原地改写；
3. 退役当前 Patch Writer；
4. 将 Sequence 置为 `awaiting_session`；
5. 将工作流控制状态持久化为 `decision_required`；
6. 用户选择 B 后创建新 Writer session；
7. 签发 regeneration authorization；
8. 生成第三版并重新双审。

授权后的第三版属于人工决定下的回炉，不应被误报为自动生成预算违规；下一次不同正文
仍需新的明确决定。

## 证据样本

本里程碑的失败证据与处置见：

- `docs/examples/agent-demo-v48-control-plane-spill-and-repair-seam.md`
- `docs/examples/agent-demo-v48-control-plane-spill-and-repair-seam.json`

系统仍不认证文学价值、作者批准或发布许可。
