# Module 2 Workspace Agent 复杂任务修复与纵向优化提示词

你正在 AI Signal Studio 仓库根目录继续开发，下文记为 `<repo-root>`。本任务要在一个
连续开发增量内修复 Workspace Agent 无法处理自然语言复杂任务的问题，并把 Planner、
Context、执行、验收、分析结果和流式 UI 补成真实可用的纵向闭环。

不要只修复一个关键词判断后停止。先以用户实际失败的两句话建立简单 TDD，再连续完成
统一 Runtime、复杂计划、会话上下文、结果综合、UI 和最终全栈验收。普通测试全部使用
Fake、Fixture 或 Scripted Model；确定性回归全绿前禁止调用真实模型。

---

## 1. 本次必须修复的真实场景

以下两句话必须原样进入自动化测试，不能为了适配实现而改写测试提示词：

```text
你好，请你帮我收集最近24小时的热点AI内容，并选出其中影响力最大的三个，给我分析总结
```

```text
那么请你就目前收集的三天内的热点AI内容，并选出其中影响力最大的三个，给我分析总结
```

### 场景 A：采集后分析

预期目标契约：

```text
mode = collect_then_analyze
lookback_hours = 24
limit = 3
rank_by = impact
synthesize = true
use_existing = true
```

预期能力链：

```text
collection.run.start
→ intelligence.timeline.query（最近 24 小时）
→ research.recommend（最多 3 条、按可验证影响信号排序）
→ research.trend_brief（基于前三条的带引用综合分析）
```

采集新增为 0 只表示去重后没有新条目，不能提前结束任务；必须继续查询信息库中的现有
内容并完成后续步骤。

### 场景 B：只分析已有信息

预期目标契约：

```text
mode = analyze_existing
lookback_hours = 72
limit = 3
rank_by = impact
synthesize = true
use_existing = true
```

预期能力链：

```text
intelligence.timeline.query（最近 72 小时）
→ research.recommend（最多 3 条）
→ research.trend_brief（带引用综合分析）
```

此场景不得再次采集。它应使用当前会话的前序 Turn/Run 引用和工作区现有信息；即使没有
可复用 Run，也能按明确的 72 小时时间范围查询信息库。

### 用户可见结果

两个场景最终都必须显示：

- 实际执行计划、每步状态和服务端耗时；
- 最多 3 条真实 AI 信息，每条包含标题、来源、发布时间、颜色标识、入选理由和
  `/timeline?focus=<information_id>`；
- 一段跨条目的综合分析，包括共同变化、分别重要的原因、可能影响和证据局限；
- 综合分析中的每个事实或结论都关联真实 `information_id`；
- 采集新增为 0、候选不足或单来源失败时，仍交付可用结果并说明缺口；
- 不显示虚构评分数字，不返回任意模型 HTML 或原始 Tool JSON。

---

## 2. 已确认的根因，不要重复误判

开始时应只读复核，但当前已有以下证据：

1. `apps/web/src/features/agent/agent-screen.tsx` 的
   `isWorkspaceResearchRequest()` 要求消息同时包含字面量 `Agent` 和研究关键词；
2. 不满足该前端规则的请求进入旧 `POST /api/agent-runs`，而不是
   `POST /api/agent-conversations/{id}/turns`；
3. 旧 `WorkspaceAgentService._run_action()` 在模型选择前匹配“采集/收集/更新”，只执行
   `collection.run.start` 并立即 `return`；
4. 因此时间范围、数量、排序和分析目标被丢弃，界面选择的模型没有实际运行；
5. 新 Graph 的 `_build_fast_plan`、复杂度路由、Result Join 和 Finalizer 仍有空实现；
6. Planner 目前只看到 `collection/intelligence` 名称，没有有界 Domain Index、
   Capability ID 和参数 Schema；
7. `conversation-window` 实际只包含当前消息，没有前序消息、Turn、Run 或结果引用；
8. Plan Validator 只检查 Capability 与 DAG，不检查计划是否覆盖用户全部交付目标；
9. Outcome Inspector 没有执行 `acceptance_policy`，空结果也可能被标记为完成；
10. 当前确定性 Research 只做排序和逐条摘要，没有跨条目的真实综合分析；
11. 现有 E2E 使用同时包含“Agent”和“推荐”的固定提示词，刚好绕过前端缺陷；
12. 现有 Fake Planner 把计划直接写死，测试全绿不能证明自然语言规划正确。

