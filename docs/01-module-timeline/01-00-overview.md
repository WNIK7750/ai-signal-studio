# 01-00 模块总览：AI 情报时间线

## 成品目标

用户可以配置少量信息来源，手动或定时采集 AI 信息，在前端按日期查看去重、摘要和三级颜色标识后的信息流；Workspace Agent 通过同一能力入口启动采集和查询结果。

## 核心闭环

```text
配置来源 → 发起采集 → 标准化与去重 → 结构化分析 → 按日期查看时间线
```

## 本模块范围

- FastAPI、Next.js、SQLite 与 Alembic 的最小可运行基线；
- RSS、GitHub Releases 和一个通用网页或搜索 Adapter；
- Collection Graph；
- 摘要、分类、三级标识与时间线查询；
- `collection.run.start` 与 `intelligence.timeline.query` Capability；
- Timeline 页面、立即采集入口和 Run 详情基础视图；
- Codex 式稳定应用壳、场景化时间线布局与可切换主题；
- Workspace Agent 的两个薄 Tool Adapter。

暂不实现审核、海报、Agent Pack、实时语音、A2A、MCP、向量数据库或独立任务集群。

## 必读资料

1. [00-04 模块边界](../00-project/00-04-module-boundaries.md)
2. [05-01 Capability 统一能力契约](../05-platform/05-01-capability-contract.md)
3. [05-02 LangGraph 工作流](../05-platform/05-02-langgraph-workflows.md)
4. [05-03 前端架构](../05-platform/05-03-frontend-architecture.md)
5. [05-04 UI 布局与组件分类](../05-platform/05-04-ui-layout-and-components.md)
6. [05-05 设计令牌与主题](../05-platform/05-05-design-tokens-and-themes.md)
7. [05-06 线性图标系统](../05-platform/05-06-icon-system.md)
8. [06-01 简单 TDD 与测试策略](../06-quality-operations/06-01-simple-tdd-and-testing.md)

## 机器资料

- [Capability Catalog](../../contracts/01-capabilities/capability-catalog.yaml)
- [Collection Graph](../../graph-specs/01-module-timeline/01-collection-graph.yaml)
- [Module 1 实施提示词](../../prompts/01-module-timeline/01-coding-agent-prompt.md)

## 完成证据

- 用户点击采集后能看到时间线结果；
- 时间线布局在桌面和不同电脑窗口宽度下保持主要任务优先；
- 用户可一键切换主题，并通过选择器与滑动条调整允许的设计令牌；
- 重复来源只形成一条标准化信息；
- Agent Tool 与 REST 调用同一 Capability；
- Run 失败能定位到来源、Provider 或 Graph 节点；
- 模块测试、契约验证和一个 Playwright 冒烟流程通过。

## 当前可运行增量

- 普通工作区首次启动会写入 OpenAI 官方 RSS、LangGraph Releases 和
  Transformers Releases 三个可编辑真实来源，不再依赖固定 Demo 内容；
- 测试环境通过 `AI_SIGNAL_SOURCE_SEED_MODE=demo` 使用确定性样本；
- 无启用来源时 Run 返回 `failed / NO_ENABLED_SOURCES`；
- 来源部分失败时 Run 与 Capability Invocation 都记录 `partial`，Agent
  会如实说明失败来源数；
- 通用网页或搜索 Adapter 仍是后续增量，当前已完成的是 RSS 与 GitHub
  Releases。
