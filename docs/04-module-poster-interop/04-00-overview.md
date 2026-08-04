# 04-00 模块总览：信息卡片与后续外部接口

## 成品目标

用户把审核保留的信息整理成可快速扫读的封面卡片，按月份、日期和条件浏览，打开后查看摘要、要点与原始地址。PNG 海报与 A2A/MCP 在浏览闭环稳定后继续实现。

## 核心闭环

```text
已保留情报 → 设置摘要上限 → 整理卡片 → 日期/条件浏览 → 查看详情 → 打开原文
```

## 当前实现范围

- 仅从 `keep` 审核决定生成卡片，重复生成保持幂等；
- 标题优先使用原始标题，审核明确改写后使用编辑标题；
- 详情摘要上限可在 100～1000 字间设定，默认 400 字；
- 来源提供合适 `cover_url` 时使用原封面，否则使用纯 HTML/CSS 文字模板；
- 默认模板在六种相近浅天蓝/青绿色间随机，并在引语底板与网格便签底板间切换；
- 顶栏使用可横向滚动的月内日期 Tab，右端选择月份；
- 左侧筛选信息标识、来源和主题，右侧按需打开详情；
- 内置 Agent 与 REST 共用 `poster.draft.generate` Capability；
- 运行记录展示能力调用。

## 后续范围

- Poster Graph、编辑与 PNG Artifact；
- A2A Agent Card、MCP Resources/Tools；
- 外部 Agent Policy、导出与审计。

## 必读资料

1. [04-01 REST、A2A 与 MCP](04-01-rest-a2a-and-mcp.md)
2. [05-01 Capability 统一能力契约](../05-platform/05-01-capability-contract.md)
3. [05-02 LangGraph 工作流](../05-platform/05-02-langgraph-workflows.md)
4. [05-03 前端架构](../05-platform/05-03-frontend-architecture.md)
5. [06-03 安全与审批](../06-quality-operations/06-03-security-and-approval.md)

## 机器资料

- [Poster Graph](../../graph-specs/04-module-poster-interop/04-poster-graph.yaml)
- [A2A Agent Card 示例](../../contracts/04-interoperability/a2a-agent-card.example.json)
- [MCP Catalog 示例](../../contracts/04-interoperability/mcp-catalog.example.json)
- [OpenAPI 轮廓](../../contracts/04-interoperability/openapi-outline.yaml)

## 当前完成证据

- 未批准情报不能进入卡片生成；
- 生成操作幂等，同一情报只对应一张卡片；
- 日期使用项目时区筛选，凌晨边界不会错位；
- 完整“采集 → 审核 → 卡片 → 详情 → 原文”端到端流程通过；
- 1440×900 与 1024×768 桌面宽度通过浏览器冒烟测试。