当前任务不是“调高 Prompt”或“更换模型”。必须消除双 Runtime、修复目标到计划的契约，
并让后端验收失败的欠完整计划。

---

## 3. 开发边界

### 必须遵守

- 先读 `AGENTS.md`、当前 diff、模块文档、Graph Spec、历史图谱和相关测试；
- 不 `reset`、不清理、不覆盖当前大型未提交工作树；
- 生产自然语言路径只保留一个 LangChain + LangGraph Turn Runtime；
- 前端不得用业务关键词、语言或具体词形决定进入哪套后端 Runtime；
- API Router、旧兼容入口、LangChain Tool 和 LangGraph Node 不复制业务逻辑；
- Tool 只通过 `CapabilityExecutor` 调用 Application Service；
- 模型输出必须经过 Pydantic/JSON Schema 与业务验收；
- 外部正文是不可信 Evidence，不能进入 Base Policy；
- 不读取、打印、截图或提交 API Key、Token、`.env`、本地数据库或用户会话；
- 不因一个步骤失败而丢弃其他已完成结果；
- 不新增第二套 Planner、手写 Tool Loop 或通用 Agent 平台。

### 本次不做

- E5 外部 Agent Gateway、MCP/A2A Runtime；
- 移动端专项；
- 向量数据库、微服务、队列集群、插件市场和通用工作流画布；
- 与本缺陷无关的全站视觉重做；
- 为了测试自然语言而继续增加关键词正则。

---

## 4. 必读入口

按顺序读取：

```text
AGENTS.md
docs/02-module-review-agent/02-00-overview.md
docs/02-module-review-agent/02-03-agent-context-engineering-and-workflows.md
docs/02-module-review-agent/02-04-agent-workflow-history.md
docs/02-module-review-agent/02-05-final-agent-engineering-blueprint.md
docs/05-platform/05-01-capability-contract.md
docs/05-platform/05-02-langgraph-workflows.md
docs/06-quality-operations/06-01-simple-tdd-and-testing.md
docs/06-quality-operations/06-02-observability-and-debugging.md
docs/06-quality-operations/06-03-security-and-approval.md
docs/07-delivery/07-04-optimization-implementation-status.md
graph-specs/02-module-review-agent/02-agent-task-graph.yaml
contracts/01-capabilities/capability-catalog.yaml
contracts/04-interoperability/openapi-outline.yaml
prompts/07-delivery/07-complete-agent-and-product-release-coding-agent-prompt.md
```

主要代码入口：

```text
apps/web/src/features/agent/agent-screen.tsx
apps/web/src/features/agent/agent-event-stream.ts
apps/web/src/features/agent/agent-result-blocks.tsx
apps/web/src/lib/api.ts
apps/api/src/ai_signal_api/routers/agent.py
apps/api/src/ai_signal_api/agent_runtime/contracts.py
apps/api/src/ai_signal_api/agent_runtime/context.py
apps/api/src/ai_signal_api/agent_runtime/graph.py
apps/api/src/ai_signal_api/agent_runtime/harness.py
apps/api/src/ai_signal_api/agent_runtime/service.py
apps/api/src/ai_signal_api/agent_runtime/tools.py
apps/api/src/ai_signal_api/capabilities/registry.py
apps/api/src/ai_signal_api/modules/agent/conversation_service.py
apps/api/src/ai_signal_api/modules/intelligence/agent/
```

---

## 5. 版本化最小变更决策

本次不改变 N01～N25 主拓扑，但会改变 Runtime 路由、Conversation Context、Planner
输入、Tool 装配、目标覆盖校验、Outcome Inspector 和结果合并契约。为了不把行为变化
伪装成旧版本，目标版本统一升级为：

```text
workflow_version = 0.5.0
```

这是对既有蓝图的最小落实，不是新建第二套 Runtime。实施完成时必须在同一增量同步：

```text
graph-specs/02-module-review-agent/02-agent-task-graph.yaml
docs/02-module-review-agent/02-03-agent-context-engineering-and-workflows.md
docs/02-module-review-agent/02-04-agent-workflow-history.md
docs/02-module-review-agent/02-05-final-agent-engineering-blueprint.md
docs/07-delivery/07-04-optimization-implementation-status.md
Figma 当前 Agent 工作流图：
https://www.figma.com/board/dF7TcDtCd3J96E0Bb0F5Ad
对应 Contract、Graph、Eval 和 E2E 测试
```

历史 Markdown 只追加 `0.5.0` 完整 Mermaid 图，不覆盖 `0.4.0`。Figma、Graph Spec、
Execution Manifest、事件、状态文档和测试必须使用同一版本。

