# 07-04 全面优化实现状态

本文记录 `07-03` 蓝图已经落地的事实、验证证据和仍需继续完成的边界。
它不是新的平行路线图；后续开发仍以 `07-03` 的阶段顺序为准。

## 1. 本轮已形成的产品闭环

### 1.1 版本化任务

- 新增统一的采集任务与不可变配置版本；
- 任务配置覆盖来源、匹配、时间窗、最少/目标/最大数量、重要性、质量、
  去重、调度和交付；
- 试运行执行真实读取与筛选，但不写入信息库；
- 正式运行使用同一套筛选漏斗，并记录任务版本、来源版本和漏斗数量；
- 运行分别记录执行状态与覆盖状态，不再用“成功”掩盖数量不足；
- 支持按原版本或当前版本重试；
- 调度器按任务版本调用 `task.run.start`，并传入幂等键。

### 1.2 统一 AI 信息库

- 时间线条目增加已读、收藏、归档和笔记状态；
- 搜索、来源、主题、任务、日期和状态筛选统一进入 Timeline Query；
- 保存视图保存查询与展示配置，不复制信息条目；
- AI 信息页提供全部、今天、未读、收藏快捷视图；
- 单条信息可以直接标记已读、收藏、归档或打开原文。

### 1.3 Agent 协作

- 对话继续保存在本地 SQLite，刷新后可恢复；
- 支持多会话的新建、搜索、重命名、置顶、归档、软删除、恢复和刷新后续接；
- 每个会话独立保存未发送草稿与滚动位置；
- “每天/定时/创建任务”意图生成结构化任务草稿；
- 草稿包含主题、数量上下限、时间和摘要字数，并随助手消息持久化；
- 用户可以确认创建并启用，也可以进入任务工作台继续编辑；
- “立即采集”仍兼容原快捷能力，不需要先建任务。

### 1.4 桌面页面框架

- 左侧导航可收缩为图标栏，服务设置与主要工作流分组；
- 新增任务工作台：左侧任务、中心配置、右侧即时摘要与试运行漏斗；
- 窄桌面比例下右侧摘要移到主区下方，1024 像素宽度不产生横向滚动；
- 右侧筛选保持可完全收起；
- 来源页显示连接健康、最近成功、条目数，并可真实测试；
- 运行页分别显示执行与覆盖结果；
- 功能图标继续使用 Tabler Outline，视觉值继续由设计令牌控制。

### 1.5 Workspace Agent 0.4.0 首个纵向切片

- 已锁定并由 `requirements.lock` 安装 `langchain`、`langchain-openai`、
  `langgraph` 和 `langgraph-checkpoint-sqlite`；
- 已实现版本化 Base Prompt、`collection/intelligence` Domain Pack、
  Context Snapshot 和按步骤动态 Structured Tool；
- 自然语言“收集最近 24 小时并推荐 Agent 内容”由 Structured Planner 输出统一
  `AgentPlan`，真实 StateGraph 执行“采集 → 查询/筛选 → 推荐 → 合并”；
- Domain Agent 使用 LangChain `create_agent`，Tool 只能调用
  `CapabilityExecutor`；新增 `intelligence.recommend` 确定性排序能力，模型不能编造
  信息 ID、来源或站内链接；
- 新增持久 `AgentTurn/Step/Event/ResultBlock`，SSE 事件先写库再发送，序号单调并支持
  `Last-Event-ID`，`conversation_id + client_message_id` 保证 Turn 与采集不重复；
- LangGraph 使用独立 SQLite Checkpointer，`thread_id=turn_id`；写动作幂等键包含
  `turn_id + step_id + capability_id + input_digest`；
- 单来源失败时保留成功来源和已保存信息，终态为 `partial`，并生成可重试错误和真实
  `signal_preview`；
- Agent 页面已接入乐观消息、SSE、可折叠计划、步骤/耗时、停止、部分失败、重试、
  3～5 条信息卡、查看全部、运行详情与 `/timeline?focus=...` 深链；
- `workflow_version` 与 `0.4.0` 拓扑未改变，因此本增量不重复生成 Figma 或历史版本图。

## 2. 数据与能力边界

| 领域 | 事实来源 | 主要入口 |
| --- | --- | --- |
| 任务 | `CollectionTask` + `CollectionTaskVersion` | `/api/tasks` |
| 任务执行 | `CollectionRun` + `SourceRunResult` | `task.run.start` |
| 信息条目 | `IntelligenceItem` | `/api/timeline` |
| 本地状态 | `WorkspaceItemState` | `/api/information/{id}/state` |
| 保存视图 | `SavedView` | `/api/saved-views` |
| Agent 对话 | `AgentConversation` + `AgentMessage` | `/api/agent-conversations`、`/api/agent-runs` |

Router、Agent 和调度器只做输入适配；任务筛选、版本选择、执行和重试都落在
Application Service/Capability。

## 3. 本轮关键验收

- 后端：任务创建、预览不写入、同漏斗执行、覆盖不足、原版本重试；
- 信息库：状态持久化、状态筛选、保存视图创建与更新；
- Agent：对话恢复、同消息幂等、结构化草稿刷新后仍存在；
- 来源：测试来源不会产生采集运行；
- 前端：Vitest、ESLint、Next.js 生产构建；
- Playwright：外观、模型、采集审核卡片、任务工作台、Agent 多会话与采集共七条桌面流程；
- 动态布局：1440×900 与 1024×768 桌面窗口。

## 4. 仍未完成的原蓝图增量

1. 运行详情抽屉：逐来源耗时、重试次数、错误建议和差异比较；
2. 任务版本历史与恢复 UI；
3. 保存视图的重命名、排序、默认视图和 URL 双向同步；
4. 来源分组、批量测试、限速与凭据状态；
5. 待处理迁移为跨任务动作队列；
6. 专题板、周报和可导出交付物；
7. Review Graph interrupt/resume 与审批 Token；
8. 最终桌面验收完成后再做移动端专项设计。

这些增量应继续按一个完整用户场景配 2～6 个关键测试推进，不提前扩展为
通用工作流平台或插件市场。

## 5. 2026-08-05 实施前审计基线

以下是新增批次拆分时的代码核查事实，用于说明任务来源，不再代表 E0、E1
完成后的当前状态：

- Agent 只有 `current` 会话读取和同步 `POST /api/agent-runs`，没有会话列表、
  新建、重命名、置顶、归档、软删除或恢复；
- Agent 等待期间只显示“正在执行”，没有 Turn、事件序号、流式端点、首输出时间和
  总耗时；
- Agent Runtime 仍以互斥分支 `return` 处理意图，一次输入中的后续独立请求可能不执行；
- 采集答复没有稳定的信息引用和来源结果组件，前端不能跳转到具体 AI 信息；
- Timeline 默认只取 50 条，前端没有加载更多；日期分组使用显示文本，且没有折叠；
- 来源编辑 UI 能切换类型，但 Patch Schema 不接受 `kind`，服务也没有对合并后的
  `kind + config` 重新校验；Patch 重名还缺少稳定 409；
- 外观页先以 Signal Light 初始化并持久化，再异步读取本地值，进入页面可能覆盖主题；
- A2A 当前只有文档和示例 Card，没有实际 Router、Task、SSE 或外部 Actor Policy；
  示例不能继续把尚未实现的 Streaming 当成已完成能力。

## 6. 新增任务顺序

任务按垂直闭环交付，不把后端、前端和测试拆成互相等待的长期分支。

