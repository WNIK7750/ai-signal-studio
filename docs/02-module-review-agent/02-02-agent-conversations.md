# 02-02 Workspace Agent 对话持久化

## 1. 产品边界

第一版是无登录的本地单工作区应用。对话历史保存在部署实例的 SQLite
数据库中，不引入用户表、账号体系、云同步或复杂会话管理。界面支持多个本地
会话的新建、搜索、切换、重命名、置顶、归档、软删除与恢复；不增加文件夹、
共享、团队权限或跨设备同步。

## 2. 数据事实来源

`agent_conversations` 保存会话标题及其来源、置顶/归档/软删除时间、最后消息
时间、活动状态和更新时间。`active_turn_id` 指向当前持久 Agent Turn；
Turn 终结后清空。`unread` 仍为后续后台会话通知保留。
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

新的长任务入口先保存用户消息与 `turn.created`，返回 `202 + turn_id`，再由
Product Turn Harness 执行。Graph 事件必须先写入 `agent_turn_events`，SSE 才能发送；
终态消息、Plan、Step、ResultBlock、错误和总耗时均以数据库为事实来源。

## 4. REST 边界

- `GET /api/agent-conversations/current`：读取或创建当前活动会话及最近消息；
- `GET /api/agent-conversations`：按活动、归档或软删除范围读取会话摘要；
- `POST /api/agent-conversations`：创建新会话；
- `GET /api/agent-conversations/{id}`：读取指定会话和消息；
- `PATCH /api/agent-conversations/{id}`：手动重命名或置顶；
- `POST /api/agent-conversations/{id}/archive`：归档；
- `POST /api/agent-conversations/{id}/restore`：恢复归档或软删除会话；
- `DELETE /api/agent-conversations/{id}`：软删除，不物理删除消息；
- `POST /api/agent-runs`：兼容的薄入口，接受可选的 `conversation_id` 和
  `client_message_id`，实际持久化与执行由 Application Service 完成；
- `POST /api/agent-conversations/{id}/turns`：创建幂等 Turn，返回 `202`；
- `GET /api/agent-turns/{id}`：读取持久计划、终态、耗时、结果块和错误；
- `GET /api/agent-turns/{id}/events`：SSE 事件流，使用递增序号并支持
  `Last-Event-ID`；
- `POST /api/agent-turns/{id}/cancel|resume`：停止或以相同 `thread_id`
  恢复执行；
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

- API：A/B 会话隔离、标题保护、置顶排序、归档/软删除恢复、旧库增量升级、
  消息顺序、刷新恢复和幂等重试；
- 浏览器：新建和切换会话、重命名、置顶、归档、软删除/撤销，刷新后会话与
  消息仍存在；
- 安全：数据库仅记录图片数量，不保存图片 Data URL；
- 回归：原有采集、审核、卡片和模型切换流程继续通过。