在现有 Figma 工作流图中原位更新当前版本，不新建无关联文件；保留历史版本区域，新增
或更新 0.5.0 的节点说明、边、Context/Tool/Acceptance/ResultBlock 注释，并截图检查
无裁切、重叠和断边。若 Figma 连接不可用，只能把“Figma 同步”列为外部阻塞，不能把
工作流变更标记完成。

同时处理版本迁移边界：

- 已完成的 `0.4.0` Turn 保持只读可查看；
- 未完成的 `0.4.0` checkpoint 不得被 `0.5.0` 静默恢复，应返回可定位的版本不兼容状态
  或通过显式、可测试的最小迁移恢复；
- Graph Spec 的 `version/workflow_version`、运行时默认、Execution Manifest、Turn 记录和
  测试断言必须一起升级，不能只改展示字符串；
- Plan、Context 或 ResultBlock 形状改变时，同步升级相应 Schema 版本与兼容读取测试；
- 回退方案是恢复 `0.4.0` Runtime 并继续只读显示 `0.5.0` Turn，不删除任何用户 Turn、
  ResultBlock 或 checkpoint。

---

## 6. 初始基线

只读检查：

```powershell
git status -sb
git diff --stat
git ls-files --others --exclude-standard
```

确定性基线：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/modules/agent_runtime tests/evals/agent tests/api/test_agent_turn_stream.py tests/api/test_agent_capability.py -q
.\scripts\pnpm.ps1 --dir apps/web test
```

记录“原测试通过但真实场景失败”的现状。初始阶段不要运行全量 Playwright、真实模型或
Git 写操作。

---

## 7. 第一批 TDD：先锁定真实失败行为

先写 2～6 个关键失败测试，不先改生产代码。

### 7.1 Runtime 路由测试

覆盖：

- 两条原始中文提示词均进入 `createAgentTurn`；
- 不包含 `Agent`、使用“选出”“归纳”“总结”等自然表达仍进入同一 Turn Runtime；
- 纯解释、任务配置、来源诊断、审核和带 Artifact 的请求也不回退到关键词 Runtime；
- 前端不再存在 `isWorkspaceResearchRequest` 一类业务 Runtime 选择器；
- 会话 ID、模型 ID、Artifact ID 和客户端幂等键完整传递。

### 7.2 Goal → Plan 契约测试

增加结构化 `AgentGoalSpec` 或等价内部契约，至少包含：

```text
operation_mode
time_window
max_items
ranking_criterion
deliverables
use_existing
requires_collection
requires_synthesis
```

两条原始提示词必须分别得到 24 小时/72 小时、3 条、影响力排序和综合分析目标。

使用 Scripted Planner 故意只返回一个 `collection.run.start` 步骤，断言 N08 拒绝该计划
并触发一次有反馈的 Replan；不得把欠完整计划标成有效。

### 7.3 Outcome 验收测试

覆盖：

- 请求 3 条但只返回 0 条时不得是无警告的 `complete`；
- `acceptance_policy.min_items`、真实 ID、应用内路径和 Evidence 引用实际执行；
- 采集新增 0 后仍继续查询；
- 单来源失败时独立查询、排序和综合继续；
- 依赖失败只跳过依赖步骤，不吞掉独立结果；
- 已成功副作用在 Replan、恢复和重试中不重复。

### 7.4 结果契约测试

最终结果必须：

- 至多 3 条真实信息；
- 每条有颜色、来源、理由和站内深链；
- 存在结构化 `trend_summary` 结果块；
- `trend_summary` 的要点分别带 `information_ids`；
- 不允许固定回复“采集完成”冒充综合分析；
- 结果块由后端白名单验证，前端有未知类型安全 fallback。

这些测试全部使用临时数据库、固定时间、Fixture 信息和 Scripted Model。

### 7.5 固定夹具与状态判定

冻结测试时钟，至少准备：

- 24 小时内 3 条，覆盖 `important/watch/normal` 三种颜色；
- 24～72 小时内 2 条；
- 72 小时外 1 条，用来证明时间边界确实生效；
- 每条都有真实 `information_id`、标题、摘要、来源、原地址、发布时间和站内深链；
- Fake Collector 分别支持新增、全部重复和单来源失败。

确定性影响排序使用工作区真实存在的代理信号：

```text
颜色优先级
→ 主题相关性
→ 发布时间倒序
→ 稳定 information_id
```

不要编造阅读量、点赞量或精确影响力分数。只有原目标的时间、数量、排序、分析和证据
全部满足时才是 `complete`；有可用结果但存在明确覆盖缺口时才是 `partial`；没有完成
任何主要目标时必须是 `failed`。禁止用 `min_items=0`、一条无关成功结果或“HTTP 200”
把空任务验收为成功。

---

## 8. 第二批实现：统一唯一生产 Runtime

### 8.1 前端

- 删除前端自然语言关键词分流；
- 所有用户消息默认调用
  `POST /api/agent-conversations/{conversation_id}/turns`；
- 快捷按钮使用结构化 `ClientCommand`，不能伪装成自然语言关键词；
- 图片和文档只传 Artifact ID；扩展 Turn Create Contract 支持 Artifact 引用；
- 会话选择的模型保存到会话设置并在刷新后恢复；
- UI 显示 `requested_model_id` 和 `effective_model_id` 的安全状态，不显示密钥。

### 8.2 后端

- `/api/agent-runs` 只保留兼容 Adapter，并委托同一个 Turn Application Service；
- `WorkspaceAgentService._run_action()` 退出生产自然语言主路径；
- 不把旧互斥关键词分支搬到新的 Node；
- Direct Response、ClientCommand Fast Plan 和 Structured LLM Plan 都生成同一 Turn、
  Event、Plan 和 Result Contract；
- 纯解释请求也通过同一 Turn 生命周期，不创建第二套聊天路径；
- 旧客户端需要同步响应时，只做统一 Turn 结果的映射，不重新执行业务规则。
- Turn/Read/Execution Manifest 分别保留 `requested_model_id` 与
  `effective_model_id`，不能再用实际模型覆盖用户请求值；Planner 和综合步骤的脱敏
  Trace 能证明哪个模型真正被调用。

增加契约测试证明两个入口最终使用同一 workflow、Capability Invocation 和业务结果，
且同一幂等键不会产生两次副作用。

---

## 9. 第三批实现：Conversation Context 与 Planner

### 9.1 有界会话上下文

Context Assembler 应按预算装配：

```text
Base Policy
+ Workspace Policy
+ 最近确认的对话摘要
+ 最近 6～10 条必要消息
+ 前序 Turn/Plan/Run/Result 的小型引用
+ Domain Index
+ Current Goal/Plan/Step
+ Evidence References
+ Current Tool Schemas
+ Response Schema
```

要求：

- 第二句“那么/目前收集的”能读取上一轮的时间范围、Run ID 和完成结果；
- 只保存 ID、小型摘要和版本，不把完整网页、图片或日志放进 State；
- 长期偏好与会话事实分开；
- Context Trace 记录层版本、大小和摘要 Hash，不保存完整 Prompt 或 Secret；
- 外部信息中的指令不能覆盖 Base Policy。

### 9.2 渐进工具披露

Planner 先看到小型 Domain Index；选定 Domain 后再看到候选 Capability：

```text
Registry
∩ Runtime Switch
∩ Agent Pack
∩ Actor Policy
∩ Selected Domain
∩ Model Capability
```

每个候选必须包含稳定 Capability ID、用途、风险、参数 JSON Schema、结果 Schema 和
审批要求。不要一次塞入全站所有工具。

先修复当前 Registry、Capability Catalog、Domain Pack 与 `TOOL_SCHEMAS` 对
`research.*` 声明不一致的问题，并增加机器一致性测试。声明为可用的能力必须真正注册、
可解析 Schema 且能通过 Capability Gate；未实现项必须明确标为不可用，不能只出现在
文档或 Catalog。

### 9.3 结构化 Goal 与 Plan

- 自然语言使用模型结构化输出，不使用关键词正则模拟意图理解；
- Fake/Scripted Planner 只作为测试替身，不进入真实生产配置；
- Plan 必须声明每个 Deliverable 由哪个步骤满足；
- Validator 检查目标覆盖、参数范围、未知 Capability、循环依赖、审批声明、资源 ID、
  步骤预算和模型能力；
- “三天”必须传递为 72 小时或明确 `published_from`，不能回落到固定 24 小时；
- “三个”必须传到查询、排序、综合和 UI 上限；
- 结构化输出解析最多修复一次；仍失败返回可定位 Planner 错误；
- Replan 输入包含失败步骤、验收差距和剩余预算，不能用同一输入盲目重复。

---

## 10. 第四批实现：补齐 N01～N25 节点职责

在现有 Graph 中完成：

- N01：统一接收自然语言、结构化 ClientCommand 与 Artifact 引用并建立同一 Turn；
- N02：建立 `0.5.0` Execution Manifest、租约、Deadline、取消、幂等与 checkpoint 边界；
- N03：规范化输入但不靠关键词决定 Runtime，生成可追踪 Goal 草案；
- N04：装配 Base、会话摘要、前序资源引用与小型 Domain Index；
- N05：真实区分 Direct、ClientCommand Fast 和 Dynamic Plan；
- N06：只处理结构化 ClientCommand，不解析自然语言关键词；
- N07：使用有界 Context、Domain Index 与 Schema 生成完整计划；
- N08：除 DAG 外验证 Goal Coverage 与预算；
- N09：缺少真正必要的信息时用 LangGraph `interrupt()` 暂停，并通过
  `Command(resume=...)` 在同一 Turn 恢复；
- N10：按依赖选择 Ready Steps；独立只读步骤可通过 `Send` 有界并行；
- N11：只装配当前步骤所需 Domain、Tool 和 Evidence；
- N12/N13：Schema 驱动 Action Binder/Validator，不为三个能力硬编码业务分支；
- N14：Capability Policy 与 Actor/开关/风险校验；
- N15：真实审批 `interrupt/resume`，一次性 Approval Token 绑定 `input_digest`；
  用户修改参数后旧 Token 自动失效；
- N16：只根据已验证步骤种类路由 Capability、Bounded Domain Agent 或 Domain Workflow；
- N17：原子 Capability；
- N18：真正使用本轮选定模型执行有界 Domain Agent，而不是只会发固定 Tool Call 的
  替身；
- N19：已知工作流或并行 Map；
- N20：保存小型事件、Artifact/Evidence 引用；
- N21：合并多个步骤结果、去重 Evidence；
- N22：执行 Acceptance Policy、Deliverable 和引用校验；
- N23：只在可修复且预算允许时重试/Replan，最多 2 次；
- N24：生成结构化结果块和面向用户的完成/部分完成/失败说明；
- N25：统一终态、耗时、未读、租约和审计。

停止、Deadline、取消和恢复要在节点边界和长 Tool 调用间持续传播。启动时使用
Recovery Scanner 查找未终结 Turn；只恢复版本兼容且租约可接管的执行。已成功副作用
通过 WAL/幂等记录复用，不因进程恢复、Replan 或 SSE 重连重复执行。

对两个目标场景，验收时至少观察到以下真实 Capability Invocation：

```text
场景 A
collection.run.start × 1
intelligence.timeline.query × 1
research.recommend × 1
research.trend_brief × 1

