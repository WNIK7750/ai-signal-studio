# 00-01 项目章程

## 1. 项目名称

AI Signal Studio，中文可称“AI 情报与卡片工作台”。

## 2. 产品目标

构建一个个人可维护的全栈应用：

- 定时或由用户发起收集最新、优秀、重要的 AI 信息；
- 将多来源内容标准化、去重、摘要、分类、评分并按日期形成时间线；
- 用户批量保留、拒绝、延后或编辑信息；
- 用户确认后批量生成可编辑海报卡片；
- 内置 Agent 能使用所有已启用的应用能力；
- 外部 Agent 与代码 Agent 能通过稳定接口使用、审阅、调试和修改系统；
- 用户可通过文档导入与直接编辑客制化 Agent 的知识、偏好与长期记忆；
- 支持图片导入与实时语音输入转文字。

## 3. 成功标准

第一版成功不是“框架完备”，而是以下闭环真实可用：

```text
采集 → 时间线 → Agent/用户审核 → 确认 → 卡片草稿 → 编辑 → 渲染
```

同时满足：

- Agent 与用户调用相同业务能力；
- 模块可单独替换；
- 编程 Agent 能通过文档、Schema、测试和日志快速定位修改点；
- 单人能在 Windows 本地运行和调试。

## 4. 非目标

首轮不建设：

- 通用多租户 SaaS 平台；
- 微服务集群；
- 插件市场；
- 拖拽式 Graph 编辑器；
- 完整企业级权限中心；
- 自动无人审批发布；
- 语音对话或语音合成；
- 视频处理；
- 通用多 Agent 社会模拟。

## 5. 架构原则

### 5.1 成品优先

先按宏模块交付可操作闭环，再从真实问题中提炼通用抽象。

### 5.2 能力内核

业务能力与 Agent 分离。Agent 是能力调用者，不是业务逻辑容器。

### 5.3 低耦合但不提前分布式

通过 Python Protocol、Pydantic Schema、Repository 与 Adapter 降低代码耦合；部署先保持模块化单体。

### 5.4 文档可修改

Agent Pack 使用 Markdown、YAML、JSONL 和 JSON Schema。用户与编程 Agent都能直接检查、导入、编辑和版本控制。

### 5.5 人机协作

LLM 可以推荐与生成，但删除、发布、批量渲染、长期记忆覆盖等动作由策略决定是否需要用户确认。

### 5.6 可回放与可观测

长流程保留 LangGraph thread/checkpoint；所有能力调用保留结构化记录；副作用幂等。

## 6. 技术基线

- Backend：Python 3.12、FastAPI、Pydantic、SQLAlchemy、Alembic。
- Agent：LangChain。
- Workflow：LangGraph。
- Frontend：Next.js、TypeScript、TanStack Query、shadcn/ui。
- Storage：SQLite + 本地文件存储，预留对象存储 Adapter。
- Schedule：APScheduler 或等价轻量调度器。
- Poster：HTML/CSS 模板 + Playwright 渲染。
- Speech-to-text：浏览器实时麦克风 + WebSocket + `vendor_tools/speech_to_text` 中的第三方转写实现。

## 7. 决策优先级

当设计发生冲突时按以下顺序取舍：

1. 可完成、可运行；
2. 用户闭环；
3. 可测试；
4. Agent 与用户统一能力；
5. 模块可替换；
6. 性能优化；
7. 平台化扩展。
