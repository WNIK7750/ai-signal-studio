# Module 2 Workspace Agent 继续开发提示词

你正在 AI Signal Studio 仓库根目录继续开发，下文记为 `<repo-root>`。当前任务是直接
实现 Workspace Agent `workflow_version=0.4.0` 的第一个真实纵向闭环，不再重新调研
或重写蓝图。

## 开发姿态

- 相信编程 Agent 的实现和调试能力，先做成品，再根据真实问题调整。
- 使用简单 TDD：先写 2～6 个能固定当前用户行为的失败测试，然后立即实现；下一段行为
  再补少量测试。不预先穷举全部边角，不追求覆盖率数字。
- 开始前只运行一次相关基线。开发中运行目标测试，结束时再跑完整相关回归。
- 不要停在设计、Schema、后端或 UI 中间层；自主完成本提示词定义的前后端闭环。
- 能从现有代码和文档判断的事项直接采用最简单一致的实现，不反复请求确认。
- 普通重构、依赖安装、Bug 修复、数据兼容和测试调整直接推进。只有确实需要改变
  `0.4.0` 工作流拓扑、公共契约或引入新基础设施时，才提交
  `Blueprint Change Proposal`；不要把它当作日常开发门禁。
- 当前工作树包含已完成的 E0/E1 和任务工作台改动。先阅读 diff，在现有实现上继续；
  不 reset、不回滚、不覆盖无关改动。

## 开始前读取

按以下顺序读取，不做第二轮大范围架构研究：

1. `AGENTS.md`
2. `docs/02-module-review-agent/02-00-overview.md`
3. `docs/02-module-review-agent/02-05-final-agent-engineering-blueprint.md`
4. `docs/02-module-review-agent/02-03-agent-context-engineering-and-workflows.md`
5. `docs/02-module-review-agent/02-01-agent-runtime-and-switches.md`
6. `docs/02-module-review-agent/02-02-agent-conversations.md`
7. `docs/05-platform/05-01-capability-contract.md`
8. `docs/05-platform/05-02-langgraph-workflows.md`
9. `docs/06-quality-operations/06-01-simple-tdd-and-testing.md`
10. `docs/07-delivery/07-04-optimization-implementation-status.md`
11. `graph-specs/02-module-review-agent/02-agent-task-graph.yaml`
12. `contracts/01-capabilities/capability-catalog.yaml`
13. `contracts/04-interoperability/openapi-outline.yaml`

## 当前代码入口

先基于这些现有文件继续，不建立平行业务实现：

| 责任 | 当前入口 |
|---|---|
| 旧同步 Agent 与关键词路径 | `apps/api/src/ai_signal_api/agent_runtime/service.py` |
| 会话、消息持久化与幂等 | `apps/api/src/ai_signal_api/modules/agent/conversation_service.py` |
| Agent REST | `apps/api/src/ai_signal_api/routers/agent.py` |
| Agent/Turn 公共 Schema | `apps/api/src/ai_signal_api/schemas.py` |
| SQLite 模型与兼容升级 | `apps/api/src/ai_signal_api/models.py`、`apps/api/src/ai_signal_api/database.py` |
| Capability 权威执行入口 | `apps/api/src/ai_signal_api/capabilities/core.py`、`apps/api/src/ai_signal_api/capabilities/registry.py` |
| 采集业务 | `apps/api/src/ai_signal_api/modules/collection/service.py` |
| AI 信息查询与信息库 | `apps/api/src/ai_signal_api/modules/intelligence/timeline.py`、`apps/api/src/ai_signal_api/modules/intelligence/library.py` |
| 工作区模型解析 | `apps/api/src/ai_signal_api/modules/models/service.py` |
| 当前模型调用适配 | `apps/api/src/ai_signal_api/integrations/llm/chat.py` |
| Agent 页面 | `apps/web/src/features/agent/agent-screen.tsx` |
| 前端 API 契约 | `apps/web/src/lib/api.ts` |
| 公共样式与结果块 | `apps/web/src/app/globals.css` |
| 现有 Agent 回归 | `tests/api/test_agent_capability.py`、`tests/api/test_agent_conversations.py` |
| AI 信息回归 | `tests/modules/intelligence/` |
| Agent E2E | `apps/web/e2e/workspace-agent.spec.ts` |

允许在下列位置新增实现，但只创建当前闭环实际使用的文件：

```text
apps/api/src/ai_signal_api/agent_runtime/
├── contracts.py
├── context.py
├── graph.py
├── harness.py
└── tools.py

apps/api/src/ai_signal_api/modules/intelligence/agent/
├── domain.yaml
├── prompt.md
├── schemas.py
└── tools.py

apps/api/src/ai_signal_api/modules/collection/agent/
├── domain.yaml
├── prompt.md
├── schemas.py
└── tools.py

tests/modules/agent_runtime/
```

