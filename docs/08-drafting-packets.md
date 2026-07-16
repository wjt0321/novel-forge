# 08 - Drafting Packet（写作上下文包）

## 目的

Drafting Packet 把 Voice Bible、Scene Contract v4、已批准 Canon Facts 以及上一章的承接片段汇总成一个外部 Markdown 文件，作为写稿人或 Skill 的硬上下文。它不是自动写稿工具，也不产生正文 revision。

## 核心原则

- **只提供上下文，不生成正文**。
- **不改变章节状态**：构建 packet 不会把 chapter 从 draft 推到 linted/reviewed/approved。
- **外部产物**：输出文件必须位于 `library/` 之外，避免与受版本控制的 manuscript 混淆。
- **不覆盖已有文件**：如果目标文件已存在，构建失败。
- ** readiness gate**：默认只在 `assess_drafting_readiness` 无 blocker 时才生成；阻止空模板直接喂模型。
- **不保证质量**：packet 增加的是创作纪律，不是质量分数；lint/review/人工审稿仍是最终 gate。

## 构建内容

生成的 Markdown 采用 **RTCO 三层结构**组织上下文，便于写稿人或 Skill 按优先级消费：

### P0 — Core（必须遵循）

- **Scene Contract v4 全文**：缺失则报错，不能构建。
- **Scene Embodiment Model**：从 Scene Contract v4 的 5 个具身字段（空间布局、身体状态、物体可供性、环境约束、具身动作链）提取的摘要；缺失字段会标注为 `not specified`。
- **Chapter Goal**：从 Scene Contract 提取的 `scene_question` / `present_want` 摘要。
- **Predecessor Context**：仅当上一章为 `approved` 且存在 revision 时，抽取其尾部最多 N 个字符作为承接片段，并明确提示不可逐字复述。

### P1 — Important Context（重要参考）

- **Voice Bible 全文**：若旧书没有，则标注 `MISSING`，不伪造。
- **Approved Canon Facts**：本书范围内已批准的 subject/predicate/object/evidence 及来源 chapter/revision。当前为保守回退：返回全书已批准事实，尚未按本章角色/关系精确过滤。

### P2 — Reference（连续性提醒）

- **Unfulfilled Promises / Foreshadows**：列出 `planned` / `planted` / `partially_paid` 状态、且目标章节 <= 当前章节的叙事承诺，分为：
  - **Must Resolve This Chapter**：目标章节等于当前章节。
  - **Overdue From Earlier Chapters**：目标章节早于当前章节。
  - **Unscoped / No Target Chapter**：无目标章节的承诺（保守回退）。

> P2 提醒仅为连续性信号，**不会自动批准任何内容**，也不改变章节状态。

### 元数据与交付清单

- **Metadata**：book slug/title、chapter number/title、当前 revision 信息、构建时间、note、source hashes。
- **Writer Operating Contract**：约束写作行为（只写这个场景、用动作展示、不替作者判定情绪、不把指令混入正文、不自动宣称人类创作等）。v4 合同额外要求：数字/术语必须落到身体接触、相对位置、可操作物与受阻动作中，不得用参数替代画面。
- **Delivery Checklist**：写完后自检 scene_question、irreversible_turn、cost、ending_pressure，以及 v4 新增的三项具身标准（开场能定位身体与关键物体、至少一项环境约束真实改变动作、不可逆选择由连续身体动作触发而非摘要宣布），然后交给 lint/review。

## 用法

### Service

```python
packet = svc.build_drafting_packet(
    "my-novel",
    3,
    Path("D:/drafts/ch03-packet.md"),
    note="focus on tension",
    previous_context_chars=1200,
)
```

### Adapter

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter \
    --root D:\my-novel \
    --confirm build-drafting-packet \
    build-drafting-packet my-novel 3 \
    --output-file D:\drafts\ch03-packet.md \
    --previous-context-chars 1200
```

`--previous-context-chars` 范围 `0..4000`，`0` 表示不纳入上一章。

如果 readiness gate 未通过但用户已明确授权探索性草稿，可附加 `--allow-incomplete`：

```bash
PYTHONPATH=. python -m app.novel_forge.skill_adapter \
    --root D:\my-novel \
    --confirm build-drafting-packet \
    build-drafting-packet my-novel 3 \
    --output-file D:\drafts\ch03-packet.md \
    --previous-context-chars 1200 \
    --allow-incomplete
```

绕过生成的 packet 会标注 `READINESS BYPASSED` 和 blocker 列表。详见 `docs/09-drafting-readiness.md`。

## 约束

- `--output-file` 必须是绝对路径。
- `--output-file` 不能在 `library/` 目录内。
- 目标文件不能已存在。
- Scene Contract 缺失时构建失败。
- adapter 的 JSON 输出只返回 packet 的 path/hash/metadata，不返回包内容、正文、Voice Bible 或 Scene Contract 全文。

## 与质量层的关系

Drafting Packet 是第二里程碑质量资产的消费端：

- Voice Bible 提供叙述纪律。
- Scene Contract v2 提供本场边界。
- Reader Review 方法（见 `docs/05-human-readable-fiction-quality.md`）提醒写完后应交给审稿。

但它本身不是检测器，也不替代人工判断。
