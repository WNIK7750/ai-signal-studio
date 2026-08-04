# Module 1 编程 Agent 实施提示词

你正在实现 AI Signal Studio 的 Module 1：可用的 AI 情报时间线。

先阅读：

- `AGENTS.md`
- `docs/01-module-timeline/01-00-overview.md`
- `docs/00-project/00-01-project-charter.md`
- `docs/00-project/00-03-system-architecture.md`
- `docs/00-project/00-04-module-boundaries.md`
- `docs/05-platform/05-01-capability-contract.md`
- `docs/05-platform/05-02-langgraph-workflows.md`
- `docs/05-platform/05-03-frontend-architecture.md`
- `docs/05-platform/05-04-ui-layout-and-components.md`
- `docs/05-platform/05-05-design-tokens-and-themes.md`
- `docs/05-platform/05-06-icon-system.md`
- `docs/07-delivery/07-01-development-roadmap.md`
- `contracts/01-capabilities/capability-catalog.yaml`
- `contracts/05-design-system/design-tokens.schema.json`
- `contracts/05-design-system/themes.example.json`
- `graph-specs/01-module-timeline/01-collection-graph.yaml`

## 目标

交付一个前后端可用闭环：配置来源 → 手动采集 → 去重与结构化分析 → 按日期查看时间线；Workspace Agent 能调用同一能力启动采集和查询时间线。

## 工作方式

- 使用简单 TDD；先写 2～6 个关键失败测试。
- 不先实现后续模块。
- 不引入 Redis、Celery、Kafka、向量数据库或微服务。
- 先使用 SQLite、本地进程任务和 Fake LLM/Search 测试。
- 所有业务动作通过 Capability/Application Service。
- LangGraph 用于采集长流程，不承载普通查询 CRUD。
- 使用 Codex 式稳定应用壳，但时间线页面只在筛选确有需要时打开右侧面板。
- 功能入口使用统一 Tabler Outline 图标；视觉值通过设计令牌提供。

## 必须交付

1. 项目可启动；
2. 数据迁移；
3. SourceConfig、CollectionRun、RawItem、IntelligenceItem；
4. 至少 RSS 和 GitHub Releases Collector；
5. Collection Graph；
6. 结构化摘要/分类/评分；
7. Timeline REST API；
8. Timeline 页面与“立即采集”按钮；
9. 响应式 AppShell 与场景化时间线布局；
10. Signal Light/Dark 一键主题切换和基础令牌自定义；
11. `collection.run.start`、`intelligence.timeline.query` Capability；
12. 两个 LangChain Tool Adapter；
13. Run 详情基础视图；
14. 模块测试和一个 E2E 冒烟。

## 停止条件

当上述闭环可运行、测试通过、文档同步后停止。不要继续实现审核、海报、Agent Pack、实时语音、A2A 或 MCP。
