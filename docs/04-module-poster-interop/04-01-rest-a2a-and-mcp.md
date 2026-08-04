# 04-01 REST、A2A 与 MCP

## 1. 统一原则

三种协议都是 Capability 的 Adapter，不实现独立业务规则。

## 2. REST / OpenAPI

供前端、脚本与普通集成使用。

主要资源：

```text
POST /api/collection-runs
GET  /api/collection-runs/{id}
GET  /api/timeline
GET  /api/review-batches/{id}
POST /api/review-batches/{id}/decisions
POST /api/poster-drafts/batch
PATCH /api/poster-drafts/{id}
POST /api/poster-drafts/{id}/render
POST /api/transcription/sessions
GET  /api/transcription/sessions/{id}
POST /api/agent-runs
GET  /api/runs/{id}
```

要求：

- 稳定 operationId；
- Pydantic 输入输出；
- RFC 9457 风格 Problem Details 或统一错误模型；
- 变更同步导出 OpenAPI；
- WebSocket 协议另外维护 JSON Schema，因为 OpenAPI 不完整表达 WebSocket。

## 3. MCP

### Resources

```text
app://architecture
app://capabilities/catalog
app://agent-packs/{id}
app://graphs/{id}
app://runs/{id}
app://contracts/openapi
```

### Tools

原子或中等粒度能力：

```text
collection.run.start
intelligence.timeline.query
review.batch.submit
poster.draft.generate
poster.card.render
memory.pack.import
```

敏感工具必须保留 Capability 执行层审批，不能只依赖 MCP Client 提示。

## 4. A2A

用于较高层、有状态、可能长时间运行的任务：

- 收集一段时间内的 AI 情报；
- 分析指定主题趋势；
- 建立待审核批次；
- 在用户审批后生成卡片草稿。

第一版 A2A Skills：

```text
collect_ai_intelligence
query_ai_timeline
prepare_poster_drafts
```

`.well-known/agent-card.json` 只包含公开能力和认证说明，不放密钥或内部实现细节。

## 5. 粒度选择

- REST：面向资源和 UI；
- MCP Tool：较原子的能力；
- A2A Skill：面向结果的长任务；
- LangChain Tool：应用内 Agent 的能力调用。

## 6. 外部 Agent 权限

外部 Agent 使用独立 actor_type、凭据和 Capability Policy。默认：

- 可以创建采集任务；
- 可以查询自己创建的任务；
- 不能物理删除；
- 不能绕过卡片生成/发布确认；
- 不能直接修改长期正式记忆。
