# LangGraph 规格

规格文件按所属交付模块存放：

- `01-module-timeline/01-collection-graph.yaml`
- `02-module-review-agent/02-review-graph.yaml`
- `02-module-review-agent/02-agent-task-graph.yaml`（`0.4.0` Context + Harness 目标规格，使用 LangChain + LangGraph）
- `04-module-poster-interop/04-poster-graph.yaml`

普通 CRUD 不需要 Graph。节点产生外部副作用时必须支持幂等，interrupt 的恢复输入必须通过类型校验。
