# 18 - 人类叙事评测与证据工作流

## 目标

本里程碑不尝试定义“文学好坏”，也不把“像人”简化成口癖、错别字或随机句长。它解决的是更窄、更可审计的问题：

1. 让 Agent 在长篇中维持事实、因果和人物认知边界。
2. 允许受控的表达差异，而不把随机缺陷当创造力。
3. 把分支试写、盲评、作者偏好和规则演进保存为可复核证据。
4. 防止旧审稿在正文或规划变化后继续充当通行证。
5. 在五章检查点和卷终发现未回收承诺、人物状态漂移与情节断线。

系统仍然不调用真实 LLM，不给文学分数，不自动批准正文，`publication_eligibility` 始终为 `False`。

## “人类写法”的可操作分解

### 事实秩序

人物生死、伤势、持有物、时间线、世界规则和角色已知信息必须可追溯。审美偏好不能覆盖 Canon，也不能把未经核验的推断写成事实。

### 因果秩序

场景不只需要“目标、阻力、转折”，还要回答：

- 角色不能同时得到哪两样东西；
- 他拒绝承认什么；
- 他误读了谁或什么；
- 哪句话不能说出口；
- 他最终接受了什么具体代价。

这些字段位于正式场景包的 `1c. 决策问题`，用于制造人物之间不整齐但有来源的摩擦。

### 有限认知

人物允许误判、迟疑、逃避和自欺，但只能根据其已知信息行动。所谓“人味”来自有限视角下的选择，不来自作者或模型随意忘记事实。

### 表达不均匀

语域、句法、细节密度和节奏应随场景功能变化。变化由压力、关系、身体状态和叙述距离驱动；故意错字、随机病句、事实错误和无意义噪声不属于合法策略。

### 作者偏好

模型可以提供比较证据，只有作者或明确授权的人类代理可以记录 preference。偏好记录说明保留与拒绝的具体品质，但不能晋升 Canon、批准章节或授权发布。

## 每书目录

```text
books/<slug>/
  evaluation/
    constitution.md
    rule-registry.md
    *-template.md
    experiments/<experiment-id>/candidates/<label>.md
  evidence/
    generations/
    evaluations/
    branches/
    preferences/
    arc-audits/
    rule-decisions/
  planning/chapter-state/chXX.md
  reviews/chXX-<role>.md
```

`evaluation/constitution.md` 与 `rule-registry.md` 是人工维护资产，`sync-tools` 只在缺失时创建，不覆盖既有内容。模板和 Agent 定义属于托管资产，可由 `sync-tools` 刷新。`evidence/**/*.md` 一经记录不可覆盖。

## 正式与探索模式

章节模式保存在 `planning/chapter-state/chXX.md`：

- `formal`：执行 5000 CJK、完整场景包、书级材料、generation、六角色审稿、formal gates 和检查点审计。
- `exploration`：用于试声、试场景、试结构或候选分支；执行表面安全与最低可渲染性检查，但 `ready_eligible=false`。

使用：

```cmd
set "NOVEL_FORGE_ROOT=%CD%" && set PYTHONPATH=%NOVEL_FORGE_ROOT%
python -m app.novel_forge.skill_adapter --root "%NOVEL_FORGE_ROOT%" --confirm set-draft-mode set-draft-mode <slug> <chapter> --mode formal
python -m app.novel_forge.skill_adapter --root "%NOVEL_FORGE_ROOT%" run-gates <slug> <chapter> --mode formal
```

`run-gates --mode` 只是断言。它与已持久化模式不一致时失败，不会临时改变规则。

## 证据格式

所有创作证据使用：

````markdown
<!-- novel-forge-evidence:v1 -->
```json
{
  "schema_version": 1,
  "id": "ASCII-stable-id",
  "kind": "generation",
  "created_at": "2026-07-17T12:00:00Z",
  "authority": "agent",
  "source_paths": ["chapters/e01/ch-01/正文.md"],
  "summary": "只用于人工审阅和索引的短摘要。"
}
```
````

共同规则：

- `id` 在本书内全局唯一，只能使用 ASCII 字母、数字、点、下划线和连字符。
- `source_paths` 必须位于当前书目录且真实存在，禁止 `..` 路径逃逸。
- 输入必须为 UTF-8；记录采用临时文件 + `os.replace` 原子落盘。
- adapter 只返回 ID、kind、路径、计数和警告，不返回摘要或正文。
- 证据不得包含 `author_approved` 或 `publication_eligibility` 声明。

## 六类证据

### generation

记录章节、模式、writer 类型、provider、model、正文路径与 SHA-256。正式审稿绑定当前 generation；正文变化后旧 generation 不能证明新正文的来源。

### evaluation

对匿名候选记录具体重建结果：人物欲望、隐瞒、关系变化、可记忆画面和下一章问题。必须记录 reviewer/provider/model/context，且 `blinded=true`。

### branch

引用同章、同实验、同候选集的 evaluation，只允许 `selection_mode=single_winner`。综合方案若有价值，必须先成为新的匿名候选，不能在选择后静默拼接。

### preference

