# 读者追读与运行真相（v4.3）

## 为什么还要再加一层

v4.2 已经具备章节独立会话、运行预算、两角色审稿和每书本地 Git，但新样本暴露了
两个不同方向的问题：

1. 一篇正文可以出现真实的人物关系和追读欲，却因为 Agent 没有记录 generation、
   没有创建有效独立审稿会话而停在流程外；
2. 另一篇正文可以把 generation、review、state 和 Git commit 全部写齐，却复用
   一个 writer session、让一份单章 runtime audit 绑定三章，并以十一轮正文修改
   穿过三次修改上限，最终仍自称 `ready`。

因此，v4.3 不继续给 writer 增加文学规则，而是把“读者是否愿意继续”和“运行事实
是否真实”分开处理。

## Reader Pull

blind-reader 仍然只读当前章正文，并继续重建空间、身体、行动约束、情绪轨迹、
对白动态和三个可记忆画面。新增三项：

```text
reader_desire: continue | conditional | stop
emotional_residue: 读后仍残留的关系、情绪或代价
next_chapter_pull: 让读者自愿追下一章的具体问题
```

`verdict=pass` 现在要求：

- `human_likeness=convincing`；
- `reader_desire=continue`；
- 两项追读证据均为实质内容；
- blind-reader 使用不同于 writer `run_id` 的原生会话；
- 原有 prose-only 重建证据完整有效。

这不是“文学评分”。系统仍然不能证明一篇小说好，也不能代替作者批准。它只要求
独立读者明确回答：**读完这一章，我是否自愿继续？为什么？**

正向样本片段只保存在 `docs/examples/` 的实验审计中，不进入新书模板、handoff 或
Voice exemplar。否则“人味证据”会立刻退化成下一轮模型的模仿配额。

## Runtime Truth

formal generation 进入 `ready` 前新增四项事实校验：

1. `generation.run_id` 只能服务一章；
2. runtime audit 的 `scope_chapter_count` 必须等于 1；
3. runtime audit 的 `generation_record_ids` 必须且只能包含当前 generation；
4. `draft_write_count`、`draft_edit_count`、`review_call_count` 必须可观测且不超限。

当前上限保持不变：

```text
draft_write_count + draft_edit_count <= 3
review_call_count <= 3
```

这些不是建议值。缺失或超限都会阻断 `ready`。如果旧项目已经写成 `ready`，
`project-status` 会把冲突列为 workflow-integrity blocker，而不是温和 warning。

## 自动审稿契约

Harness Contract 新增机器可读的 `review_orchestration`：

```json
{
  "auto_launch_after_surface_checked": true,
  "user_confirmation_required": false,
  "blind_reader_requires_new_native_session": true,
  "when_session_unavailable": "review_session_required",
  "open_ended_review_question_forbidden": true
}
```

Novel Forge 不直接调用 Claude Code、OpenCode、MiniMax Code、Reasonix 或其他产品
创建会话；外部 Harness 负责实现这个契约。formal surface gate 通过后，编排器应
自动创建独立 blind-reader 会话，再运行 chapter-editor。无法创建时返回明确机器
状态，不得暂停询问“要不要审核”。

## 对“像人”的当前答案

新样本说明，较低参数或较低推理强度不必然降低文学可读性。Flash 样本的优势不是
更完整的解释，而是人物通过工作、孤独、陪伴和冒险选择建立了可感知的关系；Pro
样本则更倾向于把情绪翻译成分类、肌肉名称和显式象征。

v4.3 因而选择：

- 保留关系压力、情绪余波和追读欲的独立读者证据；
- 不把正向片段变成 writer 的新规则；
- 把会话、审计、修改次数交给机器硬门；
- 继续让最终问题保持开放：**这篇小说像是人类写的吗？**