| Epic | 目标 | 依赖 | 状态 |
|---|---|---|---|
| `E0` | 外观恢复与来源数据正确性热修 | 无 | 已完成（2026-08-05） |
| `E1` | Agent 多会话完整闭环 | 无；建议先于流式 Turn | 已完成（2026-08-05） |
| `E2` | 可恢复 Agent Turn、耗时、结构化结果与部分成功 | `E1` | 首个采集后推荐切片完成；通用后台会话与恢复扫描待扩展 |
| `E3` | 长时间线分段加载、日期折叠与深链 | 可与 `E2` 后半并行 | 未开始 |
| `E4` | 来源 Modal、草稿测试和稳定错误 | `E0` 的来源契约 | 未开始 |
| `E5` | 外部 Agent Gateway（MCP 优先、A2A 后续） | 核心产品完成、Capability Actor Policy、明确互操作客户端 | 设计完成，Deferred；不进入当前开发任务 |
| `E6` | 用户配置真实模型的完整链路验收 | 核心产品完成、确定性全量回归通过 | 未开始；禁止模块级 Smoke |
| `E7` | LangChain/LangGraph Context Kernel 与模块 Domain Pack | 可与 `E2` 数据骨架并行，运行接线依赖 `E2` | `collection/intelligence` 首批运行切片完成 |
| `E8` | Product Turn Harness 与 Plan/Execute/Replan StateGraph | `E2`、`E7` | 0.4.0 首个纵向路径完成；interrupt/replan 通用化待扩展 |
| `E9` | AI 信息检索、筛选、推荐、比较、趋势与采集后分析 | `E8`；可与 `E3` UI 并行 | 采集后查询与推荐完成；比较/趋势/覆盖缺口待扩展 |
| `E10` | 站内读能力与受控写能力的 Agent 全覆盖 | `E8`；来源部分与 `E4` 合并 | 未开始 |
| `E11` | Agent Evaluation Harness、协议复用与工作流图谱同步门 | `E11-A` 在 E8/E9 首个纵向闭环后开始；`E11-B` 依赖 E9/E10 首批能力 | 蓝图与图谱基线完成，评测未开始 |

推荐批次：

```text
批次 1：E0 + E1（已完成）
批次 2：E7-T0 最终蓝图与公共契约边界（蓝图已完成）
批次 3：E2 + E7-T1～T5（Turn 与 Context 基座）
批次 4：E8 + E3 + E4
批次 5：E9 只读纵向闭环（仅 Fake/Fixture）
批次 6：E11-A + E10（基于首个成品建立评测集并扩展受控写）
批次 7：剩余核心能力 + E11-B 确定性发布回归
最终验收：E6 单个完整真实模型链路
```

E5 不属于上述当前批次。用户确认进入最终互操作阶段后，才按
[04-02 外部 Agent Gateway 设计](../04-module-poster-interop/04-02-external-agent-gateway-design.md)
建立新的垂直切片；不得先把当前关键词 Agent 包装为 A2A，也不得创建第二套 Runtime。

### E0：已知回归护栏

#### E0-T1 外观恢复门

- 将主题、圆角、密度、字号的读取、应用和持久化收口到共享
  `AppearanceProvider`；
- 恢复完成前禁止写入默认 `signal-light`；
- 外观页从 Provider 读取当前值，只有用户操作才保存；
- 非法值允许回退，但回退和写回只发生一次。

验收：

- 预置任一非默认主题，进入外观页后 DOM 与本地存储都不变化；
- 用户选择新主题后才改变，刷新其他页面仍保持；
- 开发 Strict Mode 下不出现双重写入或闪烁。

#### E0-T2 来源 Patch 正确性

- 编辑时来源类型先设为只读；换类型使用“复制为新来源”；
- 创建和 Patch 都在 Application Service 对最终完整定义执行同一校验；
- Patch 重名返回 `SOURCE_NAME_EXISTS`/409；
- 空 URL、空仓库或不匹配配置返回 422，数据库保留旧值；
- API 输入类型不再使用包含只读字段的 `Partial<Source>`。

### E1：Agent 多会话完整闭环

#### E1-T1 数据与迁移

`AgentConversation` 增加：

```text
title_source
pinned_at
archived_at
deleted_at
active_turn_id
last_message_at
unread
```

现有工作区增量迁移不得丢失消息。删除默认软删除。

#### E1-T2 Application 与 REST

```text
GET    /api/agent-conversations
POST   /api/agent-conversations
GET    /api/agent-conversations/{id}
PATCH  /api/agent-conversations/{id}
POST   /api/agent-conversations/{id}/archive
POST   /api/agent-conversations/{id}/restore
DELETE /api/agent-conversations/{id}
```

- 排序：置顶优先，其余按最近消息时间；
- `/current` 仅作为迁移兼容，不再是核心入口；
- 自动标题不能覆盖手动标题；
- 元数据服务不直接执行 Capability。

#### E1-T3 页面

- 会话栏包含新建、搜索、置顶、今天、最近和更早；
- 行级菜单包含重命名、置顶、归档和删除；
- 删除后可撤销，永久清理由系统数据页负责；
- 每个会话保存独立草稿和滚动位置；
- `>=1360px` 可常驻，较窄窗口使用左侧抽屉；
- 不增加文件夹、分享、团队权限和云同步。

最小测试：

1. 两个会话消息严格隔离；
2. 置顶排序稳定；
3. 归档/软删除不出现在活动列表，恢复后消息仍在；
4. 相同 `conversation_id + client_message_id` 不重复执行；
5. Playwright 完成 A/B 会话切换、重命名、置顶、归档、删除/撤销和刷新恢复。

### E2：Agent 可观察执行与业务结果

#### E2-T0 公共契约冻结

E2、E7、E8 与 E11 开发前先共享以下契约，不在各分支重复定义：

```text
AgentTurnState
AgentTurnEvent
AgentTurnResult
AgentPlan / PlanStep
ActionEnvelope
ArtifactRef / EvidenceRef
ErrorEnvelope
DeadlineBudget
ExecutionManifest
```

- `LangGraph thread_id = turn_id`；
- 采集、任务和卡片等业务 Run 只保存为引用；
- Checkpoint、Event Journal 与 Conversation Message 是不同逻辑对象；
- 公共 Schema 先有 JSON Schema 示例和契约测试，再允许并行实现。

#### E2-T1 Turn 和事件

- 新增 `AgentTurn`、`AgentTurnStep`、`AgentTurnEvent` 和
  `AgentResultBlock`；
- `POST /conversations/{id}/turns` 返回 202 和 Turn ID；
- `GET /turns/{id}/events` 使用 SSE，支持 Event ID 和断线续传；
- 最终消息/结果以数据库为事实来源，SSE 只是增量投影；
- 先完成生命周期和 Capability 状态流；模型 Provider 真支持后再输出文本 delta，
  禁止用动画伪造。

#### E2-T2 执行与耗时 UI

- 发送后立即显示用户消息和“已接收”；
- 执行中显示阶段和递增秒数；
- 完成后显示服务端总耗时，展开可看各步骤耗时；
- 支持停止；追加要求在安全边界生效；
- 后台会话继续运行并在会话栏显示运行中/未读。

#### E2-T3 信息结果块

收集结果必须含：

- 新增、去重、过滤、最终保存数量；
- 来源成功/失败和逐来源数量；
- 最多 3～5 条重点信息：颜色、来源、标题、一行摘要；
- 后端生成的应用路径；
- “查看全部、只看重点、运行详情、重试来源”。

深链：

```text
/timeline?focus=<item_id>&run=<run_id>&from=agent&conversation=<conversation_id>
```

#### E2-T4 多请求与错误分类

- 一轮最多 5 个 `TurnStep`；
- 独立步骤默认继续，依赖步骤在前置失败时跳过；
- 最终答复分为“已完成、需要你处理、未完成”；
- 错误来源为 `input/business/provider/capability/system`；
- 局部错误不能吞掉已经完成的消息、信息或 Run；
- 不显示隐藏思维链、任意工具 JSON、密钥和堆栈。

最小测试：

1. SSE 顺序、断线续传与最终持久化；
2. 时长字段单调；
3. 幂等消息不重复副作用；
4. 一个步骤失败时另一独立步骤继续；
5. 采集块含来源和可用信息引用；
6. Playwright 验证运行秒数、部分完成、重点信息和深链。

