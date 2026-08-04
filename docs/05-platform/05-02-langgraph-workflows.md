# 05-02 LangGraph 工作流

## 1. 使用边界

使用 LangGraph 的场景：

- 多步骤长任务；
- 并行采集或分析；
- 人工审核与恢复；
- 需要 checkpoint、重试、回放的流程；
- 跨 Capability 的编排。

普通查询和单次编辑直接调用 Capability，不强制经过 Graph。

## 2. Graph 列表

### collection_graph

```text
resolve_request
→ load_sources
→ dispatch_collectors
→ normalize
→ deduplicate
→ persist_items
→ analyze_items
→ build_review_batch
→ complete
```

### review_graph

```text
load_batch
→ prepare_review
→ interrupt(review decisions)
→ validate_decisions
→ apply_decisions
→ complete
```

### poster_graph

```text
load_approved_items
→ interrupt(confirm draft generation)
→ generate_drafts
→ save_drafts
→ interrupt(confirm rendering)
→ render_cards
→ complete
```

### agent_task_graph

用于 Workspace Agent 中超过单个 Tool Loop 的长任务：

```text
plan
→ execute capability/subgraph
→ inspect result
→ request approval when needed
→ finalize
```

## 3. State 规则

State 只保存：

- ID；
- 小型结构化中间结果；
- 当前阶段；
- 警告与错误；
- 审批数据；
- 进度。

不保存：

- 完整网页正文；
- 图片二进制；
- 音频流；
- 大型文档；
- 数据库连接或 Service 实例。

## 4. 节点规则

每个节点：

- 输入输出明确；
- 单一责任；
- 外部依赖通过 Runtime Context 注入；
- 返回 State patch，不任意重写全部 State；
- 容易单元测试；
- 副作用节点支持幂等。

## 5. Interrupt 规则

- 审核与确认使用 `interrupt()`；
- interrupt 前的副作用必须幂等；
- interrupt payload 只使用 JSON 可序列化简单数据；
- 不在 try/except 中包裹 interrupt；
- 不依赖 interrupt 在节点中的隐式顺序变化；
- resume 输入必须经过 Pydantic 校验。

## 6. Checkpointer

第一版：

- 开发环境可使用 SQLite Checkpointer；
- thread_id 使用业务 Run ID；
- checkpoint_id 写入执行记录；
- 对话长期记忆与 Graph checkpoint 分开管理。

## 7. 并行

采集来源、逐条分析可使用 `Send` 或等价 map-reduce 模式。并行任务必须：

- 有稳定 item ID；
- 独立失败可记录；
- 汇总节点能处理部分成功；
- 设置最大并发。

## 8. 回放

回放用于调试，不等同于无副作用重放。checkpoint 后的 LLM、HTTP 请求和副作用节点可能重新执行，因此所有写操作使用 idempotency key。

## 9. Graph 规格

机器可读示例见：

- `graph-specs/01-module-timeline/01-collection-graph.yaml`；
- `graph-specs/02-module-review-agent/02-review-graph.yaml`；
- `graph-specs/04-module-poster-interop/04-poster-graph.yaml`。