引用 branch 与同一组 evaluation；`selected_id` 必须等于 branch winner，`rejected_ids` 必须覆盖全部落选候选。authority 和 decision_authority 只能是 `author` 或 `human_delegate`。

### arc_audit

- `scope=checkpoint`：默认每五章一次；第 5、10、15……章进入 `ready` 前必须 `open_must=0`。
- `scope=volume`：卷终审计，必须带 `volume_id`；用于检查整卷承诺、人物弧、关系债务、母题、节奏、矛盾和遗弃线索。

`source_paths` 必须覆盖审计范围内的每一章，`source_sha256` 必须逐项覆盖这些路径。范围内任一来源修改后，审计变 stale，不再满足检查点。verdict 仅为 `continue / replan`，不代表批准。

### rule_decision

规则生命周期为 `experimental → advisory → blocking`，也可降级为 `retired`。升级 blocking 前，作品、类型和模型三个维度都至少需要三个独立取值。故意错字、随机缺陷和事实错误不能登记为合法干预。

## 分支与偏好闭环

1. 把候选写入 `evaluation/experiments/<id>/candidates/A.md`、`B.md`。
2. 固定人物、场景包、上下文、模型和字数范围，只改变一个变量。
3. 以匿名标签完成 evaluation，不向评审者暴露方案来源。
4. 记录 branch，选择一个胜者并写明放弃其他候选时失去的品质。
5. 由作者或授权代理记录 preference，说明接受/拒绝的具体品质。
6. `evidence-status` 报告未决实验、已决实验和最近偏好 ID。

这套闭环学习“作者在具体冲突中选择了什么”，不生成全局风格分数，也不把一次 demo 经验升级成永久硬门。

## 审稿来源与新鲜度

review 文件绑定：

- `chapter_sha256`
- `planning_sha256`
- `draft_mode`
- `generation_id`
- `source_fingerprint`
- reviewer type/id/provider/model/context

正文、场景包、动作稿、对白账本、模式或 generation 任一变化，旧 review 变为 stale，不能满足 `ready`。blind-reader 必须只读正文。关键审稿与 generation 使用相同 provider/model 时必须填写 independence note，并在状态中保留同源警告；换角色名不构成独立评审。

## 状态与 ready

向前只允许相邻迁移，回退可直接到更早材料层。`record-review` 不自动推进状态，避免“文件一落盘就跳过中间门”。

进入 `ready` 时重新执行，而不是相信历史表格：

1. 模式必须为 formal。
2. 当前 generation 已绑定。
3. causal、line、texture、consistency、blind 均为 pass。
4. chapter-editor 为 ready_for_editor_decision。
5. 所有 review 均绑定当前材料且不 stale。
6. formal quality/narrative gates 无 blocking。
7. 检查点章节的 arc audit 已满足。

返回值始终包含 `author_approval=false`、`publication_eligibility=false`。

## 稳定策略 ID

- `no-deliberate-defects`
- `single-winner-branch`
- `model-score-not-approval`
- `aesthetic-does-not-override-facts`
- `exploration-not-ready`
- `role-name-not-independence`

ID 定义在 `planning_spec.py`，并写入新书宪法、Agent 角色和 canonical Skill。修改策略时应先改共享定义、测试和本里程碑文档，避免各提示词自行发明近义规则。

## 存量书迁移

```cmd
python -m app.novel_forge.skill_adapter --root "%NOVEL_FORGE_ROOT%" sync-tools <slug> --dry-run
python -m app.novel_forge.skill_adapter --root "%NOVEL_FORGE_ROOT%" --confirm sync-tools sync-tools <slug>
```

迁移会：

- 创建缺失的 `evaluation/`、`evidence/` 目录；
- 刷新托管模板、review 模板与 Agent 定义；
- 缺失时创建 constitution/rule registry；
- 不覆盖手写 constitution、rule registry、Canon 或任何 evidence。

旧章节不会自动获得 generation 或新审稿。若要进入 v3.3 `ready`，必须显式选择模式、记录当前 generation、按新模板复审并重跑门禁。

## 与 upstream 的关系

`upstream/` 中的项目仍可用于比较状态机、角色分工、上下文压缩和工具接口，但不参与构建，也不是规则权威源。Novel Forge 的规则应来自：

1. 可复现的功能型案例；
2. 单变量分支实验；
3. 匿名盲评；
4. 作者偏好证据；
5. 跨章节、跨作品、跨类型和跨模型验证；
6. 可退休的规则生命周期。

因此，即使没有合适的开源项目，也能通过本仓库自己的证据循环继续改进，而不是靠不断堆提示词。

## 已知边界

- 系统不能证明作品已经“像人”或具有文学价值。
- 自动 gate 擅长事实、结构和流程完整性，无法替代作者对陌生感、余韵和审美风险的判断。
- 五章 checkpoint 是默认节奏，不等于所有类型的最优分段；需要调整时应通过 rule_decision 验证。
- volume audit 目前是证据协议，不存在单独的“卷 ready”状态机。
- 没有真实多模型调度器；provenance 只诚实记录来源，不能凭空制造独立性。
