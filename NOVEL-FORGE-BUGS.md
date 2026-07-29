# Novel Forge 工作流卡点报告

> **历史说明（2026-07-29）**：本报告用于保留缺陷复现和修复优先级。报告所涉本地书籍、外置 Git 与 Guardian 运行资产已在同日清理为新的测试起点；下文的路径和状态仅是历史快照，不能视为现有项目或可恢复资产。

> 本文件由 Cindy 在 2026-07-28 至 2026-07-29 写《诡渡》（slug: `gui-du`）第 02 章的
> 自动生产过程中实时记录。第 01 章已经晋升成功，第 02 章正文已通过双审（Blind
> Reader pass / Chapter Editor pass）但 Python 控制面无法把暂存正文晋升到
> `chapters/e02/ch-02/正文.md`，整个流程陷入死循环。本报告按"现象 → 复现 → 期望
> → 实际 → 影响 → 控制面快照 → 修复方向"的格式记录所有卡点，便于后续迭代。

## TL;DR

| # | 严重度 | Bug | 当前结果 |
|---|---|---|---|
| 1 | 🔴 阻断 | Chapter Editor 重试耗尽后 `ArtifactIntegrityError` 死循环 | 第 02 章正文无法晋升 |
| 2 | 🔴 阻断 | `records` 表始终为空，`chapter_snapshots` 只有创建时一条 | `status` 永远显示"重新核验" |
| 3 | 🟠 高 | Generation `content_path` 写成 `chapters/e01/ch-02/正文.md`（错 episode） | 即使晋升成功路径也会错 |
| 4 | 🟠 高 | Generation `generation_stage=raw` / `review_round=0` 与实际修订轮次不符 | 审计记录失真 |
| 5 | 🟠 高 | Review history 中 `chapter_sha256` 记录的是初稿 sha，与 capsule 内实际 prose sha 不一致 | 完整性链条含混 |
| 6 | 🟡 中 | 状态机大量把"已给出 verdict 的会话"标记为 `status=failed` | 不必要地消耗技术重试预算 |
| 7 | 🟡 中 | Chapter Editor 的多次 session-completions 从未落盘 | `reviews/history/` 完全没有 ch02 CE 归档 |
| 8 | 🟡 中 | `start --chapter N+1` 在第一章完成后仍抛 `ChapterSequenceError` | 必须用 `start --chapter N` 而非 next-action 才能推进 |
| 9 | 🟡 中 | `verdict=ready_for_editor_decision` 等内部状态名直接外溢到 review 文件 | 用户/Lead 看不懂 |
| 10 | 🟢 低 | `status` 与 `next-action` 给出的提示语义不一致 | UX 困惑 |
| 11 | 🟢 低 | Capsule 在 CRLF→LF 转换时未同步重算 `chapter_sha256` | 哈希账本与正文对不上 |

---

## Bug #1 🔴 Chapter Editor 重试耗尽后陷入 `ArtifactIntegrityError` 死循环

### 现象

当 Chapter Editor 在同一 capsule 上被重试 ≥ 2 次后，下一次 `complete-role` 抛：

```
自动流程无法继续：ArtifactIntegrityError：完整性记录已存在，不得覆盖：
3cafc7b1b8e4a355e9cb44557b41ffbdabe4029b9794f38042dd27a75d353c73-43b2883f0f9c0a4e94a528c7997ffa9ddc5e02ad1c4771f89e2f92d424711681.json
```

错误中的 sha 拼接格式为 `<prose_sha256>-<artifact_sha256>.json`，对应 `.local-guardian/<slug>/artifact-seals/` 下已存在的 seal 文件。

### 复现

1. `python tools/novel-workflow.py --root <root> start <slug> --chapter 2 ...`
2. Writer 写完正文 → `complete-role` → Blind Reader pass → `complete-role`
3. Chapter Editor 给 `needs_revision`（这是合理 MUST）→ Python 进入 patch → Writer 修订 → `complete-role`
4. 重新进入双审：Blind Reader pass → `complete-role`
5. Chapter Editor pass → `complete-role`
6. 此时状态机内部因为某种原因（疑似 capsule manifest 哈希碰撞或会话状态识别错误）把 chapter editor 标记为 `failed` 而非 `completed`，自动重发同一动作
7. 重发 1 次：再跑 Chapter Editor → pass → `complete-role` → `审稿会话异常，已自动换新会话重试`
8. 重发 2 次：再跑 → pass → `complete-role` → `ArtifactIntegrityError`