文件可以在实现后根据职责合并；不要为了与目录树完全一致而保留空文件或空抽象。

## 本批次成品场景

用户在已有 Agent 对话中输入：

> 收集最近 24 小时的 AI 信息，并从中推荐 5 条最值得看的 Agent 相关内容。

用户应看到：

1. 消息立即进入当前会话，刷新后仍存在；
2. Agent 显示已接收、规划、采集、筛选、推荐和完成等真实流式事件与递增耗时；
3. 真实 LangGraph 执行“采集 → 查询/筛选 → 推荐 → 结果合并”，不是关键词
   `if/return`；
4. 采集继续调用现有 `collection.run.start` Capability；
5. 查询和推荐通过 Intelligence Application Service 与 Capability 完成；
6. 单个来源失败时，保留成功来源和已有信息，最终状态为 `partial`，不中断整个回复；
7. 最终显示 3～5 个 `signal_preview`，每项含颜色语义、标题、100～400 字内的快速摘要、
   来源、发布时间和真实 `information_id`；
8. 每项提供后端生成的站内路径：
   `/timeline?focus=<item_id>&run=<run_id>&from=agent&conversation=<conversation_id>`；
9. 提供“查看全部”“查看运行详情”和对失败来源的重试入口；
10. 最终消息、步骤、耗时、结果块和错误都以数据库记录为事实来源。

## 实施范围

### 1. 真实依赖

更新 `pyproject.toml`、`requirements.lock` 和必要的安装脚本，加入并实际使用：

- `langchain`
- `langchain-openai`
- `langgraph`
- `langgraph-checkpoint-sqlite`

`langchain-core` 单独存在不算完成。测试可以使用 Fake Chat Model，但必须经过真实
LangChain Tool/Agent 与 LangGraph StateGraph 路径。
Agent Runtime 是产品主路径，依赖必须能由现有 `scripts/bootstrap.ps1` 从
`requirements.lock` 安装；不要只写进一个实际不会安装的 optional group。

### 2. Turn、事件与结果契约

实现并持久化蓝图中的最小公共契约：

- `AgentTurnState`
- `AgentTurnEvent`
- `AgentTurnResult`
- `AgentPlan` / `PlanStep`
- `ErrorEnvelope`
- `EvidenceRef`
- `AgentResultBlock`
- `ExecutionManifest`

在现有 `/api/agent-conversations` 命名下提供创建 Turn、读取 Turn、SSE 事件流、取消和
恢复入口；保留现有 `POST /api/agent-runs` 的兼容行为，前端迁移完成前不要破坏旧测试。
SSE 事件先持久化再发送，使用单调递增序号并支持 `Last-Event-ID` 续传。
新 Turn 复用现有 `AgentConversationModel.active_turn_id`、消息和
`conversation_id + client_message_id` 幂等规则，不建立平行 Conversation 系统。

首批稳定事件至少包括：

```text
turn.created
plan.ready
step.started
tool.started
tool.completed
result.block
turn.completed | turn.partial | turn.failed | turn.cancelled
```

### 3. Context 与动态 Tool

- Base Prompt 每次模型调用都存在并带版本；
- Bootstrap 只提供 Domain Index 和 Capability Snapshot；
- 当前步骤只加载 `collection`、`intelligence` 中真正需要的 Prompt、Tool Schema 和
  Evidence；
- Agent Tool 只能调用 `CapabilityExecutor`，不能访问 Session、Repository 或 ORM；
- 禁用 Capability 不进入 Tool 列表，伪造调用仍被执行层拒绝；
- Trace 只记录层名、版本、大小和摘要，不记录密钥、完整 Base Prompt 或网页全文。

### 4. LangGraph 与 Product Turn Harness

按照
`graph-specs/02-module-review-agent/02-agent-task-graph.yaml`
实现本场景会经过的真实节点行为。必须包含：

- Deterministic Fast Plan 与 Structured LLM Plan 的统一 `AgentPlan`；
- Plan Validator；
- Ready Step Scheduler；
- Step Context/Tool Resolver；
- Action Binder、Action Validator；
- Capability/Policy Gate；
- Capability Executor；
- Event/Artifact Recorder；
- Result Join、Outcome Inspector、Result Composer 和 Finalizer；
- 独立 `data/agent-checkpoints.db` SQLite Checkpointer；
- `thread_id=turn_id`；
- `turn_id + step_id + capability_id + input_digest` 幂等键；
- 最多 5 个步骤、2 次重规划、3 个并行只读步骤；
- 取消、部分成功、超时和可恢复错误的稳定终态。

不要为尚未使用的 Domain 建空 Pack，也不要用 25 个无意义的透传函数假装完成图谱。
同一职责可以先在一个模块内实现，但节点事件和状态语义必须符合 Graph Spec。

