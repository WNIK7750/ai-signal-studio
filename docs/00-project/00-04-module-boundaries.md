# 00-04 模块边界

## 1. 模块划分

### collection

负责来源配置、采集任务、原始结果与采集错误。不了解重要性评分与海报。

### intelligence

负责标准化信息、摘要、分类、评分、实体、事件聚类与时间线查询。

### review

负责审核批次、决策、确认请求与状态流转。删除默认映射为拒绝或归档。

### poster

负责卡片草稿、模板参数、编辑、渲染与导出。只接收已允许进入卡片流程的信息。

### agent_runtime

负责加载 Agent Pack、选择工具、构建 LangChain Agent、执行对话。不得拥有业务数据规则。

### orchestration

负责 LangGraph 状态、节点、子图、interrupt、恢复和长任务进度。

### memory

负责 Agent Pack 文档导入、解析、索引、检索和经过确认的观察记录。

### artifacts

负责文档与图片文件、元数据、解析结果和关联关系。实时语音不长期保存原音频是默认策略。

### realtime_transcription

负责实时转写会话、WebSocket 消息、Provider Adapter 和增量文字。只产生文字输入，不自动执行业务操作。

### interoperability

负责 REST/OpenAPI、A2A 和 MCP 的外部适配，不拥有业务规则。

### observability

负责 Run、Capability Invocation、Graph Thread、错误与调试视图。

## 2. 模块通信

首选直接调用类型化 Application Service。仅当需要异步解耦、审计或多个消费者时发布领域事件。

事件示例：

```text
CollectionRunCompleted
ReviewBatchCreated
ReviewDecisionApplied
PosterDraftCreated
PosterRendered
AgentPackImported
TranscriptFinalized
```

第一版不引入消息队列。事件在进程内发布，并记录到数据库或 JSONL。

## 3. 每个模块的公共面

每个模块最多暴露：

```text
contracts.py     输入输出 Schema
service.py       Application Service
capabilities.py  对外能力
events.py        领域/应用事件
ports.py         需要外部实现的 Protocol
```

内部 Repository、ORM、Prompt 和辅助函数不作为跨模块公共 API。

## 4. 允许的共享内容

`packages/shared` 仅允许：

- ID、时间、分页等通用类型；
- 错误基类；
- ExecutionContext；
- 幂等键；
- 统一 Result/Problem Details；
- 日志与追踪接口。

禁止建立“万能 utils”。

## 5. 模块完成模板

每个宏模块落地时至少包含：

- 一个端到端用户场景；
- Application Service；
- Capability；
- REST 接口；
- Agent Tool Adapter；
- 数据持久化；
- 前端页面；
- 关键测试；
- 执行记录。