场景 B
collection.run.start × 0
intelligence.timeline.query × 1
research.recommend × 1
research.trend_brief × 1
```

如果复用已注册的组合工作流，仍必须保留等价的内部 Invocation/Span、参数、状态和
`information_id` 证据；不能只断言顶层组合工作流名称。

---

## 11. 第五批实现：可验证的影响排序与综合分析

### 11.1 影响排序

`research.recommend` 增加经过 Schema 验证的参数：

```text
candidate_ids
published_from / published_to 或等价精确 time_window
topic
limit
rank_by
conversation_id
run_id
```

现有 `ResearchInput` 只有粗粒度 `lookback_days`，必须正式扩展 Pydantic、LangChain Tool、
Capability Catalog、OpenAPI/JSON Schema 和测试；24 小时与 72 小时不能只存在于 Plan
说明文字。Action Binder 必须从已验证的 query 输出绑定 `candidate_ids`，Planner 不得
编造信息 ID。

`rank_by=impact` 只能使用工作区已有且可解释的信号，例如：

- 信息标识/优先级；
- 来源类型与权威性；
- 发布时间与时效；
- 多来源佐证；
- 与已有内容的重复/新颖程度；
- 与用户明确目标的相关性。

缺少某项信号时标明不确定，不得伪造阅读量、点赞量、市场份额或统计显著性。UI 只使用
颜色、入选理由和证据，不显示综合数字分数。

当前 `collection_then_analyze` 只是 Research Service 别名，并不会采集。0.5.0 不得把
它当成已完成的采集能力；优先使用显式四步链。若将它实现为 N19 组合工作流，内部仍须
逐步调用并记录采集、查询、推荐和综合四个 Invocation。

### 11.2 综合分析

增强既有 `research.trend_brief` Capability，使它成为受控的跨信息综合步骤，不再新增一套
语义重复的分析 Capability：

输入：

```text
selected information IDs
bounded evidence excerpts
user goal
time range
output max chars
```

输出使用结构化 Schema：

```text
overview
key_findings[]
why_it_matters[]
differences[]
uncertainties[]
information_ids[]
```

要求：

- 正常配置模型时由 N18 的真实 LangChain Bounded Domain Agent 使用本 Turn 的
  `effective_model_id` 生成结构化结果，不能继续返回当前固定趋势文案；
- 只基于已选信息和 Evidence；
- 每个 finding 带至少一个 `information_id`；
- 不把三条逐条摘要简单拼接成“综合分析”；
- 默认正文简洁，必要时可展开证据；
- Demo/heuristic 模式可以提供确定性、明确标注的规则摘要，但
  `effective_model_id/mode` 必须让 UI 和 Trace 看得出它不是模型生成；
- 用户选择真实 Provider 后调用失败时，不得回退模板伪装成功；保留前三条信息，把综合
  步骤和 Turn 标成可定位的局部失败。

增强既有 `trend_summary` 的后端 ResultBlock Schema、前端类型、渲染组件、契约样例和测试。

---

## 12. 第六批实现：真实流式结果与 Agent UI

- `result.block` SSE 事件携带已验证、已脱敏的完整 ResultBlock，而不只是 step/status；
- 前端收到块后增量渲染并去重，终态 GET 仍用于权威校准；
- 展示 Goal、Plan、步骤耗时、选定 Domain、Capability、来源覆盖和局部失败；
- `plan_summary`、`collection_summary`、`evidence_sources`、`trend_summary` 均有 UI；
- 未识别的合法未来块显示安全 fallback，不静默消失；
- 错误区分 input、business、provider、capability、system；
- 多请求中某项失败不吞掉已完成信息和综合结果；
- 模型下拉必须反映会话实际选择；旧动作不得显示“选择了模型”却完全绕过模型；
- 所有结果链接只允许后端生成的应用内白名单路径。

场景 A 的终态至少包含：

```text
plan_summary
collection_summary
recommendation_list
trend_summary
evidence_sources
navigation_action
```

场景 B 不得产生新的采集结果，但必须包含计划、推荐、综合、证据和导航块。每条推荐必须
带 `information_id/title/summary/source_id/source_name/source_url/published_at/color/`
`ranking_basis/app_path`。`result.block` SSE 事件携带可验证的
`block_id/type/title/data` 或已持久化块引用，不能只有笼统的 `status=completed`。

不要为了表现“流式”输出未经验证的模型 Token；本阶段优先流式结构化事件和结果块。

---

## 13. 第七批 TDD：回归、失败继续与评测

至少覆盖以下确定性场景：

1. 原始 24 小时采集后分析；
2. 原始三天已有信息分析；
3. 同义表达不含 `Agent` 或“推荐”；
4. “三天/近三日”“三个/3 条”得到相同规范化约束；
5. 指代式追问复用前序 Turn/Run；
6. 新会话不继承旧会话的时间范围、Run 或结果引用；
7. 采集新增 0 仍完成查询和分析；
8. 最近 72 小时外的第四条信息被排除；
9. 只有 2 条候选时返回 2 条并说明不足；
10. 0 条候选时按 Acceptance Policy 返回部分完成/覆盖缺口；
11. 一个来源失败，成功来源继续；
12. Planner 缺少综合步骤被拒绝并有界 Replan；
13. Outcome 缺少来源、深链或综合分析时不得是 `complete`；
14. `/agent-runs` 与 Turn API 使用同一 Runtime 和幂等副作用；
15. Prompt Injection 不能扩大工具集合；
16. 禁用 `research.trend_brief` 后 Tool 不可见且伪造调用仍拒绝；
17. 取消、刷新、SSE 续传和进程恢复不重复副作用；
18. 带 Artifact 的复杂请求仍进入统一 Turn；
19. 普通问候和解释请求通过 Direct Turn，避免所有请求都过度规划；
20. 模型选择刷新后恢复并记录非空 `effective_model_id`；
21. 每个分析 finding 都引用实际返回的信息 ID；
22. Provider 不可用时返回明确 Provider 错误，不把模板文本伪装为模型成功。

推荐新增或扩展：

```text
tests/modules/agent_runtime/test_goal_plan_coverage.py
tests/modules/agent_runtime/test_conversation_context.py
tests/modules/agent_runtime/test_outcome_inspector.py
tests/api/test_agent_complex_turns.py
tests/evals/agent/test_complex_research_scenarios.py
apps/web/e2e/workspace-agent.spec.ts
```

不得：

- 直接让 Fake 返回正确最终答案后只断言状态；
- 用固定 24h/5 条计划代表自然语言解析；
- 允许 `failed` 也算 Live 验收通过；
- 用 Demo 恰好只有 3 条数据掩盖 `limit` 没有传递；
- 只断言卡片数量，不断言 Plan、时间、数量、排序、综合和引用。
- 为两条原始提示词增加专用 `if/else`、正则、固定计划或固定分析文本；
- 让 Fake 直接写数据库、Graph State 或 ResultBlock，绕过生产 LangChain structured
  output、LangGraph、Plan Validator、Action Binder、Tool Resolver、Capability Gate、
  Application Service、Repository 或 Result Composer；
- 将 N05、N06、N21 或 N22 从空实现改成固定返回值后宣称完成；
- 通过删除、放宽、`skip`、`xfail`、`continue-on-error` 或吞异常让测试变绿；
- 在 `effective_model_id` 为空、模型未被调用或 Provider 已失败时宣称完成模型分析；
- 把标题复述、三段原摘要拼接或来源计数命名为“综合分析”；
- 用文档、Schema、Graph 节点名称或 UI 占位状态代替运行时证据。

Fake/Scripted Model 只能替换 Provider 边界。测试仍需执行真实的 Context 装配、LangChain
结构化输出接口、LangGraph、Validator、Binder、Tool、Capability、Repository、结果
合并和终态验收。Fake 不能根据完整原句选择答案，至少要用同一结构覆盖同义改写和空格
变化。

---

## 14. 阶段验证节奏

每批只运行对应目标测试。出现失败时先修目标测试，不在每次小修改后跑全量。

示例：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/modules/agent_runtime/test_goal_plan_coverage.py -q
.\.venv\Scripts\python.exe -m pytest tests/api/test_agent_complex_turns.py -q
.\.venv\Scripts\python.exe -m pytest tests/evals/agent/test_complex_research_scenarios.py -q
.\scripts\pnpm.ps1 --dir apps/web test
```