### 期望

- 同一 capsule 的 seal 已存在时，应直接跳过记录步骤，把已有的 pass verdict 应用到状态机推进。
- 或者，重发同一动作时应使用新的 `manifest_sha256`（包含新的 review_session_id），避免与历史 seal 文件名碰撞。

### 实际

- Python 把"完整性记录已存在"作为不可恢复错误抛出，整个晋升流程停止。
- 用户被卡死，正文在 diff 区无法晋升。

### 影响

- 第 02 章及之后所有章节都无法 ready，整个项目停摆。
- 用户必须手工删除 `.local-guardian/<slug>/artifact-seals/*.json` 才能解除阻塞（但会破坏审计链）。

### 控制面快照

```
.local-guardian/gui-du/native-relay/state.json:
  phase: awaiting_chapter_editor
  chapter: 2
  patch_round: 1
  technical_retry_count: 2
  technical_retry_counts: {blind-reader: 0, chapter-editor: 2, patch-writer: 0}
  action_id: native-action-1c678ea7e0cb4c38
  control_run_id: relay-chapter-editor-ch02-15e1f12888f14d10

role_session_history (chapter-editor):
  relay-chapter-editor-ch02-c34177f57abc46ba: failed
  relay-chapter-editor-ch02-b124e1e30c14461d: failed
  relay-chapter-editor-ch02-d7650b33596e4a9b: completed   ← 第 1 次 pass，但状态机没识别
  relay-chapter-editor-ch02-5eea4d209779493a: failed
  relay-chapter-editor-ch02-fb24d9baa20e414f: failed
```

```
.local-guardian/gui-du/artifact-seals/3cafc7b1b8e4a355e9cb44557b41ffbdabe4029b9794f38042dd27a75d353c73-43b2883f0f9c0a4e94a528c7997ffa9ddc5e02ad1c4771f89e2f92d424711681.json:
{
  "artifact_path": "reviews/ch02-blind-reader.md",     ← 注意：这个 seal 是 blind-reader 的
  "artifact_sha256": "43b2883f0f9c0a4e94a528c7997ffa9ddc5e02ad1c4771f89e2f92d424711681",
  "kind": "review",
  "recorded_at": "2026-07-28T16:12:09+00:00",
  "schema": "novel-forge-artifact-seal/v1"
}
```

### 修复方向

1. **seal 文件命名加入 review_session_id**：当前 `<prose_sha>-<artifact_sha>` 在同一 capsule 多轮审稿下必然碰撞。改成 `<prose_sha>-<artifact_sha>-<session_id>` 或加入 `review_round` 维度。
2. **`ArtifactIntegrityError` 改为幂等**：如果 seal 已存在且内容一致，直接返回成功；只有内容冲突才报错。
3. **状态机识别 pass verdict 后立即推进 phase**，不要在重试预算里继续重发同一动作。

---

## Bug #2 🔴 `records` 表为空，`status` 永远显示"重新核验"

### 现象

即使第 01 章已经完整晋升（generation、guardian-receipt、reviews 全部齐备），`status` 命令仍然返回：

```
本章状态尚未一致，系统正在重新核验。
```

并且持续 30 秒以上不解除。

### 复现

1. 完成第 01 章所有流程（已观察到 generation.ch01、guardian-receipts/cap-ch01、reviews/ch01-blind-reader.md、reviews/ch01-chapter-editor.md 全部就位）
2. 执行 `python tools/novel-workflow.py --root <root> status <slug>`
3. 看到"本章状态尚未一致，系统正在重新核验"

### 期望

- 第一章晋升完成后，`records` 表应写入 ready 记录（包括 chapter、kind=tier、source_path 等）
- `status` 命令应明确返回"第 N 章已 ready"或"等待第 N+1 章 start"

### 实际

```sql
SELECT * FROM records;  -- 空
SELECT * FROM chapter_snapshots;
-- (1, '2026-07-28T10:49:39Z', '1837d99d...', 'memory/context-cache/ch01-memory.md')
-- 只有章节初始化时的快照，没有 ready 后的快照
```

### 影响

- 状态机永远卡在"重新核验"，无法给出明确指引。
- 用户只能通过 `next-action` 报错信息反推当前状态。

### 修复方向

- 在第一章 ready 时，往 `records` 表写入至少一条 `(kind='chapter_ready', chapter=1, ...)` 记录。
- `status` 命令加超时（如 5 秒查不到一致状态就降级输出当前 phase 与 last action）。

