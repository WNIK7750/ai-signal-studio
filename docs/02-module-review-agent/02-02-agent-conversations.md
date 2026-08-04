# 02-02 Workspace Agent 对话持久化

## 1. 产品边界

第一版是无登录的本地单工作区应用。对话历史保存在部署实例的 SQLite
数据库中，不引入用户表、账号体系、云同步或复杂会话管理。当前界面只恢复最近
一个活动会话；后续需要多会话时再增加归档与切换入口。

## 2. 数据事实来源

`agent_conversations` 保存会话标题、活动状态和更新时间。
`agent_messages` 按时间保存用户与 Agent 消息，并记录：

- `client_message_id`：浏览器生成的幂等键；
- `request_id`：与 Capability Invocation 关联；
- Capability ID 与执行状态；
- 可定位的错误码和实际模型 ID；
- 图片数量，不保存 Data URL、图片二进制或完整外部正文。

前端本地状态只保存正在发送的消息、未提交草稿和图片预览；已完成消息必须以
服务端历史为准。

## 3. 一轮对话的执行顺序

```text
读取或创建当前会话
→ 先保存用户消息
→ 通过 WorkspaceAgentService 调用 Capability
→ 保存 Agent 回复、能力状态和错误码
→ 返回消息 ID
→ 前端刷新当前会话查询
```

相同 `conversation_id + client_message_id` 只允许执行一次。网络重试返回已经
保存的 Agent 回复，不能重复触发采集等外部副作用。若执行失败，已知错误也要
保存成 Agent 消息，使刷新后不会只剩半轮对话。

## 4. REST 边界

- `GET /api/agent-conversations/current`：读取或创建当前活动会话及最近消息；
- `POST /api/agent-runs`：兼容的薄入口，接受可选的 `conversation_id` 和
  `client_message_id`，实际持久化与执行由 Application Service 完成；
- `GET /api/capability-invocations`：查看能力调用状态和错误码。

Router 不直接写业务表，Agent 也不直接访问数据库；采集、时间线、审核和卡片
动作仍通过统一 Capability Executor。

## 5. 采集结果在对话中的表达

- `completed + items_added > 0`：说明新增数量；
- `completed + items_added = 0`：明确说明内容已去重，而不是暗示没有执行；
- `partial`：说明新增数量和失败来源数；
- `failed`：显示可定位原因，例如 `NO_ENABLED_SOURCES`；
- Capability Invocation 的状态必须与业务 Run 的 `partial/failed` 一致。

确定性的采集、审核和卡片动作不依赖聊天模型是否可用；模型只参与需要自然语言
生成或图片理解的对话。

## 6. 验证

- API：消息顺序、刷新恢复、幂等重试、零新增和无来源失败；
- 浏览器：发送采集指令、看到 Capability 状态、刷新后消息仍存在；
- 安全：数据库仅记录图片数量，不保存图片 Data URL；
- 回归：原有采集、审核、卡片和模型切换流程继续通过。