阶段通过后直接继续，不停下来等待确认。只有以下事项可成为真正阻塞：

- 需要改变本提示词已经批准的范围之外的公共架构；
- 需要新的外部服务、付费依赖或用户凭据；
- GitHub 认证/权限；
- LICENSE 等法律选择。

---

## 15. 最终确定性全栈验收

全部代码、UI、契约、文档和图谱同步完成后，只执行一次最终全栈级验收：

```powershell
.\scripts\verify.ps1 -E2E
.\.venv\Scripts\python.exe scripts/validate_contracts.py
.\.venv\Scripts\python.exe scripts/validate_versions.py
git diff --check
.\.venv\Scripts\python.exe scripts/check_release_safety.py --worktree
.\.venv\Scripts\python.exe scripts/check_release_safety.py --tracked
.\.venv\Scripts\python.exe scripts/check_release_safety.py --history
```

Playwright 必须使用原始两句话完成：

```text
新建会话
→ 发送场景 A
→ 查看 24h / 3 条 / 分析结果
→ 同一会话发送场景 B
→ 查看 72h / 3 条 / 分析结果
→ 打开任一信息深链
→ 返回会话并确认历史、计划和结果仍在
```

不得把改写后的“收集并推荐 Agent 内容”作为唯一验收。

最终全量失败时：