---

## Bug #3 🟠 Generation `content_path` 写错 episode 编号

### 现象

`books/gui-du/evidence/generations/generation.ch02.e42930409acc4df2.md` 中：

```json
{
  "chapter": 2,
  "content_path": "chapters/e01/ch-02/正文.md",
  "source_paths": ["chapters/e01/ch-02/正文.md"]
}
```

### 期望

- 第二章应该晋升到 `chapters/e02/ch-02/正文.md`
- `content_path` 与 `source_paths` 都应该是 `chapters/e02/ch-02/正文.md`

### 实际

- Generation 记录指向 `e01/ch-02/`，但 `chapters/e01/ch-02/` 目录根本不存在
- 实际晋升流程卡死（见 Bug #1），`chapters/e02/` 也不存在

### 影响

- 即使 Bug #1 修复后，晋升逻辑可能基于错误的 path 创建目录，造成章节散落到错误 episode。
- 章节序号账本（`chapters/eXX/ch-YY/`）会失序。

### 修复方向

- Generation 工厂里 `eXX` 的 `XX` 应该等于 `chapter` 字段，不是 episode 计数器。
- 增加 unit test：第 N 章的 content_path 必须以 `chapters/e{N:02d}/ch-{N:02d}/` 开头。

---

## Bug #4 🟠 Generation `generation_stage` / `review_round` 与实际不符

### 现象

第 02 章已经经历了"Writer 初稿 → 双审 → MUST patch → 重新双审 → pass"完整流程，但 Generation 记录：

```json
{
  "generation_stage": "raw",
  "review_round": 0,
  "review_call_count": 0,
  "draft_edit_count": 0,
  "draft_write_count": 1,
  "draft_mode": "formal"
}
```

### 期望

- 经历 patch 后，`generation_stage` 至少是 `revised` 或 `patched`
- `review_round` 反映实际审稿轮次
- `draft_edit_count` 反映 Writer 在 patch 阶段的编辑次数

### 影响

- 审计链失真，未来追责或回溯无法判断章节实际经历。
- `model-score-not-approval` 策略无法基于真实 review round 评估。

### 修复方向

- Patch 完成后立即更新 Generation（或创建新的 Generation，`parent_generation_id` 指向原 raw Generation）。
- 文档化 Generation 在 patch / revise / promote 各阶段应该处于什么 stage。

---

## Bug #5 🟠 Review history `chapter_sha256` 与 capsule 实际 prose sha 不一致

### 现象

`books/gui-du/reviews/ch02-blind-reader.md`：

```
- chapter_sha256: 4a19951547eea51ab031688a05647cf49e9e658e39d2ca64b4b47fdaa7f61362
```

但实际：

```bash
# 修订前初稿（CRLF）
sha256(初稿.md) = 4a19951547eea51ab031688a05647cf49e9e658e39d2ca64b4b47fdaa7f61362

# 修订后正文（CRLF）
sha256(writer/draft/正文.md) = a6a51cb3ed9f915d68010a6723be7990ce4428ead1e8626569cdeac9fde17b75

# Capsule 给 blind-reader 的 prose.md（LF，已规范化）
sha256(blind-reader-input/prose.md) = aa61bbbbb6a87899ce32426feaa34a493fe0917deabc70f88c8b1f48421afbd7
```

也就是说：

- Blind Reader 实际读到的 prose 内容是**修订后**版本（grep 验证包含 "凉线从腕骨一直凉到指尖"）
- 但 review record 里记录的 `chapter_sha256` 是**初稿** sha
- capsule 内 prose.md（LF 规范化后）的 sha 跟记录里的 chapter_sha 都对不上

### 期望

- `chapter_sha256` 应该是 Blind Reader 实际读到的 capsule prose 的 sha（即 `aa61bbbb...`）
- 或者在记录中明确两个 sha：raw prose sha + canonical chapter sha

### 影响

- 完整性校验时，seal 文件名拼接用 `<prose_sha>-<artifact_sha>`，但 prose_sha 取自哪里不明确。
- 与 Bug #1 协同放大：当 seal 文件命名基于"初稿 sha"时，多轮重试必然碰撞。

### 修复方向

- 统一规范：所有 `*_sha256` 字段必须取自实际 capsule 文件（LF 规范化后）的 sha。
- 增加 `raw_chapter_sha256` 字段记录 writer draft 原始（CRLF）sha 作为参考。