### E3：长时间线

- 后端用 `(published_at, id)` 稳定游标替代长期 offset，默认每页 50；
- 返回 `next_cursor` 和 `has_more`；
- 分组 key 使用本地 ISO 日期，不能用“8 月 3 日”显示文本；
- 今天和最近有内容日期默认展开，较早日期按用户保存状态折叠；
- 日期标题显示总数、未读数和重要数；
- IntersectionObserver 与可访问“加载更多”按钮并存；
- 新内容只显示提示，不抢滚动位置；
- 深链可跨页定位、展开日期、滚动、高亮和打开 Peek；
- 首版不全量虚拟化；展开 DOM 经实测超过阈值后再对日期组窗口化。

最小测试：

1. 同时间戳游标稳定，两页无重复；
2. 新数据插入不导致漏项；
3. 折叠不改变已读/收藏状态；
4. 跨年份相同月日不合并；
5. Playwright 加载三页、恢复折叠和滚动，并从 Agent 定位目标。

### E4：来源 Modal 与后端修复

- 复用模型页 Modal 的视觉和交互，补齐 `role=dialog`、焦点管理、Esc 和未保存保护；
- 表单字段：类型、名称、地址、单次上限、启用状态；
- 页脚：取消、测试连接、保存；
- 新增无副作用草稿测试入口，测试后显示数量和最多 3 个样例标题；
- 草稿测试不创建来源、Run 或正式信息；
- 稳定错误码覆盖 URL、仓库、超时、DNS、401、429、解析、空 Feed 和重名；
- 每行拥有独立 testing/saving 状态。

最小测试：

1. 草稿测试零持久副作用；
2. Patch 空配置 422、重名 409；
3. 外部异常映射稳定且日志保留 request ID；
4. Playwright 验证预填、测试样例、错误不丢输入、Esc 和焦点回收。

### E5：外部 Agent Gateway（Deferred）

设计已经完成，见
[04-02 外部 Agent Gateway 设计](../04-module-poster-interop/04-02-external-agent-gateway-design.md)。
该项是核心产品完成后的最终互操作能力，不进入当前开发任务，也不为它提前安装 SDK、
开放端口或新增页面。

未来用户明确启动该阶段时：

1. 先补外部 Actor 身份传播和默认拒绝的 Capability Policy；
2. 再交付默认关闭、仅绑定 `127.0.0.1`、只读的 MCP 垂直切片；
3. 长任务使用 `start/get/cancel` 复用现有 Run/Turn，不创建第二套任务系统；
4. 存在明确 A2A Client 后，再映射 Agent Card、Task、Artifact、Streaming 和 Cancel；
5. 所有协议 Adapter 只调用 Capability/Agent Turn Service，不直接访问数据库。

进入开发的就绪条件、开关语义、首批 Tool/Resource、身份策略和未来测试范围均以
`04-02` 为准。未满足条件前，本节不是可领取的开发任务。

### E6：真实模型安全验收

用户已授权在验收阶段使用“模型”设置中已配置的真实模型；本轮仅完成设计与任务拆分，未调用真实模型，也不读取、回显或写入任何密钥。

真实模型只用于核心产品的单个完整端到端验收，不替代确定性测试。单元、模块、契约、
Graph、组件和普通 Playwright 均禁止调用真实模型。

- 仅显式 `AI_SIGNAL_RUN_LIVE_MODEL_TESTS=1` 执行；
- 只有确定性全量回归通过后，才从专用 `tests/live/` 入口执行；
- 使用用户已保存的模型 ID，通过公开 Agent 入口完成真实业务完整链路；
- 每次只运行一个代表性完整链路，Harness 限制 1～2 次模型请求、小型输出上限和固定
  超时；
- 不读取、打印或截图 Secret 文件；
- 非确定性断言只检查结构化终态、非空可见文本、模型 ID、耗时和流结束；
- 429、超时和无效模型只标记 Provider 步骤，保留其他已完成能力结果；
- 失败后不自动连续重试消耗额度；
- 不让真实模型直接删除、发布、写数据库或绕过 Capability。

### E7：LangChain/LangGraph Context Kernel 与 Domain Pack

目标设计：