1. 运行失败模块的最小目标测试；
2. 修复后重新运行完整 `verify.ps1 -E2E`；
3. 直到取得一次最终全绿证据；
4. 不用局部测试替代最终结果。

---

## 16. 可选的单次真实模型完整链路

只有确定性全栈全绿，并且环境已经显式设置：

```text
AI_SIGNAL_RUN_LIVE_MODEL_TESTS=1
```

才允许使用用户配置的真实模型运行场景 A 一次。

要求：

- 通过公开 Turn API 和真实 UI 链路；
- 最多 2 次模型请求：一次结构化 Plan、一次综合分析；
- 不读取、输出或截图 API Key；
- 使用临时测试数据，不修改用户正式来源、任务或记忆；
- 必须断言 `effective_model_id` 为所选模型；
- 必须断言 24 小时、采集后继续查询、3 条、影响力排序、综合分析和真实引用；
- `failed` 不能作为通过；
- 429、超时或额度不足如实记录为 Provider 阻塞，不循环重试。

环境开关未设置时记录真实模型调用 0 次并跳过；不得自行打开。

---

## 17. Git 与发布安全

只有最终确定性全栈、版本同步和 Release Safety 全部通过后，才进入 Git 阶段。遵循
`prompts/07-delivery/07-complete-agent-and-product-release-coding-agent-prompt.md`
中的完整发布规则。

