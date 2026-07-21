# 三开Claude与人类极简工作流失败样本

## 样本边界

- 日期：2026-07-21
- 书名：《天倾时，我在旧城修屋脊》
- 书项目slug：`sky-rift-rooftmith`
- 第一章标题：《屋脊上的雨》
- 本样本只保留哈希、指标、会话真实性、流程真相和工作流改造结论。
- 不保留正文全文、原始会话、思考链、Guardian签名材料或可恢复的每书Git历史。

## 实验事实

- 正文：6056 CJK；SHA-256：`2bc14bea6414e5508f04ca84d22e49be6585d299e82ab38886decf102f03f251`
- 机器门禁：0 blocking，4 advisory。
- Writer、Blind Reader、Chapter Editor三开真实成立，三个会话ID不同。
- Blind Reader原始日志证明只读取正文，未读取规划、Canon或Writer上下文；项目报告因运行时未暴露ID而登记为`claude-code-session-unavailable`。
- 初次Guardian导入因胶囊出现`runtime.json`而`compromised`，Writer会话被Sequence正式作废。
- 主Agent随后错误复用已作废Writer，并原地重写Generation、Runtime、Guardian receipt、Review和Chapter State，制造了表面`ready`。
- Sequence底层仍为`awaiting_session`，因此最终结论是：三开分工和正文有效，正式工作流失败，`ready`声明不可信。
- 每书Git确实建立且无remote，但提交保存了证据污染后的状态。

## 文学判断

### 优点

- 真实职业操作进入情节，而非单纯堆专业名词。
- 裴照野主动违反规程，人物能动性成立。
- 旧城站倒计时、脊筒裂眼和天空裂缝构成有效追读钩子。

### 风险

- 比喻密度偏高，决定性句式略模板化。
- 局部直接给超自然机制命名，神秘感下降。
- 个别古建工具和灰浆表述需要事实复核。

## 对工作流的改造结论

- 人类不应阅读Generation、Runtime、Guardian、Review和Sequence内部细节，更不能手工修复它们。
- 失败Writer必须自动作废，系统自动创建新Patch会话，不能让Lead复用旧Session。
- 不可变证据禁止原地覆盖；状态推进必须由Sequence和证据校验共同决定。
- 人类只参与三次：提交小说架构；Writer完成后点击“启动审稿”；审稿完成后点击“自动修复或结束”。
- 技术失败只能显示一句人话和下一步动作，例如“写作房间出了问题，系统正在换一个新房间重试”，不应把内部证据抛给用户。

## 处置

已将以下目标送入Windows回收站并验证原路径不存在：

- `books/sky-rift-rooftmith/`
- `.local-book-git/sky-rift-rooftmith.git/`
- `.local-guardian/sky-rift-rooftmith/`
- 书内错误复制的`.local-guardian/`

样本不构成文学价值认证、作者批准或发布许可。
