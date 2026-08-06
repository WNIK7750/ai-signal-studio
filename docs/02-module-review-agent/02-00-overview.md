# 02-00 模块总览：审核工作台与 Workspace Agent

## 成品目标

用户与 Workspace Agent 都能对情报执行保留、拒绝、延后、编辑和批量确认；能力开关、审批策略与执行记录真实生效。

## 核心闭环

```text
待审核批次 → 用户或 Agent 提交决策 → 必要时暂停审批 → 恢复执行 → 状态与记录可追踪
```

## 本模块范围

- ReviewBatch、ReviewDecision 与状态流转；
- Review Graph 的 interrupt/resume；
- 批量审核 UI；
- Agent Pack 基础加载与动态 Tool 集合；
- Base Prompt + 模块 Domain Pack 上下文装配；
- LangChain Agent 与 LangGraph Plan/Execute/Replan 工作流；
- Capability Policy 与一次性 Approval Token；
- 结构化 Agent UI；
- 完整 Capability Invocation 记录。

拒绝默认是状态变更，不执行物理删除；Agent 不拥有业务规则，也不能绕过审批。

## 必读资料

1. [02-01 Agent Runtime、能力开关与客制化](02-01-agent-runtime-and-switches.md)
2. [02-02 Workspace Agent 对话持久化](02-02-agent-conversations.md)
3. [02-03 Agent 上下文工程与动态工作流](02-03-agent-context-engineering-and-workflows.md)
4. [02-04 Agent 工作流历史图谱](02-04-agent-workflow-history.md)
5. [02-05 Workspace Agent 最终工程蓝图](02-05-final-agent-engineering-blueprint.md)
6. [05-01 Capability 统一能力契约](../05-platform/05-01-capability-contract.md)
7. [05-02 LangGraph 工作流](../05-platform/05-02-langgraph-workflows.md)
8. [06-02 可观测性与调试](../06-quality-operations/06-02-observability-and-debugging.md)
9. [06-03 安全与审批](../06-quality-operations/06-03-security-and-approval.md)

实施入口：

- [Module 2 Workspace Agent 继续开发提示词](../../prompts/02-module-review-agent/02-workspace-agent-next-slice-coding-agent-prompt.md)
- [Module 2 复杂任务修复与纵向优化提示词](../../prompts/02-module-review-agent/02-workspace-agent-complex-task-repair-coding-agent-prompt.md)

## 机器资料

- [Capability Catalog](../../contracts/01-capabilities/capability-catalog.yaml)
- [Review Graph](../../graph-specs/02-module-review-agent/02-review-graph.yaml)
- [Agent Task Graph 0.4.0](../../graph-specs/02-module-review-agent/02-agent-task-graph.yaml)
- [Agent Pack 示例](../../agent-packs/examples/ai-editor/agent.yaml)

## 完成证据

- Agent 和 REST 使用同一个审核 Application Service；
- 禁用能力无法通过任何入口调用；
- 拒绝和延后只写入审核决定，不删除原始信息；
- 用户可以从运行记录页面追踪 Capability 调用与错误。

## 当前可运行增量

- `GET /api/review-batches/current` 创建或读取当前批次；
- `POST /api/review-batches/{batch_id}/decisions` 通过 `review.batch.submit` 提交决定；
- 审核页支持保留、排除、稍后、标题/摘要校对与 Agent 建议；
- 内置 Agent 的“保留全部待审核信息并确认”调用同一 Capability；
- 对话、Capability 状态和已知错误保存到本地数据库，刷新后自动恢复；
- Agent 采集使用浏览器消息幂等键，重试不会重复创建采集 Run；
- 环境变量 `AI_SIGNAL_DISABLED_CAPABILITIES` 可以阻止已禁用能力。
- `POST /api/agent-conversations/{id}/turns` 创建持久 Turn，并以
  `thread_id=turn_id` 运行真实 LangGraph `StateGraph`；
- 首个 `0.4.0` 纵向闭环已完成“采集 → 查询/筛选 → 推荐 → 结果合并”，
  LangChain Structured Tool 只调用 Capability Executor；
- Turn、Step、事件、结果块、耗时和错误保存到 SQLite，SSE 支持
  `Last-Event-ID` 续传，刷新后从会话消息和 Turn 恢复；
- Agent 页面显示计划、步骤、服务端耗时、3～5 条真实 `signal_preview`、
  部分失败、停止/重试入口及 AI 信息深链；
- 独立 `data/agent-checkpoints.db`（测试工作区使用数据库同目录）保存
  LangGraph checkpoint。

Review Graph 的 interrupt/resume 和 Approval Token 仍是本模块后续增量，不作为当前 UI 闭环的已完成事实。
