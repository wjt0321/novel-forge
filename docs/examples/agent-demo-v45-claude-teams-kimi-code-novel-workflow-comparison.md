# Claude Teams 与 Kimi Code 单章工作流对照样本

## 样本边界

- 日期：2026-07-21
- Claude Teams 样本：《天倾时，我在旧城修屋脊》第一章《黑水》
- Kimi Code 样本：《死者记忆不予公证》第一章《三个程雾砚》
- 本文件只保留正文哈希、量化指标、流程真相和可迁移的文学判断。
- 不保留小说全文、原始会话、思考链、密钥、Guardian签名材料或可恢复的每书Git历史。
- 两组故事、Agent编排方式和工作流模式不同，因此只能用于诊断工作流，不能作为严格的模型排行榜。

## 对照结果

| 项目 | Claude Code Agent Teams | Kimi Code CLI单会话 |
|---|---|---|
| 书项目 | `old-roof-repair` | `dead-memory-notarization` |
| 正文 | 7772 CJK | 5713 CJK |
| SHA-256 | `a7564316e5cb23e5b8a3b82946a67230ff97305e5210cda98fc407615d2521fb` | `777e7ace400db7c6b6196cd0447b082b48e874e9aead340dc81bb8d677791c7d` |
| 门禁 | 0 blocking，23 advisory | 0 blocking，26 advisory |
| 最终状态 | `ready`，sequence `complete` | `editorial_reviewed`，未达到 `ready` |
| Writer | 原生Teams成员 | Kimi主会话直接生成 |
| 双审 | 原生独立成员，但与Writer同模型来源 | 同一会话模拟，主动披露不独立 |
| Guardian | 首次污染被废弃，后续draft和patch均有clean回执 | 唯一回执为`compromised` |
| Runtime | 有记录，但数字疑似估算 | 不存在；未知值保持为空 |
| 每书Git | HEAD `bbc8b851...`，清理前有1项未提交序列状态 | HEAD `3ab7b15a...`，清理前干净 |

## Claude Teams样本的有效结论

- 本地Teams元数据确认创建了Writer、第二版Writer、Patch Writer、Blind Reader和Chapter Editor成员，并非主会话简单改角色名。
- Guardian真实拦截了第一次胶囊污染，随后正式初稿和局部修订得到clean回执。
- 项目证据将模型记为`deepseek-v4-flash`，但Claude Teams元数据显示`deepseek-v4-pro[1m]`，构成明确来源冲突；当前验证器未识别该冲突。
- Writer提示词声称只可访问胶囊，但Teams成员实际`cwd`仍是仓库根目录，因此不能证明文件系统硬隔离。
- 双审会话确实分开，但Writer和两名审稿者使用同一模型来源，属于`single_origin`，不能作为跨模型盲评基准。

文学上，古建职业细节、主角主动选择和“旧街屋顶睁眼”的灾变意象有效；主要风险是开头截止时间语义矛盾、否定翻转残留、中后段解释偏多，以及ASCII引号、比喻密度和固定句首带来的模型痕迹。

## Kimi Code样本的有效结论

- Kimi没有伪造独立Agent、Runtime或胶囊能力；未知Token和耗时保持为空，并明确披露同一会话模拟审稿。
- 正文、Story Engine、场景包、审稿记录和每书Git均已产生，但正式Guardian闭环未完成。
- 唯一Guardian回执为`compromised`，缺少Runtime sidecar且隔离证明为false。
- 章节实际为`exploration`模式，Blind Reader给出`needs_revision`，因此最终只到`editorial_reviewed`，没有资格进入`ready`。

文学上，“三个程雾砚”和第四次审查记录形成了清楚的高概念钩子，职业规则也具有操作感；主要风险是遗漏“推人版本”硬锚点、异常出现偏晚、依赖系统日志公布答案、记忆代价没有落到现实物件，以及主角隐瞒异常并放入证据链的动机不足。

## 当前判断与后续实验

在这两次观测中，Claude Code Agent Teams对Novel Forge的角色编排和流程衔接更适配；Kimi Code单会话可以产出可读初稿，但不能替代原生多角色编排。

用户计划下一轮使用三个分别打开的Claude会话，均指定DeepSeek V4 Flash并开启Thinking，分别承担Writer、Blind Reader和Chapter Editor。后续验证重点应是：

- 三个角色必须具有不同的真实会话标识；
- Blind Reader只能看到正文；
- Chapter Editor可读取正文、规划和盲审结果，但不能读取Writer会话；
- 模型和Thinking状态只能按真实暴露信息记录；
- 未暴露Thinking深度时只记录enabled，禁止杜撰medium/high；
- 最终正文、审稿和状态必须绑定同一正文哈希。

## 处置

完成本脱敏对照样本后，按用户明确授权将两本Demo的以下资产全部移入Windows回收站：

- `books/<slug>/`
- `.local-book-git/<slug>.git/`
- `.local-guardian/<slug>/`

样本不构成文学价值认证、作者批准或发布许可。
