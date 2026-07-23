# v5.0 Python 确定性控制与工作区零污染

## 目标

v5.0 不绑定 Claude、Kimi、Codex、OMP、IDE 或具体模型。当前可见 CLI 宿主负责提供
真实独立会话，Python 状态机负责全部机械工作：

1. Python 生成当前角色的有界指令。
2. 宿主创建新的原生角色会话。
3. 宿主按原始 typed operation handle 等待官方终态。
4. 宿主回传终态 envelope 与角色绑定的 `role_result`。
5. Python 校验并写入 Guardian、证据、状态、重试和每书 Git。

Lead 只是可见的传输与调度层，不写正文、不代审、不补造完成态，也不选择来源真相。

## 终态绑定

正式 `completed` 同时绑定：

- role；
- session_id；
- session_instance_id；
- operation_kind 与 operation_id；
- result_transport；
- 角色结构化结果和当前产物。

缺失、错配、晚到或来自已退役会话的结果一律无效。外置不可变
`novel-forge-session-completion/v3` 凭证保存同一 operation 绑定，ready 不能只依赖
项目内自述。

旧的独立 `_issue_workflow_authority()` 入口已移除。控制能力必须绑定仍存活的
`NovelWorkflowOrchestrator`。这能消除实验中出现的直接导入捷径，但不能把同一 OS
用户下的无限制进程变成安全边界；正式宿主仍须限制创作角色权限。

## 零项目写入

创作角色调用前后由 Python 对项目树做快照：

- Writer 唯一可写位置是仓库外 capsule 的 `draft/正文.md`；
- 规划与审稿只经宿主结果通道返回结构化数据；
- 新建项目文件记为 `unexpected_project_artifact`，控制面只删除本次确认新建的路径；
- 修改或删除既有项目文件记为 `control_plane_mutation`，保留现场并停止；
- 失败记录和 Guardian 回执不改写，当前 session 退役，按既有上限换新 session 重试。

VCS 与缓存目录仅作快照排除；`books/`、`.local-book-git/`、`.local-guardian/`、
`data/` 和项目根文件均受保护。

## ACP 边界

ACP 只用于事后取证、成本统计和根因调查。它不是生产会话启动器、结果通道、隐藏控制器
或 ready 依赖。日常生产保持可见 CLI + 通用 Skill + Python 状态机。

## 成本

确定性工作不消耗模型 Token。默认模型调用仍为一次规划、一次正文、Blind Reader、
Chapter Editor；只有真实 MUST 才增加一次集中 Patch 和两次全文复审。MAY、advisory、
哈希、状态、Git 和证据校验不触发生成。第二版仍有 MUST 时停止并询问用户，不自动整章
无限回炉。

## 文学规则

七组最终压力测试只保留脱敏聚合，不把正文或 transcript 回灌日常上下文。生产提示词
只加载 `literary-micro-rules/v4` 的四条角色判断：具体选择与私人代价、身体物件位置
连续、允许误判和不对称关系、禁止规划答卷与解释性修补。
