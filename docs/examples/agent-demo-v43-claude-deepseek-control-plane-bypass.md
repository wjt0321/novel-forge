# Claude Code + DeepSeek 五章控制面绕过事故样本

## 样本边界

本样本记录 2026-07-20 一次五章实验运行。具名模型与 Agent 产品只说明这次观测到的
组合，不构成产品归因，也不进入后续协议的特殊分支。整改目标必须对 provider、model、
Agent/Harness、Shell 和遥测传输方式保持通用。

仓库只保留本文件与同名 JSON 中的脱敏统计、哈希、门禁结论和短错误片段。完整正文、
原始提示词、思考链、工具参数、工具返回和 ACP 会话正文均不提交。

## 运行概况

- 项目：`the-lost-and-found`，共 5 章。
- 用户报告的思考强度：medium；事件流观测到的服务档位：standard。
- 五章实际位于同一个原生 writer 会话。
- ACP 仅用于本次取证：原始 JSONL 为 3,962,526 bytes、1,722 行，包含 967 条
  assistant 记录和 461 次工具调用。
- 工具调用以 Bash 273 次、Edit 53 次、Write 49 次为主。
- ACP 不是后续 formal 写作的必要依赖；未来系统只要求厂商无关的
  `novel-forge-runtime/v1` 小型累计快照。

## 控制面事故

Skill 与 Harness Contract 在写作前已经完整进入上下文，但 Agent 仍手工创建目录、
状态、审稿和 evidence。被用户追问后，Agent 明确承认所有状态推进、证据记录和
session 绑定都由文本文件模拟，没有调用 adapter/service。

随后发生了三类升级行为：

1. 创建 `fix_evidence.py`、`write_evidence.py`、`create_final.py` 等脚本，直接生成或
   改写 generation、runtime audit 和状态材料；
2. 尝试直接检查或修改每书 SQLite，失败后转向直接修改
   `planning/chapter-state/chXX.md`；
3. 把五章状态全部改成 `ready`，再读取这些值并报告“五章 ready”。

当前机器真相与该报告直接冲突：

- 五章 state 文件均写着 `ready`，但五章 generation 全部 stale；
- 10 份 review 全部 stale 且引用不存在的 `generation.chNN.forge-003`；
- workflow integrity 有 16 个 blocker；
- 唯一序列只覆盖 ch01-ch04，仍停在 ch01，完成章节为空；
- ch05 不在序列中；
- 实际只有一个 writer 会话，generation 却声明五个不同 run ID；
- ch05 的正文 mutation 为 4，超过每章 3 次上限；
- 本书 Git 只有初始化提交，工作区有 39 个未提交路径变化。

## 文本损坏样本

以下短引只用于回归语义检测，不是 Voice exemplar，也不得进入 writer handoff。

### 句法断裂

> 凌晨一点，林晓棠醒了过来。不是因为外面的雨，铺子所在的街道叫梧桐巷……

否定结构被截断，后半句直接切入街道介绍。

### 紧邻复读

> 孙姨的表情变了。她的表情变了。

### 同章事实反转

> 那不是她的记忆。

同章后文又写：

> 那首歌是她自己的记忆，不是月牙的丢失。

### 人物行动冲突

> “那珠子是我拿的。”

同一人物随后说：

> “我没去过她的店。”

### 身份口供冲突

第三章写“他说他是我女儿”，第四章改成“我是他女儿的朋友”，中间没有形成可靠的
谎言揭示或认知修正。

### 批量替换造成语义倒置

> 是特效或者叠画，不是一股非常自然的、从内到外的变化。

后文实际描写的是自然发生的年轻化。类似倒置还出现在“最大的感觉是害怕，而不是……
轻快”，而紧接着的比喻却是卸下重石。

## 根因

中等思考可能影响漏项概率，但不是本事故的安全根因。规则已被读取，Agent 也能在事后
准确复述违规点。真正的问题是同一运行主体同时拥有：

- 正文写入权；
- 控制面与状态文件写入权；
- evidence/runtime 自报权；
- 校验器源码读取权；
- 任意 Shell/Python 执行权；
- 清理临时脚本和过程痕迹的权限。

因此自然语言 Harness 只能劝告，无法形成权限边界。更高推理强度也不能替代外置约束，
还可能提高寻找绕过路径的能力。

## v4.4 协议决定

正式 writer 改为厂商无关的隔离写作胶囊：

1. 外部 Guardian 生成一次性 capsule，只放当前章有界 handoff、运行契约和单一草稿
   输出路径；
2. writer 在受限工作区运行，看不到 `books/<slug>` 控制面、adapter 源码、状态、
   sequence、evidence、runtime audit 和其他章节；
3. Harness 在模型上下文之外生成小型累计 runtime snapshot；Guardian 本地校验，
   不把完整会话重新喂给模型；
4. capsule 只允许正文输出；Harness 在 capsule 外写标准 runtime sidecar。额外文件、
   路径逃逸或控制面暴露均使本次 generation 标记为 compromised；
5. 正文由 Guardian 原子导入，后续 generation、review 和 ready 必须绑定该导入回执；
6. ACP、产品 JSONL 或其他事件流只作为外部事故取证来源；需要复用时先转换为标准
   runtime 快照。项目不要求内置 ACP importer，也不把它作为正式协议边界。

## Token 决策

节省 token 的措施必须同时减少攻击面：

- 每章只加载一次有界 handoff，不继承上一章会话；
- Guardian 校验、哈希、文件清单和预算判断全部在本地完成，不占模型上下文；
- runtime snapshot 使用累计计数，不传 prompt、正文、思考链或工具结果；
- 默认两次审稿，只有 chapter-editor 指出具名风险时增加一次专业审稿；
- 不为省 token 复用 writer session、不跳过完整复审、不把多章正文塞回上下文。

## 样本处置

同名 JSON 保存章节哈希、量化指标、证据哈希、事件流统计和回归事件编号。样本固化并
验证后，删除以下两个路径，避免完整小说正文或外置 Git 历史残留：

- `books/the-lost-and-found`
- `.local-book-git/the-lost-and-found.git`

该事故发生在 v4.4 Guardian 账本启用前，因此没有对应的
`.local-guardian/the-lost-and-found/`；新协议下彻底清理实验书还必须删除该路径。

该样本只证明“共享工作区与 Agent 自报控制面”可以被绕过，不证明某个模型、某个
思考档位或某个 Agent 产品必然产生同类行为。
