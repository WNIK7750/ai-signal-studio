# AI Signal Studio 文档导航

文档使用两级编号组织：目录号表示阅读阶段或交付模块，文件号表示该目录内的阅读顺序。实现功能时先读对应模块的 `XX-00-overview.md`，再按其中的链接读取共享规范和机器契约。

## 推荐阅读路线

### 00 项目全局

1. [00-01 项目章程](00-project/00-01-project-charter.md)
2. [00-02 产品范围与用户流程](00-project/00-02-product-and-user-flows.md)
3. [00-03 系统架构](00-project/00-03-system-architecture.md)
4. [00-04 模块边界](00-project/00-04-module-boundaries.md)
5. [00-05 推荐仓库布局](00-project/00-05-repository-layout.md)

### 01～04 交付模块

1. [01 AI 情报时间线](01-module-timeline/01-00-overview.md)
2. [02 审核工作台与 Workspace Agent](02-module-review-agent/02-00-overview.md)：对话、
   Base + Domain 上下文工程、轻量 Harness、LangChain/LangGraph 工作流与历史图谱。
3. [03 Agent Pack、Artifact 与实时转写](03-module-agent-assets-stt/03-00-overview.md)
4. [04 信息卡片与后续外部接口](04-module-poster-interop/04-00-overview.md)：卡片成品、
   REST/OpenAPI 与延后实施的[外部 Agent Gateway 设计](04-module-poster-interop/04-02-external-agent-gateway-design.md)。

### 05～07 共享规范与交付

- [05 共享平台](05-platform/05-01-capability-contract.md)：Capability、LangGraph、前端架构、UI 布局、设计令牌、主题、图标与[模型路由](05-platform/05-07-model-configuration-and-routing.md)。
- [06 质量与运维](06-quality-operations/06-01-simple-tdd-and-testing.md)：测试、可观测性、安全与审批。
- [07 交付管理](07-delivery/07-01-development-roadmap.md)：路线图、实践来源与
  [产品、业务及体验全面优化蓝图](07-delivery/07-03-product-and-experience-optimization-blueprint.md)，
  以及[当前实现、验收状态与新增任务](07-delivery/07-04-optimization-implementation-status.md)。

### 90～99 决策与参考

- [90 架构决策记录](90-architecture-decisions/90-01-modular-monolith.md)
- [99 原始交付包参考](99-reference/README.md)

## 编号规则

- `00`：项目级事实与边界。
- `01`～`04`：按实施顺序排列的产品模块。
- `05`：多个模块共同依赖的平台规范。
- `06`：横切的质量、调试和安全要求。
- `07`：路线图与外部实践。
- `90`：已接受的架构决策。
- `99`：只读历史与来源参考。

新增文档时优先归入现有模块，并使用 `目录号-两位文件号-主题.md`；只有形成新的独立交付模块时才增加一级编号目录。