### 5. Intelligence 结果

在 Intelligence 模块增加最小推荐能力，先使用可解释的确定性候选排序和结构化 Evidence；
模型只负责用户意图、计划和必要的摘要/推荐理由，不让模型编造信息 ID、来源或链接。
结果摘要遵守现有 100～1000 字配置边界，本场景默认不超过 400 字。

### 6. Agent UI

在现有 `agent-screen.tsx` 上完成：

- 乐观显示用户消息和已接收状态；
- SSE 生命周期管理、断线续传和终态后关闭；
- 可折叠计划和步骤；
- 当前步骤、服务端耗时、部分成功与可恢复错误；
- `signal_preview` 信息卡片及真实站内跳转；
- 停止、重试失败来源、查看全部和查看运行详情；
- 页面刷新后从 Turn/Conversation 数据恢复，不依赖内存中的 React 状态。

保持现有多会话、重命名、置顶、归档和软删除行为，不重做 Agent 页面框架。
`agent-screen.tsx` 已经较大，优先把 SSE、进度和结果块分别放入
`agent-event-stream.ts`、`agent-turn-progress.tsx`、`agent-result-blocks.tsx` 等小组件，
主页面只做最少接线。

## 简单 TDD 起点

先写以下 6 个失败测试，然后立即实现。若实现中出现真实回归，再补最小测试：

1. `tests/modules/agent_runtime/test_context.py`：只装配 Base +
   `collection/intelligence`，未选 Domain 的 Prompt 和 Tool 不出现；
2. `tests/modules/agent_runtime/test_workspace_graph.py`：Fake Model 通过真实 StateGraph
   完成采集、查询和推荐，调用顺序与依赖正确；
3. `tests/modules/agent_runtime/test_workspace_graph.py`：一个来源失败时仍生成
   `partial` 和可用 `signal_preview`；
4. `tests/api/test_agent_turn_stream.py`：202、事件序号、`Last-Event-ID` 续传、终态持久化；
5. `tests/api/test_agent_turn_stream.py`：重复 `client_message_id` 不重复采集或创建 Turn；
6. `apps/web/e2e/workspace-agent.spec.ts`：用户看到运行耗时、部分/完成状态、信息卡片，
   点击后进入带 `focus` 的 AI 信息页。

不要先写 24～40 个评测用例。本批次先把这 6 个关键行为做通；完成纵向闭环后，再在
`tests/evals/agent/` 增加首批 24 个场景。

## 推荐执行循环

```text
1. 运行一次相关基线并记录结果
2. 写上述 6 个失败测试
3. 实现后端 Turn + Context + Graph + Capability 闭环
4. 接入 SSE 与 Agent UI
5. 用 Fake Model 完成 Playwright
6. 修复确定性链路中出现的问题
7. 运行目标测试、全量测试、契约校验和构建
8. 更新任务状态和实际验收证据
```

本提示词对应模块增量禁止调用用户已配置的真实模型。单元、模块、Graph、API、前端和
Playwright 全部使用 Fake/Fixture/HTTP Mock。只有整个产品完整链路准备发布、确定性
全量回归已经通过时，才由独立 `tests/live/` 验收入口在
`AI_SIGNAL_RUN_LIVE_MODEL_TESTS=1` 下执行一个受控完整链路；不得把真实模型 Smoke
添加回上述循环，也不得读取或打印密钥。

## 验收命令

```powershell
.\.venv\Scripts\python.exe -m pytest tests/modules/agent_runtime tests/api/test_agent_turn_stream.py tests/api/test_agent_capability.py tests/api/test_agent_conversations.py -q
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\pnpm.ps1 --dir apps/web test
.\scripts\pnpm.ps1 --dir apps/web test:e2e
.\scripts\pnpm.ps1 --dir apps/web build
.\.venv\Scripts\python.exe scripts/validate_contracts.py
git diff --check
```

## 文档与停止条件

完成后更新：

- `docs/07-delivery/07-04-optimization-implementation-status.md`
- `contracts/01-capabilities/capability-catalog.yaml`
- `contracts/04-interoperability/openapi-outline.yaml`
- 受影响的 Module 2 文档

如果没有改变 `0.4.0` 拓扑，只更新实现状态和证据，不重复生成 Figma。如果确实改变
拓扑，才同步：

- `graph-specs/02-module-review-agent/02-agent-task-graph.yaml`
- `docs/02-module-review-agent/02-04-agent-workflow-history.md`
- Figma 当前图
- `workflow_version`

当本提示词的用户场景在前端、Agent、Capability、持久化和测试上形成可运行闭环后停止。
不要顺手实现全部 A2A/MCP、全部站内写能力、向量数据库、多 Agent、工作流编辑器或
分布式队列。