---

## Bug #6 🟡 状态机大量把"已给出 verdict 的会话"标记为 `failed`

### 现象

`role_session_history` 显示：

```
chapter-editor:
  c34177f57abc46ba: failed   ← 实际：给出了 needs_revision + 3 MUST，是有效审稿
  b124e1e30c14461d: failed   ← 实际：同上
  d7650b33596e4a9b: completed ← 第 1 次 pass
  5eea4d209779493a: failed   ← 实际：第 2 轮 pass 后被误判 failed
  fb24d9baa20e414f: failed   ← 实际：第 3 轮 pass 后被误判 failed

blind-reader:
  409f614e86d243f5: failed   ← 实际：第 1 次 pass（被误判）
  cecca1342f85461e: failed   ← 实际：第 2 次 pass（被误判）
  4cf9188c5ca14a99: completed
  94ddd23e4a324a45: completed
```

所有标 `failed` 的会话实际上都给出了合法 verdict（pass 或 needs_revision + MUST），result_file 也写入了正确 JSON。

### 期望

- 只要 result_file 存在、verdict 合法，会话状态就应该是 `completed`。
- 只有 result_file 缺失、JSON 损坏、verdict 字段缺失才算 `failed`。

### 实际

- Python 用某种"会话异常检测"（疑似基于 result_transport、session_metadata 或 manifest 一致性）把大量合法会话标记为 failed。
- 这些 failed 会话不必要地消耗了 `technical_retry_count` 预算（最终耗尽 2 次）。

### 影响

- 同一章被反复重审，浪费 token。
- 重审产生的 seal 文件触发 Bug #1 的 ArtifactIntegrityError。

### 修复方向

- 把"会话异常检测"的判定标准从"manifest/session metadata 不一致"改为"result_file 不存在或 JSON schema 不合法"。
- 在 status 命令中暴露"被判定 failed 的具体原因"，方便调试。

---

## Bug #7 🟡 Chapter Editor 的 session-completions 从未落盘

### 现象

`.local-guardian/gui-du/session-completions/` 目录：

```
relay-blind-reader-ch01-bc9af81a8ca54f38.json
relay-blind-reader-ch02-4cf9188c5ca14a99.json
relay-blind-reader-ch02-94ddd23e4a324a45.json
relay-chapter-editor-ch01-ebd9a5e5784f4c9c.json   ← 只有 ch01 的
relay-writer-ch01-d7c6fb7d1b944d36.json
relay-writer-ch02-a20647c0d7fb45e6.json
```

ch02 chapter editor 跑过 5 次，但**没有一次**生成 `relay-chapter-editor-ch02-*.json` session-completion 文件。

同时 `books/gui-du/reviews/history/` 里 ch02 只有 blind-reader 的归档，没有任何 `review-ch02-chapter-editor-*.md`。

### 期望

- 每次 chapter editor 给出 verdict（无论 pass 还是 needs_revision），都应该：
  1. 写入 `.local-guardian/gui-du/session-completions/relay-chapter-editor-ch02-*.json`
  2. 归档到 `books/gui-du/reviews/history/review-ch02-chapter-editor-*.md`

### 影响

- ch02 chapter editor 完全没有审计痕迹，与 ch01 不对称。
- 这可能是状态机误判 chapter editor "failed" 的根因（没有 session-completion → 状态机认为没完成）。

### 修复方向

- 检查 chapter editor 的 session-completion 写入路径是否漏写了 `chapter ≥ 2` 的分支。
- 加 e2e 测试：连续跑 2 章，确认每章每个角色都有 session-completion。

---

## Bug #8 🟡 `start --chapter N+1` 抛 `ChapterSequenceError`，但 `status` 显示"第 N 章完成"

### 现象

```
$ python tools/novel-workflow.py --root <root> status gui-du
第一章完成，是否继续第二章？

$ python tools/novel-workflow.py --root <root> next-action gui-du
自动流程无法继续：WorkflowError：当前没有等待执行的原生角色动作。

$ python tools/novel-workflow.py --root <root> start gui-du --chapter 2 ...
自动流程无法继续：ChapterSequenceError：第 01 章尚未完整 ready；必须通过当前
generation、runtime、formal gates 与两角色审稿后才能创建下一章 session。
```

三个命令给出三个互相矛盾的状态信号。

### 期望