建议分支：

```text
codex/agent-complex-task-repair
```

硬要求：

- 先验证 `origin` 仍为用户给定仓库和 `gh auth status` 有效；
- 不直接提交到 `main`，不 force push；
- 不使用 `git add -A`、`git add .` 或 `git add -u`；
- 只显式暂存经过审阅的代码、测试、契约、Graph、文档和通用资产；
- 不暂存 `.env`、`*.local.json`、数据库、日志、Artifact、截图、浏览器状态、
  用户 Agent Pack、会话、来源、任务或 API Key；
- staged Guard 与 Secret 扫描通过后才提交；
- 推送新分支并创建 Draft PR，不合并、不打 Tag。

如果 GitHub 认证仍无效，只允许在 Git 发布步骤停下；不得回滚已经完成的实现和测试。

---

## 18. 完成定义

只有同时满足以下条件，本任务才算完成：

- 两条原始失败提示词都通过前端进入同一个 LangGraph Turn Runtime；
- 旧关键词 Runtime 不再是任何自然语言生产主路径；
- 场景 A 真实执行采集、24 小时查询、3 条排序和综合分析；
- 场景 B 不重复采集，真实执行 72 小时查询、3 条排序和综合分析；
- 采集新增 0 不会截断后续步骤；
- Planner 获得有界 Domain/Capability Schema 和会话上下文；
- Plan Validator 能拒绝未覆盖全部 Deliverable 的欠完整计划；
- Outcome Inspector 实际执行数量、引用和 Acceptance Policy；
- 综合分析不是固定文本或摘要拼接，每项结论有真实引用；
- SSE 增量交付真实 ResultBlock，UI 能渲染并在刷新后恢复；
- 模型选择实际生效且可追踪；
- 复杂任务的部分失败、取消、恢复和幂等通过测试；
- `workflow_version=0.5.0` 在代码、Graph Spec、历史 Markdown、Figma、状态和测试一致；
- 最终确定性全栈验收通过；
- 真实模型仅按授权执行 0 或 1 个完整场景；
- 没有 Secret 或个性化数据进入 Git 候选；
- 已推送 Draft PR，或唯一剩余阻塞是明确的 GitHub 认证/权限。