- [02-03 Workspace Agent 上下文工程与动态工作流](../02-module-review-agent/02-03-agent-context-engineering-and-workflows.md)
- [02-04 Agent 工作流历史图谱](../02-module-review-agent/02-04-agent-workflow-history.md)
- [02-05 Workspace Agent 最终工程蓝图](../02-module-review-agent/02-05-final-agent-engineering-blueprint.md)
- [Agent Task Graph 0.4.0](../../graph-specs/02-module-review-agent/02-agent-task-graph.yaml)
- [Figma 当前工作流图](https://www.figma.com/board/dF7TcDtCd3J96E0Bb0F5Ad)

#### E7-T0 设计与同步基线

状态：**已完成（2026-08-05）**。

- 固定 `workflow_version=0.4.0`；
- 设计 Base + Domain + Task/Step + Evidence 上下文栈；
- 增加 Product Turn Harness、Evaluation Harness、Action/Approval、DAG 调度与适配性审查；
- 建立追加式 Markdown 历史图谱；
- 建立机器可读目标 Graph Spec；
- 生成可编辑 FigJam；
- 把“工作流变化必须同步图谱”写入 `AGENTS.md`。

#### E7-T1 真实 Agent 依赖与模型适配

- 在 Agent 可选依赖和安装脚本中加入稳定主版本并锁定：
  `langchain`、`langchain-openai`、`langgraph`、
  `langgraph-checkpoint-sqlite`；
- OpenAI-compatible 工作区模型通过 LangChain Chat Model 适配，不继续扩展自制聊天
  协议；
- 保留确定性 Fake Chat Model，但测试必须运行真实 LangChain Agent/Graph/Tool 路径；
- 增加 `supports_tool_calls` 的真实连接测试，不按模型名猜测；
- 没有 Tool Calling 的模型只允许纯对话和来自结构化快捷动作的确定性 Fast Plan。

#### E7-T2 Base Prompt 与 Context Assembler

- 新增版本化 Base Prompt，放系统级身份、安全、审批、部分成功和输出规则；
- 加载 Agent Pack 的身份、偏好、知识和长期记忆，不能把安全规则下放给 Agent Pack；
- 实现 `ContextAssembler`，记录各层版本、摘要哈希和预算；
- Conversation History、Turn State、Graph Checkpoint、长期偏好和业务数据分别管理；
- 外部网页和信息正文只进入受边界标记的 Evidence，不进入 System Prompt；
- 旧 Tool 结果压缩为 ID、状态、数量和小型摘要。

#### E7-T3 模块 Domain Pack

每个模块在自己的目录内维护：

```text
modules/<domain>/agent/
├── domain.yaml
├── prompt.md
├── tools.py
├── schemas.py
├── result_blocks.py
├── examples/
└── workflows/
```

Domain 按真实纵向闭环逐批建立，不预建空壳：

```text
第 1 批：intelligence + collection
第 2 批：tasking + sources + runs
第 3 批：review + cards
```

`information_library` 合入 `intelligence`；`models/workspace/agent/observability` 先作为受控
设置、会话或诊断能力，只有出现独立 Prompt/Tool 语义时才拆成 Domain Pack。

工具说明必须包含“何时使用/何时不用、参数、返回、风险、审批、幂等、稳定错误和恢复
建议”；JSON Schema 从 Capability 输入输出生成，不复制业务校验。

#### E7-T4 动态 Tool Resolver 与能力一致性

- Planner 初始只看到轻量 Domain Index；
- 每个步骤最多激活 3 个 Domain、暴露 8 个工具；
- 使用 LangChain Agent Middleware 动态装配 Prompt 和 Tool；
- 工具可见集合取
  `Registry ∩ Workspace ∩ Agent Pack ∩ Actor Policy ∩ Step ∩ Model`；
- Tool Resolver 只能缩小工具集合，Capability Gate 才是执行授权边界；
- 修复 Catalog、Runtime Registry、Agent Pack 和 REST 的漂移；
- Catalog 中没有真实实现的接口不能声明为已支持。

#### E7-T5 Evidence、记忆与 Context Budget

- 新增 `EvidenceBundle`、去重、时效性、冲突和资料缺口字段；
- Context 依次执行 Write/Select/Compress/Isolate；
- Conversation Summary 使用结构化 Schema 与回归样例；
- 记录 Context Snapshot 的层名、版本、大小和引用，不回显完整 Base Prompt；
- 长期记忆只写用户明确保存的偏好，可查看、修改、撤销和软删除；
- Tool Schema 超过可用上下文 5% 时才启用 Catalog → Inspect 渐进发现；
- 首版不引入独立向量数据库。

最小测试：

1. 每次模型调用包含 Base Prompt；
2. 未选 Domain 的 Prompt 和 Tool 不进入模型请求快照；
3. Domain 不能覆盖 Base Policy；
4. 禁用能力既不暴露，伪造 Tool Call 也被 Executor 拒绝；
5. Catalog、Registry、Agent Pack 和 Adapter 能力清单一致；
6. Prompt、Domain 和 Tool 版本随 Turn 记录且不记录 Secret。

### E8：Product Turn Harness 与结构化 Plan/Execute/Replan StateGraph

生产路径必须使用 LangChain Agent 与 LangGraph `StateGraph`，禁止新增关键词分支或自制
Tool Loop。

#### E8-T1 Plan 契约

- 新增 `AgentPlan`、`PlanStep`、预算、依赖、成功条件和失败策略 Schema；
- 增加 Direct Response、Deterministic Fast Plan 与 Structured LLM Plan 三种统一模式；
- 使用 LangChain structured output 生成，禁止正则解析自由文本 Plan；
- 顶层最多 5 步、最多重规划 2 次；
- Plan Validator 拒绝未知能力、循环依赖、超预算、虚假审批和未验证资源 ID；
- 每步引用注册的 `acceptance_policy`，不能靠自由文本成功条件自我宣布完成；
- 自然语言 Fast Plan 不能依赖旧关键词分支；无法确定时进入 LLM Plan。

#### E8-T2 LangGraph 主图

- 按 `02-agent-task-graph.yaml` 实现稳定节点 `N01`～`N25`；
- `N10` 使用 `Send` 调度就绪步骤，`N21` 汇合并行结果；
- `N12 Action Binder` 与 `N13 Action Validator` 在审批前产生可验证参数和
  `input_digest`；
- 原子动作进入 Capability Executor；
- 开放式步骤进入有预算的 LangChain Domain Agent，已知长流程进入模块 LangGraph
  Subgraph；
- 只读独立步骤可用 `Send`/等价 API 并行，写步骤顺序执行；
- Clarification Gate 与 Approval Gate 分离；
- Result Inspector 只返回
  `continue/replan/await_user/await_approval/complete/partial/failed`；
- Reflection 不能直接调用工具或批准动作。

#### E8-T3 Product Turn Harness 与持久化

- 实现 `ExecutionManifest`、`TurnLease`、`DeadlineBudget`、`CancellationToken`、
  `EventJournal`、`RecoveryScanner` 和统一 `Finalizer`；
- 本地单实例使用独立 `data/agent-checkpoints.db` 的 LangGraph SQLite Checkpointer，
  内存 Checkpointer 只用于单元测试；
- 开启 WAL、短事务和单写入协调；
- Plan、步骤前后、interrupt 和 Artifact 保存后 checkpoint；
- 幂等键使用 `turn_id + step_id + capability_id + input_digest`；
- 进程重启、Web 断线、等待审批和等待用户输入后可恢复；
- 成功并行步骤不能因同批其他步骤失败而重跑；
- 启动时扫描 `running/waiting/stale` Turn，版本不兼容时安全终止并返回可定位错误；
- 模型不可用时保留确定性 UI/REST 动作，不伪装自然语言 Agent 已成功；
- 多实例仅预留 PostgreSQL Checkpointer，不引入 Kafka/Celery/微服务。

#### E8-T4 迁移与 UI

- E2 的 `AgentTurnEvent` 投影 LangGraph stream/astream 事件；
- 旧关键词路径只允许迁移期兼容并受 Feature Flag 隔离；确定性 Fast Plan 读取结构化
  ClientCommand/快捷动作，不复用关键词 `_run_action()`；
- E8 完成后关键词互斥 `_run_action()` 退出生产主路径；
- UI 展示计划摘要、步骤、耗时、Domain、Capability、部分成功和恢复动作；
- 不显示隐藏思维链、完整 Prompt 或原始工具 JSON。

最小测试：

1. 真实 StateGraph 路径完成单 Tool 与 Subgraph；
2. Plan DAG、并行、局部失败、依赖跳过和有界 Replan；
3. Clarification 与 Approval interrupt/resume；
4. 进程重启恢复且副作用不重复；
5. 取消、等待、部分完成和不可恢复错误均有稳定终态；
6. Playwright 显示计划、步骤、实时耗时、审批和恢复。

### E9：AI 信息研究工作流

首批交付最高频的信息工作：

```text
research.filter
research.recommend
research.match_requirements
research.compare
research.trend_brief
research.coverage_gap
collection_then_analyze
```

需要补齐：

- 信息详情和批量查询的稳定引用；
- 日期、主题、来源、任务、已读、收藏、颜色、数量和排序条件；
- 推荐结果的来源、理由、证据和站内 AI 信息跳转；
- 比较表中每个事实的 `information_id`；
- 趋势摘要的代表信息、反例和资料缺口；
- 采集部分失败时仍分析成功来源；
- 候选不足时返回较少结果，不伪造补足；
- 分析失败时仍交付已查询信息和来源。

结果块：

```text
information_list
recommendation_list
comparison_table
trend_summary
evidence_sources
partial_failure
navigation_action
```

最小验收场景：

1. 推荐过去 30 天最值得关注的 5 条 Agent 信息；
2. 按开源、本地部署、Windows 和官方证据筛选；
3. 比较三个 Agent 框架；
4. 分析一个月趋势并给出反例；
5. 先采集再分析，单来源失败后仍返回推荐；
6. 每条结果都能跳到站内信息详情。

### E10：站内能力 Agent 全覆盖

把站内用户可理解的业务动作 Capability 化，不把 REST 路由或数据库直接暴露给模型。

#### E10-T1 信息管理

- 已读、收藏、归档、笔记、保存视图和专题；
- 单条显式操作可直接执行，模型推断出的批量写操作需要确认；
- 按 item 返回部分成功和幂等结果。

#### E10-T2 审核与卡片

- 查询批次、逐项建议、保留/拒绝/延后和批量提交；
- 卡片查询、生成、修改、模板/字数校验和导出；
- 批量审核、覆盖编辑和渲染按 Policy 审批；
- 单卡失败不阻断其他成功草稿。

#### E10-T3 任务

- 查询、创建草稿、修改、预览、创建版本、启停、运行、取消和重试；
- 启用计划必须确认；
- 预览失败保留草稿，新版本失败不覆盖活动版本；
- REST、Agent、Scheduler 都调用 `task.run.start`，不能一部分直调 Service。

#### E10-T4 来源与运行诊断

- 来源列表、无副作用测试、健康诊断、修复草稿、启停；
- 修改地址、类型或启停先展示影响并确认；
- Run、SourceRunResult 和 Capability Invocation 查询；
- 只重试失败来源、按原版本或当前版本重试；
- 来源测试失败是可展示诊断结果，不是 Agent 崩溃。

#### E10-T5 模型、外观和会话

- 模型可查询、测试和为当前会话选择；Secret 永不进入模型；
- 新增/修改模型密钥只打开设置表单，由用户输入；
- 外观修改投影为受控客户端动作，不能让后端直接操作 DOM；
- 会话重命名、置顶、归档和恢复可开放；物理删除不开放。

最小测试：

1. 每个站内 Agent Tool 映射唯一 Capability；
2. 所有读动作和受控写动作有 Schema、Policy、幂等与稳定错误；
3. 批量写入某项失败不吞掉其他结果；
4. 禁用、审批拒绝和 Provider 失败都有可恢复 UI；
5. REST 与 Agent 对同一输入得到相同业务结果。

### E11：Evaluation Harness、协议与图谱同步门

#### E11-A 首个成品后的 Evaluation Harness

- E8/E9 首个前端 + Agent + Capability 闭环先采用每个行为 2～6 个关键测试推进，不让
  大型评测集阻塞成品；
- 首个闭环验收后建立 24 个手工高质量场景，覆盖查询、推荐、比较、趋势、采集后分析、
  来源修改、定时任务、部分失败、注入攻击、禁用能力、审批和断点恢复；
- 提供确定性 Workspace Fixture、Fake Model、Fake Tool、固定时间与 Failure Injection；
- 默认 Fake Model，但执行真实 LangChain/LangGraph/Tool/Capability 路径；
- Grader 顺序为 Outcome、Contract、Trajectory、Safety、Reliability、UX、Cost/Latency；
- 开放式内容最后才使用可选 LLM Judge，不比较固定文案；
- 增加 Context Snapshot 测试，确保不相关 Domain/Tool/正文不进入模型；
- 增加 Prompt Injection、预算耗尽、无限 Replan 和 Secret 泄漏测试；
- 本地 TraceSink 和 pytest Grader 必须可用；LangSmith 只作为可选开发增强。

#### E11-B 发布回归与协议

- 将脱敏后的真实失败轨迹逐步扩展为约 40 个回归场景；
- 全部日常 Trial 使用 Fake Model 并与人工抽查校准；
- 外部 Gateway 进入最终互操作阶段后，MCP/A2A 复用同一 Plan/Event/Result，不共享
  隐藏推理；
- 增加 Catalog/Registry/Agent Pack/Adapter 一致性校验；
- 增加工作流同步校验：Graph Spec、Markdown 当前版本、Figma URL、设计文档和任务状态
  必须使用同一个 `workflow_version`；
- 每次拓扑变化向历史 Markdown 追加完整 Mermaid 图，不覆盖旧图。

最小测试：

1. Eval 结果可重复并保存 workflow/prompt/domain/tool/model 版本；
2. `workflow_version` 四方一致；
3. 未来 MCP/A2A 只能调用已验收工作流，不包装旧关键词 Agent；
4. 真实模型只在 E6 完整链路专用入口与显式开关同时满足时运行；
5. 工作流图谱未同步时文档/契约校验失败。

## 7. 新批次完成定义

一个 Epic 只有同时满足以下条件才可从“未开始”改为“完成”：

- 用户可通过前端完成完整场景；
- 内置 Agent 通过同一 Capability 完成同一业务动作；进入最终互操作阶段后，外部
  MCP/A2A 再满足同一要求；
- 状态、耗时、来源和错误与后端记录一致；
- 功能开关、Actor Policy、审批和幂等真实生效；
- 关键 Domain/Application、REST/Adapter、组件与 Playwright 测试通过；
- Agent 相关 Epic 真实运行 LangChain Agent、LangGraph StateGraph 和持久 Checkpointer，
  不能由关键词分支或测试替身绕过；
- 1024px、1360px、1600px 桌面布局通过；
- 相关模块文档、OpenAPI、JSON Schema 和本文件同步；
- Agent 工作流版本、Graph Spec、历史 Markdown、Figma 当前图和验收证据同步；
- 没有把团队、账号、插件市场、节点画布或任意函数执行带入范围。

## 8. E0 + E1 交付证据

2026-08-05 已按首批范围完成：

- 外观值在首屏渲染前恢复；只有用户操作才持久化，非法值只归一化一次；
- 来源创建与 Patch 复用完整定义校验，类型编辑只读，重名稳定返回
  `SOURCE_NAME_EXISTS`/409；
- 多会话 REST、SQLite 兼容升级、自动/手动标题、置顶排序、归档、软删除和恢复
  已形成前后端闭环；
- Agent 页面在 1536×1024 使用常驻会话栏，在 1024×768 使用可关闭抽屉；
- 后端全量 `65 passed`，其中 E0/E1 目标回归 `22 passed`；契约 2 条包含在全量测试中；
- 前端单元测试 `10 passed`，Playwright 桌面流程 `7/7` 通过；
- 仅保留一条既有 Starlette/httpx 弃用警告；
- OpenAPI Outline 与 Agent 会话模块文档已同步。

本批次完成的是 E7-T0 的 0.4.0 最终蓝图、Graph Spec、历史 Markdown、Figma 当前图、
长期同步规则，以及 E11-A/E11-B 的评测任务基线；没有实现 E2～E11 的运行时代码，
现有 E0/E1 功能也未在本批次扩展。

E0/E1 当前仍位于未提交工作区。其他开发对话应先读取现有 diff 和本节证据，不得重复
实现、回滚或覆盖这些文件。

## 9. 其他开发对话的接手入口

### 9.1 可立即并行

| 开发线 | 推荐分支 | 可做范围 | 暂时不要做 | 首要验收 |
|---|---|---|---|---|
| A：E2 Turn/Event 公共契约 | `codex/e2-agent-turn-events` | Turn/Step/Event/ResultBlock 数据、202、SSE、耗时、恢复与终态 | 不实现 Planner 和 Domain Tool | SSE 顺序、断线续传、最终持久化 |
| B：E7 Context/Evidence 契约 | `codex/e7-agent-context-kernel` | LangChain/LangGraph 依赖、Base Prompt、Domain Pack、EvidenceBundle、Catalog 一致性测试 | 不改 E2 会话/事件表，不接 UI | 未选 Domain 不进入模型请求 |
| C：E3 Timeline | `codex/e3-timeline-cursor-groups` | 稳定游标、日期折叠、分段加载、深链 | 不改 Agent Runtime | 两页无重复、Agent 深链可定位 |
| D：E4 Source Modal | `codex/e4-source-dialog-dry-run` | Modal、草稿测试、样例、错误和焦点 | 不重做 E0 Patch 校验 | 草稿测试零副作用 |

如果这些开发线共享同一工作树，开始前必须协调文件所有权；不要同时编辑
`agent_runtime/service.py`、`schemas.py` 或 `models.py`。优先让 A 拥有 Agent Turn 数据，
B 只落独立 Context/Domain/Evidence 契约；A、B 的公共 Schema 合并后再接 E8。

### 9.2 串行依赖

```text
E7-T0（蓝图已完成）
→ E2 + E7-T1～T5
→ E8
→ E9 只读工作流（Fake/Fixture）
→ E11-A + E10
→ Module 3（Agent Pack / Artifact / 实时转写）
  + Module 4 剩余范围（Poster Graph / 编辑 / PNG Artifact）
→ 剩余核心能力 + E11-B 确定性发布回归
→ E6 单个完整真实模型链路
```

- E8 不得在 E2 的持久 Turn/Event 或 E7 的 Domain/Tool Contract 之前自行定义平行状态；
- E8/E9 先用简单 TDD 做成首个纵向闭环；E11-A 再把实际成功和失败轨迹整理为评测集；
- E9 先交付查询、推荐、比较和采集后分析，再扩展趋势与覆盖缺口；
- E10 按信息管理 → 任务/来源/Run → 审核/卡片 → 模型/外观/会话推进；
- Module 3 按 Agent Pack 原子导入、Artifact 检索、WebSocket 转写三个纵向闭环推进；
- Module 4 本批只完成 Poster Graph、编辑和 PNG Artifact；外部接口不随之启用；
- E5 为 Deferred 设计项，不在当前串行依赖中；进入最终互操作阶段时不暴露旧关键词
  Agent；
- E6 不拆模块级 Smoke；只在核心功能完成且确定性全量回归通过后执行一次完整发布验收。

### 9.3 每个对话开始前必读

```text
AGENTS.md
docs/02-module-review-agent/02-00-overview.md
docs/02-module-review-agent/02-05-final-agent-engineering-blueprint.md
docs/02-module-review-agent/02-03-agent-context-engineering-and-workflows.md
docs/02-module-review-agent/02-04-agent-workflow-history.md
docs/05-platform/05-01-capability-contract.md
docs/05-platform/05-02-langgraph-workflows.md
docs/07-delivery/07-04-optimization-implementation-status.md
graph-specs/02-module-review-agent/02-agent-task-graph.yaml
prompts/07-delivery/07-complete-agent-and-product-release-coding-agent-prompt.md
```

### 9.4 基线命令

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\pnpm.ps1 --dir apps/web test
.\scripts\pnpm.ps1 --dir apps/web test:e2e
.\.venv\Scripts\python.exe scripts/validate_contracts.py
```

Agent Runtime 增量还应增加一条模块级命令，例如：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/modules/agent_runtime -q
```

接手对话只有在更新本节状态、附上实际测试证据并同步工作流图谱后，才可宣称对应 Epic
完成。

## 10. Workspace Agent 首个纵向切片交付证据

2026-08-05（Asia/Shanghai）按
`02-workspace-agent-next-slice-coding-agent-prompt.md` 完成：

- Agent Runtime 目标回归：
  `tests/modules/agent_runtime`、`test_agent_turn_stream.py`、
  `test_agent_capability.py`、`test_agent_conversations.py` 共 `21 passed`，
  包含部分完成后只重试失败来源、事件序列连续且不重复创建助手消息；
- 后端全量：`71 passed`，仅保留既有 Starlette/httpx 弃用警告；
- 前端单元：`10 passed`；
- Playwright：`8/8 passed`，新增流程覆盖已接收、计划、服务端耗时、终态、
  3 条真实信息卡与 `focus` 深链，同时原有外观、模型、任务、审核卡片和多会话流程
  继续通过；
- Next.js 生产构建通过，契约校验 `2 passed`，`git diff --check` 通过；
- 真实模型只读 Smoke 严格限制为 2 次、未调用业务 Tool：第一次定位到 Provider
  对小写 `json` 的要求，第二次确认其原生 JSON Schema 返回未遵守 `AgentPlan`；
  运行时据此显式改用 LangChain `function_calling` 结构化输出。因请求上限已到，
  该 Provider 修复尚未再次现场调用，确定性回归仍为发布依据；
- 本增量实现既定 `workflow_version=0.4.0` 节点职责，没有改变 Graph Spec 拓扑，
  因此未新建历史版本或重复生成 Figma。

自 2026-08-06 起采用新的额度保护规则：以上两次调用作为历史调试证据保留，后续单元、
模块、协议或局部 Smoke 不再调用真实模型；下一次真实模型调用只能发生在 E6 的专用
完整链路发布验收中。

## 11. 2026-08-06 Agent 与产品发布收尾实施状态

### 已完成并有目标测试证据

- E2/E8：持久 Turn/Event、SSE 续传、真实 `interrupt`/`Command`、租约恢复、取消、
  DAG 校验、局部失败、幂等与最多两次 Replan；
- E3/E4：稳定 `(published_at, id)` 游标、日期折叠/分段加载/深链，以及来源
  新增编辑 Dialog、草稿测试和稳定错误；
- E7/E9/E10：10 个按需 Domain Pack、Schema 驱动 Tool、研究工作流，以及来源、
  任务、运行、审核、卡片、信息状态、模型、会话和外观 Capability；
- Module 3：Agent Pack 安全原子版本、FTS、Artifact、本地实时转写协议与 WebSocket；
- Module 4：真实 Poster LangGraph、双审批、乐观编辑、离线 HTML/CSS 1200×1500
  PNG Renderer、Artifact 下载与 Agent 编辑/渲染；
- E11：真实 Graph + Fake Model 的 Outcome、Contract、Trajectory、Safety、
  Reliability 与 Cost/Latency 发布评测；
- 发布安全：工作树、跟踪文件和可发布 Git 历史 Guard，以及固定版本 Gitleaks
  pre-commit/Action。

### 图谱同步

主拓扑未改变，继续使用 `workflow_version=0.4.0`。Domain 路由和 Tool 装配事实已同步到
Graph Spec、本文、工作流历史和 Figma 节点 `3:304`，没有创建第二套 Runtime 或虚构
新版本。

### 最终确定性证据

- `scripts/verify.ps1 -E2E`：后端 `103 passed`、live_model `1 deselected`，
  契约 `2 passed`，前端 `12 passed`，ESLint、Next.js 生产构建和 Playwright
  `12/12` 全部通过；
- 非阻断警告：Starlette TestClient 对当前 httpx 适配的既有弃用警告 1 条；
- `git diff --check` 通过；
- Release Safety 的 worktree、tracked 和可发布 history 三种模式通过；
- `AI_SIGNAL_RUN_LIVE_MODEL_TESTS` 未获显式授权，真实模型调用 `0` 次；
- staged 模式将在显式路径暂存后执行；
- E5 外部 Agent Gateway 继续 Deferred。

Git 分支、提交、推送与 Draft PR 仅在 staged 审计通过后更新，不提前写成完成。

## 12. 2026-08-06 复杂任务阻断缺陷重新打开

状态：**P0 Reopened；此前“发布收尾完成”不再代表复杂自然语言 Agent 已验收。**

用户原始场景：

```text
你好，请你帮我收集最近24小时的热点AI内容，并选出其中影响力最大的三个，给我分析总结
那么请你就目前收集的三天内的热点AI内容，并选出其中影响力最大的三个，给我分析总结
```

只读诊断确认：

- 前端关键词规则要求字面量 `Agent`，两条请求因此进入旧 `/api/agent-runs`；
- 旧 `_run_action()` 匹配“收集”后只执行 `collection.run.start` 并立即返回；
- 两次实际消息的 `turn_id` 与 `effective_model_id` 均为空，所选模型未参与；
- 当前信息库存在最近三天候选，失败不是因为缺少数据；
- 新 Graph 仍缺 Goal Coverage、真实 Conversation Context、Acceptance Policy 验收和跨条目
  综合分析；
- 当时的固定 Fake/E2E 提示词恰好包含 `Agent` 与“推荐”，因此测试全绿未覆盖该缺陷。

当前唯一实施入口：

```text
prompts/02-module-review-agent/02-workspace-agent-complex-task-repair-coding-agent-prompt.md
```

必须以两条原始提示词建立 TDD，统一自然语言 Runtime，并取得 24h/72h、3 条、影响力
排序、带引用综合分析和真实流式 ResultBlock 的全栈证据。只删除前端关键词判断或让 Fake
返回正确计划都不能关闭本缺陷。

本修复预计沿用 N01～N25 主拓扑，但会改变 Context、路由、Planner、Inspector 和结果
合并契约；实施增量目标 `workflow_version=0.5.0`，必须同步 Graph Spec、追加式历史
Markdown、Figma 当前图、本文、契约和 Graph/Eval/E2E 测试后才能重新标记完成。

## 13. 2026-08-06 Workspace Agent 0.5.0 复杂任务修复

状态：**代码、确定性全栈与真实模型两轮闭环已通过；Figma 写入仍被外部安全门禁阻塞。**

已落地：

- 前端所有自然语言、纯解释和带 Artifact 的消息默认进入 Turn API；删除
  `isWorkspaceResearchRequest`，旧 `/agent-runs` 只同步映射同一 Turn；
- `AgentGoalSpec` 固化 operation mode、24/72 小时时间窗、3 条、impact、deliverables、
  use existing、collection 与 synthesis 要求；
- N08 同时验证 DAG、Capability、参数和 Goal Coverage，欠完整计划带 gap 反馈进入有界
  Replan；
- Conversation Context 限制为最近 8 条消息摘要和 3 个 prior Turn/Run/Result 引用；
- 四步链使用精确时间窗、Query 真实候选 ID、可解释颜色/相关性/时间/稳定 ID 排序，
  `items_added=0` 不阻止后续查询；
- `research.trend_brief` 返回 overview、key findings、why it matters、differences、
  uncertainties 和逐 finding `information_ids`；
- N22 验收真实 ID、来源、站内路径、数量下限和 grounded synthesis；不足时不再无警告
  complete；
- `result.block` SSE 携带完整 ResultBlock；UI 增量去重渲染 Plan、采集、推荐、综合、
  Evidence、局部失败和安全未知类型 fallback；
- Manifest/Turn 分离 requested/effective model ID，测试 Provider 只能由显式
  `agent_test_mode` 选择；正常 heuristic 配置不再伪装模型成功；
- OpenAI 标准兼容端点使用中性 Provider 画像；DashScope 的思考模式参数只位于
  Provider Adapter。核心 Graph、Goal/Plan、Capability 和 Inspector 不感知厂商；
- 健康检查公开 `workflow_version`，启动器与 Graph Spec 做版本握手；旧 API 即使返回
  HTTP 200 也不会再被当前启动器误当作可复用服务。Windows Uvicorn reload 父进程
  已退出但 multiprocessing 子进程仍持有端口时，可按监听父 PID 安全识别并清理；
- 未执行的依赖步骤显示为“未执行”，不再因缺少 Capability Result 被默认标为
  “已完成”；模型配置和已知 Provider 兼容错误显示稳定错误码与安全提示，不回显
  Provider 原始负载；
- Capability ID 为机器枚举，Planning Contract 约束四步链每步的 kind、side effect、
  acceptance policy 和依赖；解析失败使用 `include_raw` 的一次 Schema 修复，禁止
  无约束 JSON fallback；
- workflow/state/plan/event 版本为 `0.5.0/1.1.0/1.1.0/1.1.0`；未完成 0.4
  checkpoint 显式失败，已完成历史 Turn 保持可读。

目标与发布证据：

- Goal/Plan、Provider 兼容、Graph 与两个原始 API 场景最新目标回归：`15 passed`；
- `/agent-runs` 兼容 Adapter 的统一 Runtime 与幂等副作用已覆盖；
- 前端单元 `12 passed`，Next.js 生产构建通过；
- 确定性 `scripts/verify.ps1 -E2E`：后端 `132 passed / 1 deselected /
  0 failed / 0 xfail`、契约 `3 passed`、前端 `12 passed`、ESLint、Next.js 构建与
  Playwright `12/12` 通过；
- 显式授权的专用真实模型验收选择 `qwen3.7-plus`：同一 Conversation 内场景 A
  为 `collect_then_analyze / 24h / 3 / impact`，能力顺序为
  `collection.run.start → intelligence.timeline.query → research.recommend →
  research.trend_brief`；场景 B 为 `analyze_existing / 72h / 3 / impact`，
  `collection.run.start × 0`，随后查询、推荐与综合。两轮均为 `complete`，
  测试 `1 passed / 0 failed / 0 skipped / 0 xfail`，耗时约 92 秒；
- 用户本地正式服务重启后使用稳定模型 ID 再执行场景 A：真实
  `qwen3.7-plus` 在 `workflow_version=0.5.0` 完成结构化四步 Plan，requested 与
  effective model ID 一致；采集 `40`、新增 `0`，精确 24 小时查询为 `0`，因此按
  Acceptance Policy 返回 `partial` 并明确显示“0 条可追溯结果”，不再返回
  `AGENT_EXECUTION_FAILED`。该现场验收耗时约 79 秒；
- Release Safety、最终全量覆盖结果和 Draft PR 证据在本节完成后补录。

Figma 阻塞：连接器拒绝向指定 FigJam 写入内部工作流架构，提示外部文件所有权与目标
授权不足。已遵守门禁停止写入，没有新建替代文件或绕过；在取得用户明确外部目标授权
并完成同板截图前，Figma 同步保持未完成。

## 14. 2026-08-06 Workspace Agent 0.6.0 工具可选与语境推理

状态：**代码、Graph Spec、契约、历史、确定性全栈与真实模型已通过；Figma
仍等待同一外部目标的明确写入授权。**

- Planner 允许只读 `model_reasoning`，工具不再是所有计划步骤的必选项；
- N12～N14 对该步骤执行受控 bypass，N16 路由到 N18，由本轮
  `effective_model_id` 完成语境推理；
- `model_response` 结果块携带正文、basis、证据边界、信息 ID 与实际模型 ID；
- Conversation Context 增加前序推荐、趋势和模型回答的小型 Result 摘要；
- 模型连接状态改为 `pending / healthy / needs_retest / error / not_applicable`：
  新建/编辑后标记待检测并由用户显式检测，正常模型选择不检测，疑似 Provider
  错误只标记需复检；
- Provider 核心仍为 OpenAI-compatible 中性接口；阿里云参数继续隔离在兼容适配器；
- workflow/state/plan/event/context 版本为
  `0.6.0/1.2.0/1.2.0/1.2.0/1.2.0`。

验收证据：

- Agent Runtime + 模型配置首批目标回归：
  `26 passed / 0 failed / 0 skipped / 0 xfail`；
- 前端单元：`12 passed / 0 failed / 0 skipped / 0 xfail`；
- 最终 `scripts/verify.ps1 -E2E`：后端
  `136 passed / 0 failed / 1 deselected / 0 xfail`，契约 `3 passed`，前端
  `12 passed`，ESLint、Next.js 生产构建与 Playwright `12/12` 通过；
- `validate_contracts.py`、`validate_versions.py`、`git diff --check` 通过；
- Release Safety 的 worktree、tracked、history 三种模式全部通过；
- 专用真实模型验收使用 `qwen3.7-plus`，测试
  `1 passed / 0 failed / 0 skipped / 0 xfail`，耗时约 100 秒：
  - 24 小时场景为 `collect_then_analyze`，真实调用
    `collection.run.start → intelligence.timeline.query → research.recommend →
    research.trend_brief`，返回 3 个真实 `information_id`；
  - 三天场景为 `analyze_existing`，真实调用
    `intelligence.timeline.query → research.recommend → research.trend_brief`，
    没有再次采集；
  - “请你挑选出刚才收集内容中，影响力最大的三个并进行分析总结”为
    `direct/model_reasoning`，`capability_id=null`，Capability Invocation 为 0，
    返回 `model_response`，requested/effective model 相同；
- Replan 产生的旧步骤在运行记录中标记 `superseded`，不再作为 pending 冒充当前计划；
- `model_response.information_ids` 从前序有界 Result 摘要复用真实 ID，不生成新 ID；
- Figma：沿用已报告的目标授权阻塞，未重试或绕过。

## 15. 2026-08-06 Workspace Agent 0.6.0 空结果推荐与趋势修复

状态：**代码与目标回归通过，完整全栈和真实模型验收进行中；Figma 仍等待授权。**

- 实机根因：查询返回 0 条后，N22 把 `items_below_minimum` 作为不可恢复失败，
  `research.recommend` 和 `research.trend_brief` 因依赖失败均未执行；
- 修复：空时间线、候选不足和无证据 finding 是可定位的 `partial` 覆盖缺口，
  依赖链继续执行；
- `research.recommend` 进入 N18，用本轮模型在有界候选上生成推荐理由和趋势综合；
  `research.trend_brief` 复用同一结构化综合并保留独立 Capability Invocation；
- 空候选时两个步骤仍执行，但只输出证据不足说明，不虚构 AI 热点、来源、ID 或评分；
- SSE 新增 `model.research.started/completed` 和 `step.outcome`；UI 展示每步部分完成、
  推荐说明、趋势不确定性和真实覆盖缺口；
- OpenAI-compatible 结构化结果会在 Capability 边界内归一化：保留有效模型理由，
  过滤无效/重复 ID，按真实能力排序补齐遗漏推荐，并把趋势引用约束到真实选择；
  归一化不增加模型调用；
- 工作区证据核验为 46 条信息、6 个来源配置（3 个启用），24h/3d/30d 分别为
  0/3/34 条；采集 40、新增 0 是去重，不再错误等同为工作区没有证据；
- 精确窗口不足时明确补充已保存背景，披露实际窗口；默认中文、唯一总结块、证据和
  不确定性去重、模型错误中文解释已实现；
- 联网搜索为待审核的 17.2 Blueprint Change Proposal，当前未改生产拓扑；
- 当前定向证据：后端 30 passed，默认中文/Provider 后备目标集 19 passed，
  Web 13 passed，ESLint passed；最终全量和真实模型验收待更新。

## 16. 2026-08-06 Workspace Agent 0.7.0 统一搜索与联网补证

状态：**实现、完整确定性全栈、Release Safety、真实模型验收与 Figma 同板同步
已全部通过。**

- 新增 `intelligence.search`：同一 `intelligence_id` 跨待处理、情报库、已归档和
  卡片阶段检索，避免重复候选；
- 排序采用 FTS5 BM25、短词子串兜底、RRF 融合以及 Top 候选 SimHash 近重复分组；
- 新增 `web.search.collect`：本地结果达到目标时零网络调用；不足时通过 Provider
  Adapter 搜索 URL，遵守 robots 与现有 SSRF/MIME/大小边界，页面和查询均有 TTL
  缓存；
- 抓取结果进入原有 RawItem/Intelligence 分析、标签、优先级和 canonical URL 去重
  链路，模型只接收紧凑候选；
- 缺少搜索密钥或外部 Provider 失败时返回中文 partial 和明确错误，保留本地研究结果；
- 默认 Brave 仅是第一个 Search Provider Adapter；Agent Graph、Capability 和模型
  分析仍不感知厂商；
- workflow/state/plan/event/context 版本为
  `0.7.0/1.2.0/1.2.0/1.2.0/1.3.0`；
- Capability 的 Domain、kind、side effect、risk 和 acceptance policy 由服务端注册
  契约裁定；Goal 已验证的时间窗、条数和排序条件由服务端写回 Plan 与工具输入，
  避免不同 Provider 的字段别名、未知 Domain 或风险自报造成无效重规划、审批中断和
  `FileNotFoundError`；
- 真实中高风险写操作仍按服务端策略进入审批，联网读取、受限抓取与缓存不会因模型
  自报 `medium` 风险而错误暂停。
- Context Contract `1.3.0` 增加从持久 Plan/步骤状态/安全错误摘要派生的工作记事板；
  每个模型步骤都会复述目标、当前步骤与 Todo，Turn 结束后不把派生 scratchpad 污染
  下一任务；
- 模型载荷改为确定性合法 JSON 预算压缩，超限优先保留可恢复 ID、路径、URL、目标、
  状态和错误码，并产生 `context.compacted` 事件；不再用字符串切片生成残缺 JSON，
  也不为压缩额外调用真实模型。

验收证据：

- 后端确定性全量：`155 passed / 1 deselected / 0 failed / 0 xfail`；
- 契约 `3 passed`、前端 `13 passed`、ESLint、Next.js 生产构建和 Playwright
  `12/12` 通过；
- `git diff --check` 与 Release Safety 的 worktree、tracked、history 模式通过；
- 专用真实模型验收选择 `qwen3.7-plus`：`1 passed / 0 failed / 0 skipped /
  0 xfail`，耗时约 146 秒。同一 Conversation 中 24 小时
  `collect_then_analyze` 五步链、72 小时 `analyze_existing` 三步链、无工具
  `direct/model_reasoning` 均为 `complete`；
- 2026-08-07 获得用户明确授权后，已将 0.7.0 统一搜索与按需联网补证流程追加到
  `https://www.figma.com/board/dF7TcDtCd3J96E0Bb0F5Ad`，可编辑图节点为
  `10:305`～`10:385`；
- Figma Release Sync Section `12:364` 明确记录
  `0.7.0/1.2.0/1.2.0/1.2.0/1.3.0`、Context Engineering 边界和上述验收证据；
  节点回读与 2048px 截图核验均通过，无裁切、无重叠，图谱同步门禁已关闭。
## 17. 2026-08-07 Workspace Agent 0.8.0 个性化上下文与搜索模型

状态：**实现、契约、文档、Figma、完整确定性全栈与真实 qwen3.7-plus 验收全部通过。**

- 模型设置新增唯一“搜索模型”角色，使用 OpenAI 兼容 Responses `web_search`；
  支持 OpenAI 与百炼，共用现有抓取、缓存、正常化与统一检索链，Brave 保留为备用；
- Provider 复用选择器列出全部关联模型名称，避免同名 Provider 无法区分；
- Agent Pack 新增可编辑、可版本化 Rules / Skills；默认提供证据优先、清晰中文和
  安全操作三项 Skill；
- Rules 始终有界加载；Skill 仅按当前步骤 Domain 动态选择，禁用项不进入 Context，
  每轮 Manifest 记录 Agent Pack 版本；
- 运行记录按信息处理、Agent、内容产物和其他粗粒度切换；分类由能力前缀派生，
  新能力仍会进入“其他”，不会被固定枚举隐藏；
- Artifact 按生成内容、图片、文档切换，并展示来源标题、来源时间和可用跳转链接；
- `workflow/state/plan/event/context` 版本为
  `0.8.0/1.2.0/1.2.0/1.2.0/1.4.0`；N01～N25 拓扑未改变。
- Figma 已在既定 FigJam 追加 0.8.0 Release Sync Section `15:364`，业务节点
  `16:366`～`16:399`、连接器 `17:388`～`17:436`；1800px 截图核验无裁切、无重叠，
  0.7.0 历史 Section `12:364` 保持不变。
- 验收：后端 `162 passed, 1 deselected`；契约 `3 passed`；前端 `13 passed`，
  ESLint 与生产构建通过；Playwright `13/13`；专用真实模型命令使用
  `qwen3.7-plus` 完成 `1 passed`，耗时 148.76 秒。

## 18. 2026-08-08 Workspace Agent 0.8.0 Agent Pack 启动兼容热修复

状态：**实现、确定性全量、浏览器回归与真实模型单次验收全部通过。**

- 根因是旧系统默认 Pack 仍处于 Active，且缺失 `agent.yaml` 时运行时直接抛出未处理
  `KeyError`；不是模型连接或 qwen3.7-plus 推理失败；
- 系统默认 Pack 现在随仓库默认版本安全升级；用户 Pack 保持优先，不会被启动流程覆盖；
- 相同版本的损坏/缺失存储会迁移到新的内容寻址目录后修复数据库引用；
- 运行时读取不到自定义 Pack 时使用有界内置规则继续执行，并记录可追溯降级事件；
- E2E 的 Agent Pack 与 Artifact 存储已隔离到临时目录；
- 验收：后端 `165 passed, 1 deselected`；契约 `3 passed`；前端 `13 passed`，ESLint、
  生产构建和 Playwright 通过；真实 qwen3.7-plus Turn
  `turn_f9464089162e4b64801d9afc0b6427a1` 为 `complete`，工作流仍为 `0.8.0`，
  Agent Pack 为 `0.2.0`。