- `status` 显示"第 N 章完成"时，`start --chapter N+1` 应该立即成功。
- 或者 `status` 应该显示"第 N 章已 ready；调用 `start --chapter N+1` 开始下一章"。
- `next-action` 在第一章 ready 后应自动给出"start --chapter N+1"提示，而不是抛 WorkflowError。

### 实际

- 用户必须**手动尝试 `start --chapter N+1`**，且只有在 `status` 显示"完成"时才有效。
- 在第 01 章刚 ready 但状态机尚未稳定时（见 Bug #2），`start --chapter N+1` 还会抛 ChapterSequenceError。

### 修复方向

- `status` 命令直接给出下一步 CLI 建议（如"运行 `start --chapter 2`"）。
- `next-action` 在 ready 状态下不要抛错，而是返回一个 hint 动作。

---

## Bug #9 🟡 内部状态名（如 `ready_for_editor_decision`）外溢到 review 文件

### 现象

`books/gui-du/reviews/ch01-chapter-editor.md`：

```
- verdict: ready_for_editor_decision
```

但 Lead / 用户看到的 Lean 协议字段只有 `pass` / `needs_revision`。

### 期望

- Review 文件里的 `verdict` 字段应该与 Lean 协议保持一致：`pass` / `needs_revision`。
- 内部状态名（如 `ready_for_editor_decision`）应该只在 Python 控制面内部使用。

### 影响

- 用户读到 `ready_for_editor_decision` 不知所云，误以为章节还没决定。
- 与 Blind Reader 的 `verdict: pass` 不对称，造成混淆。

### 修复方向

- 在 review 序列化层把内部状态映射为用户可见状态：`ready_for_editor_decision → pass`。
- 文档化所有可能的 verdict 值。

---

## Bug #10 🟢 `status` 与 `next-action` 提示语义不一致

### 现象

| 命令 | 返回 |
|---|---|
| `status gui-du` | "正在自动处理本章。" |
| `next-action gui-du` | 返回 chapter-editor 动作 JSON（说明还在等 chapter editor） |
| `complete-role gui-du` | "审稿会话异常，已自动换新会话重试。" |

三个命令对当前状态的描述各不相同。

### 期望

- `status` 应明确说出当前 phase（如 `awaiting_chapter_editor`）和已完成的步骤。
- `next-action` 报错时应附带 phase 信息。
- `complete-role` 报"审稿会话异常"时应该说明判定 failed 的具体原因（result_file 缺失？schema 不合法？sha 不一致？）。

### 修复方向

- 统一 status / next-action / complete-role 的状态描述字典。
- 异常信息里加 `reason` 字段。

---

## Bug #11 🟢 Capsule 在 CRLF→LF 转换时未同步重算 `chapter_sha256`

### 现象

- Writer 在 Windows 上写正文默认 CRLF：`writer/draft/正文.md` 字节 = 17973，CRLF = 323
- Python 在组装 capsule 时做了 CRLF→LF 转换：`blind-reader-input/prose.md` 字节 = 17650，CRLF = 0
- 但所有 review / generation / seal 记录里的 `chapter_sha256` 仍然指向初稿 sha（`4a199515...`，CRLF 版本）

### 期望

- Capsule 应该固定一种规范化策略（推荐 LF），所有 sha 都基于规范化后的内容计算。
- 或者明确两个 sha 字段：`raw_sha256`（writer draft 原文）+ `canonical_sha256`（LF 规范化后）。

### 影响

- 跨平台（Windows ↔ Linux）会导致 sha 不稳定。
- Bug #5 的根因之一。

### 修复方向

- 在 Writer capsule 写入时立即做 CRLF→LF 规范化，并基于规范化内容计算 sha。
- 文档化"所有 sha256 字段都基于 LF 规范化后的字节序列"。

---

## 复现脚本（最小化）