任何以下结果都不能宣称完成：

- 只删除 `isWorkspaceResearchRequest`；
- 只让测试 Fixture 返回正确计划；
- 只增加 Capability/Schema 但 UI 不可用；
- 只显示三张卡但没有 24h/72h 参数和综合分析；
- 空结果仍无警告标记为 `complete`；
- 文档继续写“全部完成”但原始提示词无法通过；
- Graph Spec、历史、Figma 和实现版本不一致。

---

## 19. 最终交付格式

最终答复必须给出：

1. 根因如何被消除；
2. 两条原始提示词各自的实际 Goal、Plan 和 Capability 顺序；
3. 三条信息与综合分析结果块的引用证据；
4. Conversation Context、Planner、Validator、Inspector、SSE 和 UI 的变化；
5. 目标测试、全量测试、构建、契约和 Playwright 的真实结果；
6. 真实模型调用次数、所选模型和结果；
7. `workflow_version` 与 Graph/Figma/历史同步证据；
8. Release Safety 结果；
9. 分支、Commit、Push 和 Draft PR URL；
10. 唯一仍需用户处理的事项。

对两个原始场景分别附上脱敏后的运行证据：

```text
turn_id
conversation_id
effective_model_id
workflow_version
planning_mode
selected_domains
plan steps
每步 capability_id 与规范化参数
step status 与服务端耗时
result block types
information_id 列表
最终 acceptance 逐项结果
```

还要给出场景 A 在 `items_added=0` 后继续查询的事件序列、场景 B 的
`collection.run.start × 0` 调用序列、72 小时时间边界、同会话继承与新会话隔离证据。
测试报告必须分别列出 `passed/failed/skipped/xfail`，不能只报通过数量；新增
`skip/xfail` 时必须解释并且不能用于绕过本任务门禁。

不要只报告“测试通过”或“Agent 已优化”；必须证明用户原始两句话已经形成可理解、
可恢复、可引用的复杂任务成品。