```bash
# 1. 创建新书
python tools/novel-workflow.py --root D:/mydev/s-black-novel start test-bug \
  --title "Test" --genre "test" --protagonist "A" --world "A" \
  --conflict "A" --hook "A"

# 2. 跑完第一章（Writer → Blind Reader → Chapter Editor → 晋升）
python tools/novel-workflow.py --root D:/mydev/s-black-novel next-action test-bug
# ...委派 Writer...
python tools/novel-workflow.py --root D:/mydev/s-black-novel complete-role test-bug
# ...委派 Blind Reader...
python tools/novel-workflow.py --root D:/mydev/s-black-novel complete-role test-bug
# ...委派 Chapter Editor，故意给 needs_revision + MUST...
python tools/novel-workflow.py --root D:/mydev/s-black-novel complete-role test-bug

# 3. Patch Writer 修订
python tools/novel-workflow.py --root D:/mydev/s-black-novel next-action test-bug
# ...委派 Writer patch...
python tools/novel-workflow.py --root D:/mydev/s-black-novel complete-role test-bug

# 4. 第二轮双审
# ...Blind Reader pass...
# ...Chapter Editor pass...

# 5. 现在连续调用 complete-role 几次：
python tools/novel-workflow.py --root D:/mydev/s-black-novel complete-role test-bug
# 预期：第一章完成
# 实际：审稿会话异常，已自动换新会话重试。

python tools/novel-workflow.py --root D:/mydev/s-black-novel next-action test-bug
# 重发 chapter-editor 动作

# 再跑一次 chapter editor pass...
python tools/novel-workflow.py --root D:/mydev/s-black-novel complete-role test-bug
# 预期：第一章完成
# 实际：ArtifactIntegrityError：完整性记录已存在
```

---

## 第 02 章当前状态（截至 2026-07-29）

**正文已写好，无法晋升**：

| 资产 | 状态 |
|---|---|
| `books/gui-du/.novel-forge/diff/ch02/writer/draft/正文.md` | ✅ 修订后版本，5009 CJK |
| `books/gui-du/.novel-forge/diff/ch02/初稿.md` | ✅ 修订前版本，5003 CJK（CRLF） |
| `books/gui-du/.novel-forge/diff/ch02/修订.diff` | ✅ patch diff（修复凉线章际回退 MUST） |
| `books/gui-du/.novel-forge/diff/ch02/blind-reader.json` | ✅ verdict=pass, convincing, continue |
| `books/gui-du/.novel-forge/diff/ch02/chapter-editor.json` | ✅ verdict=pass, 0 MUST |
| `books/gui-du/chapters/e02/ch-02/正文.md` | ❌ 不存在（晋升失败） |
| `books/gui-du/evidence/generations/generation.ch02.*.md` | ⚠️ 已存在但路径错（e01/ch-02） |
| `books/gui-du/reviews/ch02-blind-reader.md` | ✅ 已 archive |
| `books/gui-du/reviews/ch02-chapter-editor.md` | ❌ 不存在 |
| `books/gui-du/reviews/history/review-ch02-chapter-editor-*.md` | ❌ 不存在 |

**用户决策**：保留草稿，等迭代掉 Bug #1 后让 Python 自动补记晋升。

---

## 修复优先级建议

1. **P0（阻断）**：Bug #1 ArtifactIntegrityError 死循环 → 必须先修，否则任何多轮审稿都会卡死
2. **P0（阻断）**：Bug #6 状态机误判 failed → Bug #1 的上游成因之一
3. **P1（高）**：Bug #2 records 表为空 → 影响 status / start --chapter 推进逻辑
4. **P1（高）**：Bug #3 Generation content_path 错 episode → 即使晋升成功也会写错位置
5. **P1（高）**：Bug #7 Chapter Editor session-completions 缺失 → Bug #6 的可能根因
6. **P2（中）**：Bug #4, #5, #8, #9 → 审计链准确性 / UX 一致性
7. **P3（低）**：Bug #10, #11 → 长期技术债

---

## 调试时用到的关键文件路径

- 状态机：`.local-guardian/<slug>/native-relay/state.json`、`next-action.json`
- 会话完成：`.local-guardian/<slug>/session-completions/*.json`
- Seal 记录：`.local-guardian/<slug>/artifact-seals/<prose_sha>-<artifact_sha>.json`
- Guardian Receipts：`books/<slug>/evidence/guardian-receipts/cap-chNN-*.json`
- Generations：`books/<slug>/evidence/generations/generation.chNN.*.md`
- Reviews：`books/<slug>/reviews/chNN-{blind-reader,chapter-editor}.md`、`reviews/history/`
- 暂存区：`books/<slug>/.novel-forge/diff/chNN/`
- 正式章节：`books/<slug>/chapters/eNN/ch-NN/正文.md`
- 索引 DB：`books/<slug>/.novel-forge/index.sqlite3`（表：records / chapter_snapshots / entities / facts / events / promises / knowledge）

---

*报告由 Cindy 在 2026-07-29 生成。正文保留在 diff 区，等 Bug #1 修复后由 Python 自动补记晋升到 `chapters/e02/ch-02/正文.md`。*
