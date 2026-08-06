# 07-03 产品、业务与体验全面优化蓝图

## 文档定位

本文定义 AI Signal Studio 下一阶段的目标产品形态，覆盖业务闭环、信息架构、
页面框架、任务个性化、信息查找、Agent 协作、运行追溯、视觉系统和实施顺序。

本文是“目标状态与实施依据”，不是当前已经完成的事实。每完成一个垂直增量，
必须同步对应模块文档、机器契约和测试，不能只更新本文。

相关现行规范：

- [00-02 产品范围与用户流程](../00-project/00-02-product-and-user-flows.md)
- [00-04 模块边界](../00-project/00-04-module-boundaries.md)
- [05-03 前端架构](../05-platform/05-03-frontend-architecture.md)
- [05-04 UI 布局与组件](../05-platform/05-04-ui-layout-and-components.md)
- [05-05 设计令牌与主题](../05-platform/05-05-design-tokens-and-themes.md)
- [05-06 图标系统](../05-platform/05-06-icon-system.md)
- [02-03 Agent 上下文工程与动态工作流](../02-module-review-agent/02-03-agent-context-engineering-and-workflows.md)
- [02-05 Workspace Agent 最终工程蓝图](../02-module-review-agent/02-05-final-agent-engineering-blueprint.md)
- [06-01 简单 TDD](../06-quality-operations/06-01-simple-tdd-and-testing.md)
- [07-01 开发路线图](07-01-development-roadmap.md)

---

## 1. 结论先行

AI Signal Studio 应明确成为：

> 面向个人部署者的 AI 信息监测与整理工作台。用户用可复用任务持续采集信息，
> 在统一信息库中搜索、筛选、收藏、审核和制作卡片，并让 Agent 帮助创建、
> 修改、运行和解释这些任务。

下一阶段采用九项核心决策。

1. **“任务”成为一级业务对象。**
   前端不再要求用户理解“常用方案”和“定时任务”两套概念。用户只创建一个
   “信息任务”，其中同时包含目标、来源、规则、数量、计划和交付。

2. **所有内容进入一份统一信息库。**
   时间线、任务结果、保存视图、审核队列和专题板是不同查询或处理方式，不复制
   多份信息事实。

3. **自动信息流和人工精选内容分开。**
   任务持续产生信息；用户明确保留的内容进入专题板、审核或卡片。自动命中不等于
   用户认可。

4. **每次运行都必须可解释、可复现、可恢复。**
   运行绑定不可变任务版本，展示逐来源结果和筛选漏斗；部分失败、数量不足和真正
   失败必须准确区分。

5. **页面首先是工作工具，不是展示型仪表盘。**
   首屏直接提供搜索、信息、任务或对话，不设置装饰性 Hero，不堆叠卡片中的卡片。
   布局学习 Codex 的稳定导航、聚焦主区和按需详情区，但按页面任务分配栏位。

6. **普通配置简单，高级能力按需展开。**
   普通用户只需完成目标、来源、时间、数量和计划；包含/排除规则、去重、失败策略
   等放入高级设置。Agent 可生成结构化草稿，但不能用一段不可验证的 Prompt 代替
   核心业务字段。

7. **Agent 答复必须交付业务结果，而不只是聊天文字。**
   信息收集答复要展示执行耗时、来源覆盖、重点信息摘要、部分失败和可跳转的 AI 信息
   引用。执行过程和最终答复分层显示，不暴露模型原始思维链，也不把完整信息正文复制
   到对话中。

8. **内置 Agent、REST、流式 UI 与 A2A 共用一份结果契约。**
   协议适配层只转换消息、状态和 Artifact；不得重新实现任务、采集、筛选、审核或
   卡片业务。A2A 的本地调试入口必须可验证 Agent Card、流式事件和能力策略，但不能
   变成绕过权限的“任意函数执行器”。

9. **Agent 使用真实 LangChain + LangGraph 工程。**
   LangChain 负责模型、动态 Prompt/Tool、结构化输出和 Agent Loop；LangGraph 负责
   Plan 状态图、checkpoint、并行、流式、重试和人工恢复。旧关键词分支必须退出生产
   主路径；简单请求使用相同 Plan/Event/Result 契约的确定性 Fast Plan。

---

## 2. 当前基线与必须修复的问题

### 2.1 已有能力应保留

- 来源库已经支持 RSS 与 GitHub Releases，且有启停入口；
- 手动采集和 Agent 已经共用 `collection.run.start` Capability；
- 采集链路已经具备规范化、确定性去重、结构化分析和部分失败记录；
- 时间线已经支持基础搜索、来源类型、颜色筛选和日期分组；
- 审核已经支持保留、拒绝、延后和内容修订；
- 卡片已经具备日期 Tab、月份选择、筛选、封面和详情面板；
- Agent 对话已经落库，适合作为任务创建和解释入口；
- 设计令牌、主题切换、Tabler Outline 图标和可收缩导航已有基础。

这些能力应通过重组形成产品闭环，不应推倒重写。

### 2.2 当前业务断点

| 问题 | 当前表现 | 目标状态 |
|---|---|---|
| 方案字段未真正执行 | `prompt`、`time_range_hours`、`topics` 已保存，但调度器只传 `source_ids` | 手动、定时、Agent 运行均从同一任务版本解析完整规则 |
| 任务模型割裂 | “常用方案”和“每日定时”分别存在，且定时仅支持 daily | 前端统一为“任务”，调度只是任务的一部分 |
| Agent 草稿未闭环 | Agent 可以形成定时意图，但界面没有可靠的编辑、确认、启用流程 | Agent 输出结构化任务草稿，用户确认后调用同一保存能力 |
| 数量目标缺失 | 用户不能定义最小、目标、最大结果数 | 明确数量语义，低于最小值不造数，超过最大值稳定截断 |
| 信息难以再次找到 | 筛选只在当前页面内存在，刷新后丢失 | 查询写入 URL，可保存为视图并固定到导航 |
| 信息缺少个人状态 | 只有审核决策，没有已读、收藏、归档、笔记 | 阅读状态和审核状态分离 |
| 运行结果不可信 | 采集运行在 UI 中固定显示“已完成” | 真实展示完成、部分失败、覆盖不足、失败、取消 |
| 运行不可定位 | 缺少任务版本、逐来源结果、筛选漏斗和详情页 | `/runs/[id]` 可复盘、重试和比较版本 |
| 来源管理过薄 | 只能新增和启停，不能测试、编辑和查看健康状态 | 来源列表以健康、产量、错误和最近成功为核心 |
| 页面入口不完整 | 模型页存在但导航不可见，任务长期塞在 Agent 右栏 | 明确一级导航和设置分组 |
| Agent 只有单一当前会话 | 后端只读取最近一个活动会话，前端没有列表、新建、重命名、置顶、归档或删除 | 多会话可搜索、切换和恢复；删除默认软删除并可撤销 |
| Agent 执行反馈过弱 | 阻塞请求期间只显示“正在执行”，完成后只渲染短文案和能力状态 | 状态事件流 + 文本流；显示阶段、耗时、来源、结果引用和恢复动作 |
| 多请求被单点失败截断 | 一个 Capability 或外部依赖异常可能令整轮只剩错误 | 独立请求尽量继续，最终按“已完成 / 需处理 / 未完成”汇总 |
| 时间线会无限变长 | 固定数量读取、按日连续铺开，缺少分组折叠、游标加载和滚动恢复 | 默认聚焦近期；日期组可折叠，服务端分页，保留阅读位置 |
| 来源编辑契约不一致 | 编辑 UI 可以选择类型，但更新请求不修改 `kind`，合并后的类型与配置也未统一校验 | 新增/编辑共用模型页式对话框；后端校验完整合并对象 |
| 外观页会覆盖偏好 | 页面挂载时先用 Signal Light 写回，再异步读取本地值 | 主题运行时先恢复再持久化，进入设置页不得改变当前外观 |
| A2A 仍只有文档与示例 | Agent Card 和 OpenAPI 示例存在，但没有可运行服务与调试闭环 | 先交付最小 Agent Card、消息/任务/Artifact、流式与本地 Inspector |

### 2.3 首要正确性修复

以下问题在任何视觉重构前都应视为 P0：

- 调度器必须执行任务的时间、主题、来源、数量和质量规则；
- Agent、REST、手动按钮和调度器必须调用同一 Application Capability；
- 时间线和运行页不得把 `partial` 或 `failed` 显示成成功；
- 每次运行保存任务版本、规则快照和实际解析出的来源；
- 任务结果低于最小数量时显示“覆盖不足”，不得静默放宽条件或生成内容凑数；
- 停用来源后，所有入口都必须真实阻止采集；
- 外观运行时必须在读取持久化偏好后才允许写回，禁止页面导航触发主题重置；
- 来源更新必须对 `kind + config` 的最终合并结果做与创建相同的校验；
- Agent 即使某个独立子请求失败，也必须保存已完成动作并返回可继续操作的部分结果。

---

## 3. 成熟产品模式与本项目取舍

本节只借鉴已经验证的产品模式，不进行像素级模仿。

| 产品 | 值得借鉴的模式 | 本项目的取舍 |
|---|---|---|
| Feedly | AI Feed 用主题、来源和包含/排除条件形成自动信息流；Board 用于人工精选，两者职责分离。[AI Feeds](https://docs.feedly.com/article/807-how-to-create-ai-feeds)、[Feeds 与 Boards](https://docs.feedly.com/article/805-feeds-and-boards) | 采用“任务结果流 + 专题板”；不引入企业情报层级和庞大 AI 模型目录 |
| Inoreader | 可把搜索保存为持续更新的 Monitoring Feed；顶部栏只保留高频操作。[发现与监测](https://www.inoreader.com/blog/2026/01/discover-and-monitor-content.html) | 支持“当前搜索保存为视图/创建任务”；不拆出 Rules、Filters、Reports 等多套系统 |
| Readwise Reader | 一份扁平内容库通过可保存、可固定的 Filtered Views 组织不同场景。[Filtered Views](https://docs.readwise.io/reader/docs/faqs/filtered-views) | 统一信息事实，同一条信息可属于多个任务和视图，不复制正文 |
| Linear | Custom View 可保存和固定；筛选与显示选项分开；Peek 不离开列表查看详情。[Custom Views](https://linear.app/docs/custom-views)、[Filters](https://linear.app/docs/filters)、[Peek](https://linear.app/docs/peek) | 筛选决定“看什么”，显示设置决定“怎么看”；快捷键只做加速层 |
| Notion | 同一数据集可以有列表、表格、画廊等视图，详情可在 Side peek 打开。[视图与筛选](https://www.notion.com/help/views-filters-and-sorts) | 信息页支持时间线、紧凑列表和封面卡片；不做自由数据库和无限页面嵌套 |
| Zapier | 自然语言生成草稿、逐步测试、发布版本和运行历史相互关联。[测试步骤](https://help.zapier.com/hc/en-us/articles/18811411817741-Test-Zap-steps)、[运行历史](https://help.zapier.com/hc/en-us/articles/8496291148685-View-and-manage-your-Zap-history) | Agent 先生成结构化草稿，任务先试运行再启用；不做节点画布和通用字段映射 |
| Make | 提供引导式必要设置、人类可读调度和保留失败执行。[场景设置](https://help.make.com/scenario-settings) | 高级设置默认折叠，失败结果可恢复；不暴露执行引擎术语 |
| n8n | 失败执行可按原版本或当前版本重试，并可加载历史输入调试。[执行记录](https://docs.n8n.io/workflows/executions/all-executions/) | Run 详情提供两种明确重试方式；不呈现节点、表达式或 Credential 映射 |
| Codex | 稳定左侧导航、聚焦任务主区、持久对话和按需执行细节形成连续工作上下文。[Codex App](https://openai.com/index/introducing-the-codex-app/) | Agent 对话和任务互相引用，但不扩展成多 Agent 通用编排平台 |
| ChatGPT / Claude | 对话历史支持搜索、重命名、归档与删除；旧对话不必一次性装入侧栏。[ChatGPT 历史搜索](https://help.openai.com/en/articles/10056348)、[ChatGPT 归档与删除](https://help.openai.com/en/articles/8809935-how-to-delete-and-archive-chats-in-chatgpt)、[Claude 会话管理](https://support.anthropic.com/en/articles/8230524-how-can-i-delete-or-rename-a-conversation) | 采用最近会话 + 搜索 + 归档 + 软删除；不引入账号同步和团队项目 |
| ChatGPT Deep Research | 研究前可检查计划，运行中展示进度，最终输出结构化结果与来源。[Deep Research](https://help.openai.com/en/articles/10500283-deep-research-daq) | 信息采集显示可验证阶段和来源；不显示隐藏思维链 |
| GitHub Copilot Agents | 会话可持续运行并显示实时日志、会话时长、停止、归档与后续引导。[Agent sessions](https://docs.github.com/en/enterprise-cloud@latest/copilot/how-tos/copilot-on-github/use-copilot-agents/manage-and-track-agents) | 对话正文与执行详情分层；不同会话可后台运行，同一会话首版只允许一个活动 Turn |
| A2A | 协议把 Message、Task、状态事件和 Artifact 分开，并原生支持长任务与流式更新。[A2A 1.0 规范](https://github.com/a2aproject/A2A/blob/main/docs/specification.md) | 状态用事件、最终业务结果用受控 Artifact；不把外部 Agent 输入视为可信内容 |

### 3.1 明确不照搬

- 不做拖拽 DAG、任意节点、分支和循环；
- 不做账号、登录、多工作区、团队共享、RBAC 和计费；
- 不做插件市场或通用 Connector SDK；
- 不要求普通用户编写 Cron、正则、脚本或布尔表达式；
- 不引入企业级情报术语和多层治理；
- 不用不透明数字分数代替可理解的颜色、标签和原因；
- 不为了“可配置”允许用户任意创建数据库字段或页面结构。

---

## 4. 目标业务对象与数据归属

### 4.1 核心对象

```text
Source
  └─ SourceVersion（不含密钥的不可变来源配置）
       └─ 在 Run 开始时解析并锁定

CollectionTask
  ├─ TaskDraft（可恢复的编辑草稿）
  ├─ CollectionTaskVersion（不可变规则快照）
  ├─ Schedule（可选）
  ├─ SavedView（任务结果视图）
  └─ CollectionRun
       ├─ SourceRunResult
       └─ CollectionRunItem ── IntelligenceItem

IntelligenceItem
  ├─ WorkspaceItemState
  ├─ ReviewDecision
  ├─ BoardItem
  └─ Card

Conversation
  ├─ TaskDraft
  ├─ CapabilityInvocation
  └─ CollectionRun
```

### 4.2 一份信息事实，多种关系

`IntelligenceItem` 是规范化后的唯一信息事实。任务不复制正文，只通过
`CollectionRunItem` 记录：

- 哪个任务和运行发现了它；
- 是否被选入；
- 被排除、去重或聚类的原因；
- 排序位置；
- 主来源和相关来源；
- 命中哪些主题或规则。

这样一条 OpenAI 发布信息可以同时出现在“Agent 更新”和“模型发布”两个任务视图，
但数据库只保留一份规范化事实。

### 4.3 三组状态必须分离

| 状态轴 | 推荐值 | 用途 |
|---|---|---|
| 阅读状态 | 未查看、已查看、稍后、已归档 | 个人信息管理 |
| 处理状态 | 未审核、保留、拒绝、延后 | 内容决策和后续生成 |
| 产物状态 | 无、卡片草稿、已生成 | 卡片/海报流程 |

“已查看”不等于“保留”，“归档”也不等于“拒绝”。避免一个状态字段承担多个业务含义。

### 4.4 人工专题板

新增 `Board` / `BoardItem` 作为人工精选层：

- 用户明确收藏或保留的信息才能进入专题板；
- 专题板支持排序、短笔记、导出和生成卡片；
- 自动任务不能直接把所有结果标记为精选；
- 第一版可以先用“收藏 + 专题名”实现，不需要复杂看板协作。

---

## 5. 目标信息架构与路由

### 5.1 一级导航

| 入口 | 路由 | 用户问题 |
|---|---|---|
| AI 信息 | `/timeline` | 最近发生了什么，我要找哪条信息？ |
| 待处理 | `/inbox` | 哪些信息、异常或 Agent 动作需要我处理？ |
| 专题板 | `/boards` | 我已经选出的重要内容在哪里？ |
| 卡片 | `/cards` | 已整理的可浏览信息卡片和封面在哪里？ |
| 任务 | `/tasks` | 系统正在替我追踪什么，规则和计划是什么？ |
| Agent | `/agent` | 我如何用对话创建任务、研究和处理信息？ |
| 运行记录 | `/runs` | 某次任务发生了什么，为什么失败或数量不足？ |

“审核”作为待处理中的一个稳定视图存在，并保留 `/review` 兼容路由。若首个增量不实现
统一待处理页，可暂时保留“审核”一级入口，待异常、审批和提醒合并后再迁移。

### 5.2 设置导航

| 设置 | 路由 | 内容 |
|---|---|---|
| 信息源 | `/settings/sources` | 来源、健康状态、测试、限额、启停 |
| 模型与 Agent | `/settings/models`、`/settings/agent` | 模型路由、Agent Pack、能力开关 |
| 外观 | `/settings/appearance` | 主题、令牌、密度、封面模板 |
| 系统与数据 | `/settings/system` | 本地目录、备份、导入导出、版本和诊断 |
| 互操作与调试 | `/settings/interoperability` | A2A Agent Card、能力策略、协议自检和本地调用 |

本软件不出现登录、注册、账号套餐、团队邀请或用户头像菜单。底部可以显示“本地工作区”
和服务状态，但不能伪装成账户入口。

### 5.3 收藏区

左侧导航在主入口下提供一个可折叠“收藏”区，可固定：

- 任务；
- 专题板；
- 保存视图。

收藏支持拖动排序和移除固定，但不改变对象本身。左栏收缩为图标时，收藏区隐藏，
通过命令面板或对应页面访问。

### 5.4 不增加首页仪表盘

启动后直接进入用户上次使用的主视图，默认是“AI 信息 · 今天”。不创建一个只展示
统计数字、欢迎语和快捷卡片的首页。状态摘要应出现在真正能采取行动的页面中。

---

## 6. 全局页面框架

### 6.1 框架结构

```text
┌──────────────┬──────────────────────────────────────────┬──────────────┐
│ 全局导航      │ 页面顶栏                                  │ 按需详情      │
│ 主入口        ├──────────────────────────────────────────┤ 元数据        │
│ 收藏          │ 页面局部导航 / 日期 / 保存视图              │ 运行 / 预览    │
│ 设置          ├──────────────────────────────────────────┤ 可完全关闭     │
│ 可收成图标栏   │ 主工作区                                  │              │
└──────────────┴──────────────────────────────────────────┴──────────────┘
```

三列是可用能力，不是每页固定模板：

- 时间线、专题板和运行页适合“列表 + 按需详情”；
- 任务编辑适合“表单 + 预览摘要”；
- Agent 使用“会话工作栏 + 对话主区”，运行/任务详情按需打开；会话工作栏不是新的
  全局导航，在较窄窗口中必须变为抽屉；
- 外观设置适合单主区加实时预览；
- 来源页适合列表加统一实体编辑对话框，新增和编辑复用模型页已验证的 Modal 模式；
- 审核页可以保留专用队列、内容和决策检查器布局。

### 6.2 顶栏

顶栏保持单行稳定，只承载高频操作：

- 左：页面名称、当前视图或面包屑；
- 中：当前页面搜索；
- 右：筛选、显示设置、页面主动作；
- 排序、密度、分组、字段显示进入“显示设置”；
- 主动作每页最多一个高强调按钮；
- 状态文案必须真实，例如“部分来源失败”，不能统一写“采集已完成”。

### 6.3 筛选面板

- 默认以按钮打开，不永久占用宽栏；
- 桌面宽屏可由用户固定到左侧或右侧；
- 可完全收起并记住页面级偏好；
- 收起后已生效条件以筛选标签显示；
- “清除全部”只清查询条件，不重置显示密度等偏好；
- 条件较少时直接用弹出面板，较复杂时使用 280–320px 抽屉。

### 6.4 详情 Peek

- 点击列表项后在右侧打开详情，主列表保持可交互；
- 支持上一条/下一条；
- 详情栏可完全关闭，关闭后主区回收空间；
- 可将详情升级为完整页面，URL 保留 item ID；
- 面板宽度由令牌控制，用户可在合理范围内拖动；
- 不用多个弹窗层叠完成连续任务。

---

## 7. 可配置任务设计

### 7.1 用户心智

```text
我想追踪什么
→ 从哪里找
→ 什么算匹配
→ 需要多少
→ 何时运行
→ 结果放到哪里
→ 每次发生了什么
```

前端统一称为“任务”。后端可以在迁移期保留 `CommonPlanModel` 和
`ScheduledTaskModel`，但不能让这两个技术对象继续成为两套用户概念。

### 7.2 创建路径

提供三种入口，最终都生成同一 `TaskDraft`：

1. 在任务页点击“新建任务”；
2. 在当前搜索或筛选结果中点击“保存为任务”；
3. 在 Agent 中用自然语言描述目标。

创建流程不做冗长向导，采用一页分组表单：

1. 目标与来源；
2. 匹配、时间和质量；
3. 数量与去重；
4. 计划与交付。

右侧显示“任务摘要 + 即时预览”。窄窗口时，预览变为可展开底部面板。

### 7.3 基础字段

| 字段 | 规则 | 推荐默认 |
|---|---|---|
| 名称 | 1–160 字；Agent 可建议但用户可改 | 根据目标生成 |
| 目标 | 自然语言描述，1–500 字 | 必填 |
| 来源 | 指定来源、来源组或全部已启用来源 | 必须解析出至少一个有效来源 |
| 时间范围 | 1–720 小时或“自上次成功运行后” | 24 小时 |
| 主题 | 结构化标签 | 可空 |
| 最小数量 | 软目标 | 5 |
| 目标数量 | 期望结果量 | 10 |
| 最大数量 | 最终硬上限 | 30 |
| 摘要长度 | 100–1000 字 | 400 字 |
| 计划 | 手动、每 N 小时、每天、工作日、每周 | 仅手动 |
| 状态 | 草稿、启用、暂停、归档 | 草稿 |

### 7.4 来源范围

```yaml
sources:
  mode: selected                # selected | all_enabled
  include_ids: []
  exclude_ids: []
  required_ids: []
  fallback_ids: []
  per_source_max_items: 20
```

规则：

- 来源是工作区公共资产，任务只引用 ID，不复制 URL 或密钥；
- “全部已启用来源”在运行开始时解析为明确 ID，并写入运行快照；
- 必选来源失败必须显示警告；
- 备用来源只有用户明确启用兜底策略时才参与；
- 来源选择器显示类型、健康状态和最后成功时间；
- 第一版不建设任意来源规则引擎。

### 7.5 匹配规则

```yaml
matching:
  topics: ["Agent", "AI Coding"]
  include_any: ["coding agent", "代码智能体"]
  include_all: []
  exclude: ["招聘", "课程促销"]
  search_scope: title_and_content
  languages: ["zh", "en"]
```

普通模式用自然语言标签呈现：

- 包含任意一个；
- 必须同时包含；
- 排除这些内容。

标题/全文范围、语言、精确短语等放进高级设置。后端保存结构化字段，不能把一段
Prompt 作为唯一规则。

### 7.6 时间范围

```yaml
time_window:
  mode: rolling
  lookback_hours: 24
  overlap_hours: 2
  timezone: Asia/Shanghai
```

- 定时任务默认使用滚动窗口；
- 手动一次性运行可以选择绝对日期；
- 默认保留少量重叠，由跨运行去重消除重复，避免调度延迟造成空档；
- 时间锚点、时区和最终起止时间写入 Run；
- “自上次成功运行后”不能把失败运行当作新锚点。

### 7.7 数量语义

```yaml
quantity:
  min_items: 5
  target_items: 10
  max_items: 30
  minimum_shortfall_policy: complete_with_warning
  overflow_policy: keep_best
```

必须满足：

- `0 <= min_items <= target_items <= max_items <= 500`；
- `max_items` 是时间、匹配、质量、去重和排序之后的最终结果硬上限；
- 超过上限时稳定保留最合适的 N 条，并记录“因上限排除 X 条”；
- 低于最小值时绝不编造、复制或静默降低质量；
- 默认仍交付已有结果，`coverage_status` 为 `insufficient`；
- 第一版可选短缺策略仅提供：
  - 按现状完成并提示；
  - 只扩大一次时间窗口；
- 两种策略都保持真实的 `execution_status`，并以
  `coverage_status=insufficient` 表达数量不足；
- 扩大时间或启用备用来源必须由用户明确选择；
- 不自动放宽关键词、来源可信度或质量要求。

### 7.8 重要程度与质量要求

“重要程度”表示用户是否应优先查看，“质量”表示信息是否具备足够证据。两者必须分开。
界面不显示 `92/100` 一类分数；重要程度只显示颜色、短标签和一条原因：

| 等级 | 颜色令牌 | 含义 |
|---|---|---|
| 重要 | `--signal-critical` | 需要优先查看 |
| 关注 | `--signal-watch` | 值得留意 |
| 常规 | `--signal-routine` | 可按需浏览 |
| 未判断 | `--signal-muted` | 尚未完成分析 |

业务字段使用 `importance_level: important | watch | routine | unknown`，颜色只是该语义的
主题映射，不能成为 API 字段或业务筛选值。颜色也不能成为唯一信息载体，必须同时显示
文字或图标。内部排序可以使用确定性权重，但用户不需要看到不透明的数字。

```yaml
importance:
  accepted_levels: ["important", "watch"]

quality_requirements:
  require_source_link: true
  prefer_primary_source: true
  allow_unknown_publish_time: false
  require_extractable_content: true
```

官方原始来源优先成为主证据，重复报道作为相关来源保留，不物理删除。

### 7.9 去重与聚类

```yaml
deduplication:
  mode: balanced
  window_days: 31
  across_runs: true
  preserve_related_sources: true
```

提供三种人类可理解的模式：

- 保守：URL、明确版本号、完全相同标题；
- 平衡：默认，加入标题近似和正文指纹；
- 聚合同一事件：把相似报道组成事件簇。

不向普通用户暴露相似度数字。任何被合并信息都能在详情中展开，并显示合并原因。

### 7.10 调度

第一版提供：

- 仅手动；
- 每 N 小时；
- 每天；
- 工作日；
- 每周指定日期。

不向普通用户显示 Cron。默认策略：

- 同一任务最多一个正在运行的实例；
- 前一次未结束时跳过本次并记录原因；
- 软件离线期间错过多次时，只补最近一次；
- 采集频率和通知频率分开；
- 编辑后只影响后续 Run，不修改历史；
- 下一次运行时间在保存前即可预览。

### 7.11 失败策略

```yaml
failure:
  retry_attempts: 2
  continue_on_source_error: true
  overlapping_run_policy: skip
  missed_schedule_policy: latest_only
```

运行结果使用两条正交状态轴，避免“一次运行既有来源失败又数量不足”时丢失事实：

```yaml
execution_status: queued | running | completed | partial | failed | cancelled | skipped
coverage_status: unknown | met | insufficient
```

- `execution_status` 描述执行是否完成以及来源是否完整；
- `coverage_status` 只描述最终数量是否达到 `min_items`；
- 两者可以组合，例如 `partial + insufficient`；
- `warning_codes` 保存必选来源失败、数量不足等可解释事实；
- UI 根据组合生成短文案，不把覆盖不足伪装成执行失败。

用户看到的基础文案为：

- 运行中；
- 已完成；
- 部分完成；
- 覆盖不足；
- 失败；
- 已取消；
- 已跳过。

单一来源失败时，默认保留其他来源结果并标记“部分完成”。错误必须包含来源、阶段、
稳定错误码、尝试次数和是否可重试。

### 7.12 交付

第一版只实现：

- 写入任务专属结果视图；
- 写入统一 AI 信息库；
- 应用内通知；
- 可生成 Markdown 摘要。

通知条件：

- 每次完成；
- 仅出现“重要”信息；
- 覆盖不足；
- 部分完成或失败；
- 不通知。

邮件、Webhook 等外部交付等真实需求出现后再增加。所有外部副作用必须使用幂等键。

### 7.13 预览与试运行

任务编辑器同时提供两种预览。

**即时预览**

- 使用信息库已有数据；
- 不访问外部网络；
- 不写正式信息、不发送通知；
- 返回筛选漏斗和 3–5 条样例；
- 即时提示条件过窄或过宽。

```text
已有候选 86
→ 时间范围内 51
→ 主题匹配 23
→ 质量通过 17
→ 去重后 12
→ 最终输出 12
```

**真实试运行**

- 使用尚未保存的表单配置访问真实来源；
- 不写正式时间线、不产生审核批次、不发送通知；
- 保存一条 `test` 类型运行记录；
- 代表样例写入有限期 `PreviewCandidateSnapshot`，不创建正式
  `IntelligenceItem` 或 `CollectionRunItem`；
- 快照只保留标题、URL、时间、来源、命中/排除原因等必要字段，并按保留策略过期；
- 展示逐来源连接状态、耗时和数量；
- 用户点击“应用设置”后才创建正式新版本。

Agent 可以解释预览并建议字段变化，但不能自动放宽条件。

### 7.14 草稿与版本

- 表单编辑期间写入可恢复的 `TaskDraft`，只保存草稿不会影响调度；
- `TaskDraft` 记录 `conversation_id`、`task_id`、`base_version_id`、确认状态和编辑配置；
- “应用设置”创建不可变新版本，并原子更新 `latest_version_id`；
- 启用任务时由 `active_version_id` 指定调度器实际使用的版本；
- 已启用任务编辑后，“保存草稿”不切换 `active_version_id`；只有“应用版本”才切换；
- 历史 Run 永远指向当时版本；
- 恢复旧版是“基于旧配置创建新版本”，不是覆写历史；
- Run 详情显示版本号和字段差异；
- Run 开始时锁定实际使用的 `SourceVersion`，其中不包含密钥；
- 密钥只通过版本化凭据引用解析，快照和日志不得包含密钥值；
- “按原配置重试”需要原任务版本、来源版本和兼容的 Adapter 均可用；否则按钮禁用并说明原因；
- 重试必须明确选择“按原配置”或“按当前配置”。

---

## 8. 信息管理与查找

### 8.1 查询能力

时间线查询应逐步支持：

- 全文关键词；
- 具体来源多选和来源组；
- 主题多选；
- 日期范围；
- 任务；
- 重要程度（查询字段为 `importance_level`，颜色仅由主题映射）；
- 阅读状态；
- 处理状态；
- 是否有封面、卡片或笔记；
- 排序；
- 游标分页。

普通筛选以可编辑标签显示；高级筛选支持有限的 AND/OR 分组，但不要求用户写查询语言。

### 8.2 URL 与保存视图

- 查询、排序、分组和选中项写入 URL；
- 刷新、返回和复制链接后保持当前上下文；
- 当前查询可保存为 `SavedView`；
- 视图支持重命名、复制、删除、设为默认和固定到左栏；
- 同一视图保存“显示什么”和“如何显示”，但两类设置在 UI 中分开编辑；
- 删除视图不会删除任何信息。

### 8.3 全局搜索与命令面板

全局搜索可以查找：

- 信息标题、摘要、主题和来源；
- 任务；
- 专题板；
- Agent 对话；
- 运行 ID。

命令面板提供当前上下文动作，例如：

- 新建任务；
- 保存当前视图；
- 立即运行当前任务；
- 标记已读/收藏/归档；
- 打开运行详情；
- 切换主题或显示密度。

快捷键是加速方式，不是唯一入口。

### 8.4 空结果

空状态必须回答“为什么为空”和“下一步做什么”：

- 没有采集过：引导配置来源或运行任务；
- 条件无匹配：显示当前筛选并提供逐个移除；
- 全部是重复项：显示去重数量和查看合并结果入口；
- 覆盖不足：显示目标、实际和可选调整；
- 来源失败：显示失败来源和测试连接入口；
- 服务未启动：显示本地服务状态和启动说明。

---

## 9. 关键页面设计

### 9.1 AI 信息 `/timeline`

页面目标：快速扫描、找到、保存和进入后续处理。

顶栏：

- 当前保存视图；
- 局部搜索；
- 筛选；
- 显示设置；
- “立即采集”或当前任务的“运行一次”。

第二行：

- 可横向滚动的日期 Tab；
- 最右侧月份选择；
- “今天、未查看、收藏、全部”等快捷视图；
- 生效的筛选标签。

主区支持三种显示：

- 时间线：适合按日期连续浏览；
- 紧凑列表：适合高密度筛选；
- 封面卡片：适合视觉浏览和卡片内容。

信息项只显示：

- 颜色状态；
- 来源与发布时间；
- 标题；
- 一到两行摘要；
- 少量主题；
- 收藏/更多操作。

点击后打开右侧 Peek，详情包含：

- 封面、标题、来源、原文链接；
- 100–1000 字的整理摘要；
- 命中任务、主题和原因；
- 相关来源和去重信息；
- 已读、收藏、归档、加入审核、加入专题、生成卡片；
- 围绕当前信息继续向 Agent 提问。

#### 长时间线治理

信息增长后不能只靠“整页继续向下滚动”，也不能把所有历史默认折叠到用户无法发现。
采用“聚焦视图 + 日期分组 + 游标分页 + 可恢复位置”的组合：

- 默认进入“今天”或用户上次保存视图，不默认加载全部历史；
- 今天和最近一个有内容的日期默认展开，更早日期按月/日折叠；
- 日期标题是可访问按钮，显示总数、未读数和重要信息数；
- 提供“展开本月”“折叠较早日期”，不提供会造成巨大 DOM 的无限“全部展开”；
- 折叠状态按 `saved_view_id + date_group` 保存，切换视图后各自恢复；
- 搜索或定位 `focus` 信息时自动展开命中日期，但不永久改写用户偏好；
- 使用服务端游标或稳定分页，每批建议 30–60 条；前端可做窗口化渲染，但不能以
  虚拟列表代替后端分页；
- 用户阅读旧内容时，新数据不直接插到顶部导致跳动，显示“有 N 条新信息”按钮；
- 从详情、卡片或 Agent 返回时恢复保存视图、展开状态和滚动锚点；
- 已读隐藏、归档和保存视图用于减少日常噪声，均不物理删除信息事实。

Agent 的信息引用统一跳转：

```text
/timeline?focus=<information_id>&run=<run_id>&from=agent&conversation=<conversation_id>
```

页面收到参数后展开对应日期、滚动并短暂高亮条目、打开 Peek，同时提供“返回对话”。

### 9.2 待处理 `/inbox`

统一承载需要用户动作的事项：

- 待审核信息；
- Agent 请求确认的任务草稿或副作用；
- 部分完成、覆盖不足和失败运行；
- 来源连续异常；
- 延后到期的信息。

按类型和日期分组，默认只显示未处理项。每个条目提供一个明确主动作和最多两个次要
动作。第一阶段可以由现有 `/review` 逐步迁移，不阻塞任务闭环。

### 9.3 专题板 `/boards`

页面目标：管理人工精选而不是再次浏览所有自动结果。

- 左侧或顶部选择专题；
- 主区支持封面卡片和紧凑列表；
- 支持手动排序、短笔记和批量生成卡片；
- 同一信息可进入多个专题；
- 原始链接和任务来源始终可追溯；
- 删除专题只删除关系，不删除信息。

### 9.4 任务列表 `/tasks`

每行只展示：

- 名称；
- 启用、暂停或异常状态；
- 来源数量和时间范围；
- 计划摘要；
- 上次结果数量；
- 上次和下次运行时间；
- 来源异常提示。

主操作：

- 立即运行；
- 暂停/启用；
- 编辑；
- 查看结果；
- 查看运行记录。

支持按名称、状态、主题、来源和异常筛选。任务可以复制和归档，默认不物理删除。

### 9.5 任务详情与编辑 `/tasks/[id]`

顶部提供“概览、规则、计划、运行、版本”。

编辑模式使用单页分组表单，右侧常驻任务摘要和预览：

```text
┌──────────────────────────────┬──────────────────────┐
│ 目标与来源                    │ 任务摘要              │
│ 匹配、时间与质量              │ 下次运行              │
│ 数量与去重                    │ 预计结果 / 筛选漏斗     │
│ 计划与交付                    │ 代表样例              │
├──────────────────────────────┴──────────────────────┤
│ 取消        保存草稿        试运行        保存并启用   │
└─────────────────────────────────────────────────────┘
```

滑块必须同时提供数字输入和可访问名称；不要仅靠拖动精确设置数量或摘要长度。

### 9.6 Agent `/agent`

#### 页面框架

Agent 不是单一、无限增长的聊天框。默认结构：

- 会话工作栏：新建、搜索、切换和管理对话；
- 主区：当前对话、结构化结果与稳定 Composer；
- 右侧：只在需要时显示当前任务草稿、运行、审批或信息上下文；
- 顶栏只保留当前标题、会话动作、运行状态和“任务控制”入口。

会话工作栏按“置顶、今天、最近 7 天、更早”分组。每行展示标题、最后更新时间和
执行中/未读/警告状态，行级菜单提供：

- 重命名；
- 置顶/取消置顶；
- 归档/恢复；
- 删除；
- 打开关联任务或最近运行。

标题在首轮完成后可根据第一条用户消息生成；用户手动重命名后不再自动覆盖。删除默认
设置 `deleted_at` 并立即从活动列表隐藏，同时提供撤销；物理删除只在“系统与数据”
中显式确认。不同会话可以后台执行；同一会话第一阶段只允许一个活动 Turn。

#### 执行过程与耗时

执行过程同时有两条投影：

1. 状态事件流：理解请求、读取来源、筛选、去重、保存信息、生成答复；
2. 答复内容流：自然语言和受控结构化结果块。

推荐事件：

```text
turn.started
step.started
step.progress
step.completed | step.failed | step.skipped
assistant.delta
result.block.created
turn.completed | turn.completed_with_warnings | turn.failed
```

- 发送后立即创建持久 `AgentTurn` 并返回 Turn ID；
- SSE 事件带顺序号，断线后用 `Last-Event-ID` 续传；最终消息和结果块以数据库为事实
  来源，不能依赖流永久保存；
- 执行中显示实时计时，例如“正在读取 4 个来源 · 12 秒”；
- 完成后显示服务端计算的总耗时；排队、首事件、各步骤耗时在展开详情中显示；
- 只有模型 Provider 真正提供 delta 时才逐段显示文本，不用打字动画伪造流式；
- 用户向上阅读时不强制滚到底部，显示“有新进展”按钮；
- 提供停止当前 Turn；首版的“追加要求”在当前能力步骤结束后生效；
- 不显示隐藏思维链、原始 Prompt、密钥或无约束工具 JSON。

#### 信息收集结果

不能只回复“新增 40 条”。成功或部分成功的收集答复由受控组件构成：

```text
✓ 收集完成 · 18 秒
40 条 AI 信息 · 6/7 个来源成功 · 3 条重要

来源覆盖
OpenAI 12  LangChain 8  GitHub 20
Hugging Face：连接超时                         [重试来源]

重点 AI 信息
● 重要 · OpenAI 官方
标题
一到两行快速摘要
[查看 AI 信息]

[查看本次全部 40 条] [只看重要] [打开运行详情]
```

允许的结果块首版限定为：

- `collection_summary`；
- `source_coverage`；
- `signal_preview`；
- `task_draft`；
- `warning_notice`；
- `error_notice`；
- `action_group`。

`signal_preview` 由后端返回信息 ID、标题、来源、颜色语义、简短摘要、发布时间和应用
路径。每次默认展示 3–5 条代表性信息，不复制完整正文。Web 端只映射白名单组件，
不执行模型生成的 HTML、脚本或任意路由。点击“查看 AI 信息”使用 9.1 的深链并打开
对应 Peek。

#### 多请求与错误语义

用户一次提出多个请求时，Agent 先形成最多 5 个有依赖关系的 `TurnStep`：

- 独立步骤默认 `continue_on_error=true`；
- 只有依赖失败的步骤标记 `skipped`；
- 某个来源、模型或 Capability 失败不抹去已经完成的结果；
- 仅在用户明确要求原子操作，或不可缺少的前置条件失败时停止依赖链；
- 最终答复固定汇总“已完成、需要你处理、未完成”，并提供重试或修正动作。

错误必须标记来源，而不是把所有问题都写成“用户错误”：

| `origin` | 示例 | UI |
|---|---|---|
| `input` | 数量上下限冲突、缺少目标 | 黄色“需要补充/调整”，定位字段 |
| `business` | 任务暂停、来源被停用 | 黄色说明和编辑入口 |
| `provider` | RSS 超时、模型限流 | 局部警告，保留其他结果并提供重试 |
| `capability` | 能力开关关闭、审批未通过 | 独立能力状态和可采取动作 |
| `system` | 数据库或事件流损坏 | 红色错误、请求 ID 和运行记录入口 |

快捷动作仍包括：

- 用当前对话创建任务；
- 把当前筛选保存为任务；
- 先试运行，不保存；
- 修改来源、时间、最小/最大数量；
- 设置或暂停计划；
- 只重试上次失败来源；
- 解释为什么某条信息被选中或排除。

Agent 返回的任务草稿必须是可编辑结构化组件。涉及启用计划、外部交付、覆盖长期记忆
或物理删除时需要显式确认。

### 9.7 运行记录 `/runs`

列表支持按任务、触发方式、日期和状态筛选。每行展示：

- 任务与版本；
- 手动、计划、Agent、测试或重试触发；
- 状态；
- 开始/耗时；
- 最终数量；
- 失败来源数量；
- 与父 Run 的关系。

详情 `/runs/[id]`：

```text
候选抓取 86
→ 时间过滤 51
→ 规则匹配 23
→ 质量通过 17
→ 去重后 12
→ 最终选入 10
```

同时展示：

- 任务规则快照；
- 逐来源 fetched / matched / duplicate / selected / error；
- 稳定错误码和重试建议；
- Capability Invocation；
- 结果样例和排除原因；
- “按原版本重试”与“按当前版本重试”；
- 返回任务结果和相关 Agent 对话。

### 9.8 信息源 `/settings/sources`

列表优先显示：

- 名称和类型；
- 健康颜色与文字；
- 最后成功；
- 最近产量；
- 连续错误；
- 被多少任务使用；
- 启用状态。

新增或编辑使用与“添加模型”同等级的模态对话框，不再把表单铺在列表顶部。新增与
编辑复用同一个 `EntityFormDialog` 的焦点、Esc、未保存保护和页脚结构，但字段由来源
Schema 决定：

- 名称、类型、地址；
- 单次上限；
- 超时和更新频率；
- 启用状态；
- “测试连接”与“保存”；
- 测试样例；
- 可操作错误说明。

新增来源的“测试连接”必须接受尚未保存的完整定义，不能为了测试先制造一条来源或
Collection Run。编辑已有来源时，来源类型首版设为只读；需要更换类型时提供“复制为
新来源”，避免破坏历史 Run 的来源版本关系。

后端保存规则：

- 创建与编辑都对最终 `kind + config` 完整对象执行 Adapter 专用校验；
- Patch 先与现有值合并再校验，不能用空配置破坏来源；
- 重名稳定返回 `SOURCE_NAME_EXISTS`，不能泄漏数据库异常；
- URL、`owner/repo`、限额和超时先规范化再保存；
- Python 异常类名不能直接作为用户错误码；
- 测试 A 来源时不能禁用其他来源行的操作。

停用前提示受影响任务；默认软删除或归档。凭据不进入任务快照和前端日志。

### 9.9 卡片 `/cards` 与 `/cards/[id]`

保留已有方向：

- 顶部日期 Tab 和月份选择；
- 左侧筛选可完全收起；
- 瀑布流/网格展示简单封面和标题；
- 点击在右侧显示封面、标题、整理内容和原文跳转；
- 摘要默认 400 字，可设置 100–1000 字；
- 优先原始合适封面，否则使用六种浅青蓝 HTML/CSS 模板；
- 不使用默认图片库兜底，不依赖生图模型；
- 卡片必须显示它来自哪条信息和哪个任务。

完整详情页 `/cards/[id]` 用于：

- 修改标题、摘要和原文跳转；
- 选择或调整 HTML/CSS 封面模板；
- 保存草稿和查看生成来源；
- 在 HTML 卡片闭环稳定后增加 PNG 渲染与导出；
- 返回日期、专题或任务时恢复原筛选位置。

### 9.10 外观 `/settings/appearance`

把设计令牌分为用户能理解的组件类别：

- 色彩：强调色、信号色、表面和边框；
- 字体：字号、行高、字重；
- 密度：紧凑、标准、宽松；
- 圆角与阴影；
- 导航和详情栏宽度；
- 卡片封面模板与配色；
- 动效强度。

每个可连续调整的值使用“预设选择 + 滑块/数字输入”。提供一键主题：

- Signal Light；
- Signal Dark；
- Soft Cyan；
- Mint Desk；
- High Contrast。

主题切换、用户自定义和高对比模式都必须通过令牌生效，页面局部样式不得绕过。

主题恢复与保存由全局 `AppearanceProvider` 或等价运行时统一拥有。进入外观页时，
页面控件读取已经恢复的工作区值；在恢复完成前禁止把组件默认值写入
`localStorage`。只有用户操作或显式恢复默认值才持久化。必须覆盖以下回归：

- 从其他页面进入外观页不改变当前主题；
- 刷新时不先闪成 Signal Light；
- 非法本地值可以回退，但要在内存恢复完成后一次性写回；
- 页面卸载或 Strict Mode 重渲染不产生额外主题切换；
- 主题、圆角、密度和字号使用同一恢复门，不各自竞争写入。

### 9.11 互操作与调试 `/settings/interoperability`

该页面是 A2A 的本地产品入口，不是通用 Postman 或任意函数控制台。默认只在 loopback
或显式开发开关下可见，包含：

- Agent Card：渲染最终公开 Card、Schema 版本和真实能力；
- 发送请求：从白名单 Skill 生成安全示例请求；
- 流事件：查看状态事件、Artifact、请求 ID 和对应 Run；
- Tasks：查询、取消和回到业务页面；
- 自检：运行官方 Schema/TCK 或项目内兼容测试。

第一批 A2A Skills：

```text
collect_ai_intelligence
query_ai_timeline
prepare_card_drafts
```

协议映射：

- `contextId` 映射会话/工作上下文；
- A2A Task ID 映射 `AgentTurn` 或业务 Run；
- Message 只承载请求、补充信息和状态说明；
- 最终信息列表、卡片草稿等业务输出使用 Artifact；
- `message/stream` 使用与内置 Agent 相同的 `AgentTurnEvent`；
- Agent Card 只有实现并通过测试后才能声明 `streaming: true`；
- 外部 Agent 输入、Agent Card 与 Artifact 一律视为不可信，需校验、净化和限额。

生产 A2A Adapter 只能调用已注册 Capability，并使用 `external_agent` 策略、功能开关、
审批和幂等键。它不得访问数据库、加载内部密钥或暴露“调用任意 Python 函数”的入口。
绑定非 loopback 地址时必须要求工作区 Token 或受信任反向代理认证。

---

## 10. 视觉与组件系统

### 10.1 设计方向：Quiet Signal Desk

目的：让用户长时间扫描信息和管理任务时保持安静、清晰、可信。

- 中性浅表面为主，颜色只用于状态、选中和主要操作；
- 内容密度中高，但通过分组、间距和对齐维持可读性；
- 边框优先于重阴影；
- 不使用大面积渐变和装饰性 Hero；
- 不把每一段内容包成独立卡片；
- 标题、摘要和元数据层级明确，减少说明性长文；
- Signal Rail 作为时间线和运行阶段的识别细节，其他页面克制复用。

### 10.2 核心组件

| 类别 | 组件 |
|---|---|
| 框架 | `AppShell`、`PageTopbar`、`LocalNav`、`ContextPanel`、`PeekPanel` |
| 查找 | `GlobalSearch`、`QueryBar`、`FilterPopover`、`FilterChips`、`SavedViewTabs` |
| 信息 | `SignalRow`、`SignalCard`、`SignalDetail`、`DateGroupHeader`、`NewItemsNotice`、`StatusMark`、`SourceBadge` |
| 任务 | `TaskListRow`、`TaskEditor`、`SourcePicker`、`QuantityControl`、`ScheduleEditor` |
| 预览 | `PreviewFunnel`、`SampleResults`、`RuleSummary`、`ValidationNotice` |
| 运行 | `RunStatus`、`RunFunnel`、`SourceRunTable`、`RunErrorNotice`、`RetryMenu` |
| Agent | `ConversationList`、`ConversationRow`、`MessageBlock`、`TurnProgress`、`CapabilityBlock`、`InformationResultBlock`、`TaskDraftBlock`、`Composer` |
| 设置 | `EntityFormDialog`、`SourceForm`、`SourceTestResult`、`InteroperabilityInspector` |
| 状态 | `EmptyState`、`LoadingState`、`PartialState`、`ErrorState`、`OfflineState` |
| 外观 | `ThemePresetPicker`、`TokenSlider`、`DensityPicker`、`CoverTemplatePicker` |

### 10.3 图标

- 统一使用 Tabler Outline；
- 功能入口必须同时有图标和可见文字；
- 左栏收缩后保留图标、Tooltip 和可访问名称；
- 纯图标按钮必须有 `aria-label`；
- 不混入写实、填充、彩色或平台品牌风格图标；
- 来源品牌图标只在来源身份场景使用，不能代替功能图标。

### 10.4 动效

- 只用于面板展开、状态切换、列表插入和运行进度；
- 120–220ms；
- 支持 `prefers-reduced-motion`；
- 不使用持续漂浮、背景粒子或与任务无关的过场。

---

## 11. 动态桌面布局

本阶段不专门制作移动端，但编码必须保持动态布局。

| 宽度 | 布局策略 |
|---|---|
| `>= 1600px` | 224–240px 完整导航 + 弹性主区 + 可选 320–380px 详情；Agent 可同时显示 240–280px 会话栏 |
| `1360–1599px` | 全局导航优先收成 56–64px，Agent 保留会话栏，右侧详情改为按需抽屉 |
| `1280–1359px` | 56–64px 图标导航 + 主区；会话栏、筛选和详情按页面改为抽屉 |
| `1024–1279px` | 56–64px 图标导航 + 主区；筛选和详情改为覆盖式面板 |
| `768–1023px` | 单一主工作区；全局导航、筛选和详情均使用抽屉 |
| `< 768px` | 保证基本流程不崩溃，但不作为本阶段正式移动端验收目标 |

收缩顺序：

1. 压缩留白和非关键列；
2. 左侧全局导航收成图标；
3. 隐藏收藏区和局部辅助栏；
4. 详情栏改为覆盖式；
5. 低频操作进入菜单；
6. 主任务区保持最小可用宽度，不被两侧面板挤压。

实现优先使用 CSS Grid、Flex、`minmax()`、容器查询和令牌，不按设备型号写死页面。
Agent 在 `1024–1359px` 时，会话栏与任务详情使用互斥抽屉，Composer 和当前对话始终
留在主区。页面不能为了容纳四栏把对话压到低于 640px；也不能擅自覆盖用户保存的全局
导航收缩偏好。

---

## 12. 状态、反馈与可访问性

### 12.1 统一运行状态

`execution_status` 决定主状态，`coverage_status` 作为可同时存在的数量徽标。推荐映射：

| 执行状态 | 颜色 | 文案要求 |
|---|---|---|
| `queued/running` | 蓝 | 等待中 / 运行中 |
| `completed` | 绿 | 已完成，并显示实际数量 |
| `partial` | 黄 | 部分完成，并显示失败来源 |
| `failed` | 红 | 失败，显示可操作原因 |
| `cancelled/skipped` | 灰 | 已取消 / 已跳过，并说明原因 |

当 `coverage_status=insufficient` 时，额外显示黄色“覆盖不足：目标 X，实际 Y”；它可以
与“已完成”或“部分完成”同时出现。主状态颜色和覆盖徽标都必须配文字。

“正常完成但无新增”和“没有内容匹配”不是失败；“部分来源失败”也不能显示为完整成功。

Agent Turn 使用独立但可映射的状态：

| Turn 状态 | 含义 |
|---|---|
| `queued/running` | 已接收 / 正在执行 |
| `completed` | 所有必要步骤完成 |
| `completed_with_warnings` | 有可用结果，但存在独立步骤或来源失败 |
| `needs_user_action` | 需要补充输入、授权或确认 |
| `failed` | 没有可交付结果或关键前置失败 |
| `cancelled` | 用户停止；已经完成的外部副作用仍需如实记录 |

一个 Turn 的总状态不能覆盖各 `TurnStep` 的真实状态。UI 必须同时保留成功结果和局部
错误，不能因为最终 HTTP 响应是错误就丢弃已经保存的消息、信息或运行记录。

### 12.2 操作反馈

- 保存成功在原位置显示，不只依赖短暂 Toast；
- 长任务立即返回 Run ID，并持续更新状态；
- 乐观更新只用于可安全回滚的已读、收藏等本地状态；
- 删除、归档、拒绝等动作提供明确区别；
- 批量操作前显示数量和影响范围；
- 错误消息包含下一步，不显示原始堆栈；
- 断线后保留未提交表单和 Agent 草稿。

### 12.3 可访问性

- 所有输入有可见标签；
- 颜色与文字共同表达状态；
- 焦点顺序与视觉顺序一致；
- Peek、抽屉和弹出层正确管理焦点；
- 键盘可以完成搜索、浏览、打开详情和常用状态切换；
- 紧凑模式仍满足点击目标和文本对比度；
- 滑块必须提供键盘操作和数字输入替代。

---

## 13. Application 与 Capability 边界

### 13.1 模块职责

下表只列本蓝图直接影响的模块，不删除 `memory`、`orchestration`、`artifacts`、
`realtime_transcription`、`interoperability` 等现有边界。

| 模块 | 负责 | 不负责 |
|---|---|---|
| `tasking`（由现有 `automation` 演进） | 任务、草稿、版本、计划、启停、预览和运行入口 | 抓网页、评分、直接写 Agent 消息 |
| `collection` | 来源连接、抓取、规范化、原始候选、逐来源结果 | 用户阅读状态、任务表单 |
| `intelligence` | 匹配、重要程度、质量校验、排序、去重/聚类、最终数量上限 | 调度和外部通知 |
| `information_library` | 已读、收藏、归档、笔记、保存视图 | 审批和发布 |
| `review` | 保留、拒绝、延后和审核批次 | 个人收藏夹 |
| `cards` | 卡片生成、封面、摘要长度和导出 | 重新采集来源 |
| `agent` | 会话、消息、Turn、事件序列、结果块和会话生命周期 | 采集、审核和任务业务规则 |
| `agent_runtime` | 把自然语言转为结构化步骤/草稿，调用 Capability，汇总部分结果 | 直接访问数据库、复制业务规则、吞掉局部成功 |
| `interoperability` | REST/SSE/A2A/MCP 的 Schema 与协议适配、Agent Card、外部 Actor 策略 | 重新实现 Capability 或提供任意函数调用 |
| `observability` | Run、Invocation、错误、指标和版本关联 | 修改任务业务状态 |

若暂不新增 `information_library` 顶层目录，可先作为 `intelligence` 子模块实现，但接口
和数据所有权必须独立于 `review`。

### 13.2 最小 Capability

```text
task.query
task.save_draft
task.apply_version
task.preview
task.archive

task.run.start
task.run.query
task.run.retry
task.run.cancel

information.query
information.state.update
information.saved_view.save

source.test
source.query
source.save

agent.conversation.query
agent.conversation.create
agent.conversation.update
agent.conversation.archive
agent.turn.start
agent.turn.query
agent.turn.cancel
```

`task.run.start` 只允许两种互斥输入：

- `task_id + task_version_id`；
- 临时 `config_snapshot`，仅用于试运行或一次性 Agent 请求。

Router、Agent Tool、Scheduler 和未来 A2A/MCP Adapter 只做 Schema 适配，业务动作全部
落到 Application Service。

`AgentTurnResult` 与 `AgentTurnEvent` 是应用层契约，不属于 SSE 或 A2A。REST 最终响应、
Web SSE、内置 Agent UI 和 A2A Adapter 分别投影同一份结构；协议断线只重放事件，
不能重放业务副作用。

现有 `collection.run.start` 在迁移期保留为兼容适配器，委托给 `task.run.start` 的一次性
配置路径，不得继续维护另一套任务规则。`collection` 模块仍拥有来源抓取和候选处理，
`tasking` 拥有用户任务定义与运行编排入口。

### 13.3 幂等

- 计划运行：`task_id + scheduled_for + version_id`；
- 手动按钮：客户端提供 idempotency key；
- 失败来源重试：`parent_run_id + source_id + attempt`；
- 卡片生成：`intelligence_item_id + template_version`；
- 外部通知：`run_id + channel + policy_version`。

---

## 14. 建议数据契约

```yaml
AgentConversation:
  id:
  title:
  title_source: auto | manual
  status: active | archived | deleted
  pinned_at:
  active_turn_id:
  last_message_at:
  unread:
  created_at:
  updated_at:
  deleted_at:

AgentTurn:
  id:
  conversation_id:
  request_id:
  client_message_id:
  status: queued | running | completed | completed_with_warnings | needs_user_action | failed | cancelled
  started_at:
  first_event_at:
  completed_at:
  duration_ms:
  requested_model_id:
  effective_model_id:
  result_summary:

AgentTurnStep:
  id:
  turn_id:
  sequence:
  capability_id:
  depends_on:
  continue_on_error:
  status: queued | running | completed | failed | skipped | cancelled
  duration_ms:
  output_ref:
  error:

AgentTurnEvent:
  turn_id:
  sequence:
  kind:
  payload:
  created_at:

AgentResultBlock:
  id:
  turn_id:
  kind: collection_summary | source_coverage | signal_preview | task_draft | warning_notice | error_notice | action_group
  schema_version:
  data:
  created_at:

CollectionTask:
  id:
  name:
  goal:
  status: draft | enabled | paused | archived
  latest_version_id:
  active_version_id:
  pinned:
  created_at:
  updated_at:

TaskDraft:
  id:
  task_id:
  conversation_id:
  base_version_id:
  config:
  status: editing | confirmed | discarded
  confirmed_version_id:
  created_at:
  updated_at:

CollectionTaskVersion:
  id:
  task_id:
  version_number:
  schema_version:
  config_snapshot:
  config_hash:
  change_note:
  created_at:

SourceVersion:
  id:
  source_id:
  version_number:
  adapter_type:
  adapter_version:
  config_snapshot_sanitized:
  credential_ref_version:
  config_hash:
  created_at:

CollectionRun:
  id:
  task_id:
  task_version_id:
  trigger_type: manual | schedule | agent | test | retry
  execution_status: queued | running | completed | partial | failed | cancelled | skipped
  coverage_status: unknown | met | insufficient
  time_anchor:
  resolved_source_version_ids:
  funnel_counts:
  warning_codes:
  errors:
  parent_run_id:
  capability_invocation_id:
  started_at:
  completed_at:

SourceRunResult:
  run_id:
  source_id:
  source_version_id:
  status:
  fetched_count:
  matched_count:
  duplicate_count:
  selected_count:
  attempts:
  error_code:

PreviewCandidateSnapshot:
  id:
  run_id:
  source_id:
  title:
  url:
  published_at:
  decision:
  reason_code:
  expires_at:

CollectionRunItem:
  run_id:
  intelligence_item_id:
  decision: included | excluded | duplicate
  reason_code:
  matched_rules:
  rank:
  cluster_id:
  is_primary:

WorkspaceItemState:
  intelligence_item_id:
  seen_at:
  snoozed_until:
  starred:
  archived_at:
  note:

SavedView:
  id:
  name:
  query:
  display:
  pinned:
  is_default:
```

`AgentResultBlock.data` 必须按 `kind + schema_version` 通过后端 Schema 校验。信息引用的
最小结构：

```yaml
InformationPreview:
  id:
  title:
  summary:
  source_name:
  priority:
  published_at:
  app_path:
  canonical_url:

AgentError:
  origin: input | business | provider | capability | system
  code:
  message:
  recoverable:
  suggested_action:
  request_id:
```

建议稳定错误码：

```text
TASK_ITEMS_RANGE_INVALID
TASK_NO_ENABLED_SOURCE
TASK_SOURCE_REQUIRED_FAILED
TASK_MIN_ITEMS_NOT_MET
TASK_ALREADY_RUNNING
TASK_VERSION_NOT_FOUND
SOURCE_CONNECTION_FAILED
SOURCE_RATE_LIMITED
SOURCE_PARSE_FAILED
RUN_RETRY_NOT_ALLOWED
AGENT_CONVERSATION_NOT_FOUND
AGENT_CONVERSATION_DELETED
AGENT_TURN_ALREADY_RUNNING
AGENT_TURN_EVENT_GAP
AGENT_STEP_PARTIAL_FAILURE
A2A_SKILL_DISABLED
A2A_INPUT_INVALID
```

---

## 15. 分阶段实施

### 阶段 A：正确的任务闭环

交付一个可用成品：

```text
创建任务
→ 配置来源/主题/时间/数量
→ 即时预览
→ 保存版本
→ 手动运行
→ 查看任务结果
→ 查看真实运行详情
```

包含：

- 新 `/tasks`；
- 任务 Schema、版本和 Capability；
- 手动运行；
- 规则真实参与采集；
- 筛选漏斗；
- 真实状态；
- Agent 创建可编辑草稿；
- 一个端到端冒烟测试。

### 阶段 B：计划、来源与恢复

- 人类可读调度；
- 来源健康与测试连接；
- 逐来源运行结果；
- 部分失败和覆盖不足；
- 按原版/当前版重试；
- 任务暂停、复制、归档；
- Agent 修改计划和重试失败来源。

### 阶段 C：信息管理与保存视图

- 全文搜索和多条件筛选；
- URL 状态；
- 保存视图和收藏区；
- 已读、稍后、收藏、归档、笔记；
- 右侧 Peek；
- 任务、专题和信息交叉跳转。

### 阶段 D：待处理、专题板与卡片整合

- 统一待处理页；
- 人工专题板；
- 审核、异常和 Agent 确认汇总；
- 从专题批量生成卡片；
- 卡片来源和任务追溯。

### 阶段 E：视觉与交互收口

视觉系统不等到最后才开始；每阶段都使用令牌和目标组件。此阶段只做整体校正：

- 所有页面顶栏和布局一致性；
- 主题预设与自定义令牌；
- 密度、面板宽度和偏好持久化；
- 1024px、1180px、1440px 桌面回归；
- 键盘、焦点、对比度和 reduced motion；
- 空、错、加载、部分完成、离线状态统一。

### 阶段 F：Agent 多会话与可观察执行

```text
新建/切换会话
→ 发出多步骤请求
→ 实时看到阶段和耗时
→ 一个步骤失败时继续独立步骤
→ 查看来源和重点 AI 信息
→ 跳回信息详情或运行记录
```

包含：

- 会话列表、新建、重命名、置顶、归档、软删除和恢复；
- `AgentTurn`、有序事件和断线恢复；
- 生命周期流式优先，真实 Provider 支持后再增加文本 delta；
- 结构化信息结果块、来源覆盖和应用内深链；
- `input/business/provider/capability/system` 错误分类；
- 多请求依赖和 `continue_on_error`；
- 后台会话状态、未读提示和停止 Turn；
- 真实消息、Turn、结果块刷新后可恢复。

### 阶段 G：长信息库与设置可靠性

- 时间线稳定游标、日期组折叠、分段加载和滚动恢复；
- 新信息提示而不抢滚动位置；
- 来源新增/编辑 Modal、草稿测试和完整合并校验；
- 来源稳定错误码、逐行测试状态和重名处理；
- 全局 Appearance Provider、恢复门和主题不回退回归测试；
- 1024px、1360px、1600px 的 Agent/时间线/设置布局验收。

### 阶段 H：完整链路真实模型验收与最终互操作

- 核心产品完整、确定性全量回归通过后，才执行一次受控真实模型完整链路；
- 单元、模块、契约、Graph 和普通 Playwright 不调用真实模型；
- 密钥不进入截图、响应、事件或日志，默认 CI 使用确定性假实现。

外部 Agent Gateway 作为产品最后阶段的独立设计项，当前不进入开发任务。未来先实现
默认关闭、本机回环、只读的 MCP 入口；存在明确长任务互操作对象后再实现 A2A Agent
Card、Task、Artifact 和 Streaming。详细边界见
[04-02 外部 Agent Gateway 设计](../04-module-poster-interop/04-02-external-agent-gateway-design.md)。

---

## 16. 简单 TDD 与验收

每个垂直增量只写 2–6 个关键测试，先保证契约和完整用户行为。

### 16.1 任务契约

1. 用户可创建、编辑、复制、启停和归档任务；
2. `min > target`、`target > max` 或无有效来源返回明确错误；
3. 手动、定时和 Agent 从同一任务版本生成等价能力输入；
4. 时间、包含/排除词、主题、重要程度、质量要求和来源均真实参与筛选；
5. 最终数量永不超过 `max_items`；
6. 低于 `min_items` 返回覆盖不足，不造数、不静默放宽。

### 16.2 运行与版本

1. 保存草稿不改变启用版本；应用版本 2 后，旧 Run 仍可读取版本 1；
2. 相同幂等键不会创建第二个 Run；
3. 一个来源失败、其他来源成功时状态为部分完成；
4. 失败来源重试不复制信息或重复通知；
5. 按原配置和按当前配置重试产生可区分的新 Run；
6. 运行详情的状态、数量和 API 原始记录一致。

### 16.3 信息查找

1. 来源、主题、日期、任务、重要程度和阅读状态筛选正确组合；
2. 查询写入 URL，刷新后结果不变；
3. 保存视图与普通查询使用同一 Query Service；
4. 已读、收藏和归档刷新后仍保留；
5. 同一信息属于多个任务时只存在一份事实；
6. 空结果展示生效条件和恢复动作。

### 16.4 Agent

1. “每天 9 点，从指定来源收集 24 小时内 Agent 信息，至少 10 条、最多 30 条”
   生成可编辑结构化草稿；
2. 用户确认前不启用任务；
3. Agent Tool 禁用时不能绕过能力开关；
4. 刷新后对话、草稿、任务和运行关联仍可恢复；
5. Agent 修改任务会创建新版本；
6. Agent 解释选入/排除原因时引用真实 Run 记录；
7. 两个会话消息严格隔离，重命名、置顶、归档、软删除和恢复持久化；
8. 相同 `conversation_id + client_message_id` 重试不重复副作用；
9. Turn 事件顺序稳定，断线续传不重复事件，最终消息以持久记录为准；
10. 总耗时与步骤耗时单调且由服务端生成；
11. 一个独立步骤失败时其他步骤继续，最终返回部分完成而不是丢失成功结果；
12. 收集结果至少包含来源覆盖、信息引用和可定位到时间线的应用路径；
13. `input`、`business`、`provider`、`capability`、`system` 错误分别映射到稳定 UI；
14. 不保存或输出隐藏思维链、模型密钥和未经 Schema 校验的任意结果块。

### 16.5 Playwright 最小流程

1. 创建任务 → 预览 → 保存 → 运行 → 查看匹配信息 → 打开 Run 详情；
2. Agent 草稿 → 编辑数量和来源 → 确认 → 任务列表出现；
3. 保存筛选视图 → 固定到左栏 → 刷新 → 恢复；
4. 1024px 下导航收成图标、详情覆盖打开，主任务区不被挤压；
5. 来源失败时任务、时间线、运行页和 Agent 显示一致的部分完成状态；
6. 新建 A/B 两个会话 → 分别发送消息 → 切换 → 重命名、置顶、归档和恢复；
7. Agent 执行中显示递增耗时和步骤，完成后出现来源、重点信息和可用跳转；
8. 模拟一个来源失败时仍显示其他来源信息和“部分完成”；
9. 折叠较早日期 → 加载三页 → 刷新恢复 → Agent 深链展开并高亮目标；
10. 新增来源打开与模型页一致的 Modal，草稿测试不创建来源或 Run，错误不丢表单；
11. 预置非默认主题 → 进入外观页 → 主题不变 → 用户点击后才持久化；
12. A2A 调试页读取真实 Agent Card → 发送查询 → 查看 Artifact → 跳到对应 Run。

### 16.6 来源、外观与 A2A

1. 来源创建和 Patch 对最终完整定义使用同一校验；空 URL 返回 422 且数据库不变；
2. Patch 重名返回 409，超时、401、429、空 Feed 和解析失败使用稳定错误码；
3. 草稿测试不创建来源、Collection Run 或 Capability 副作用；
4. Theme Runtime 恢复前不持久化默认值，非法值回退只执行一次；
5. Agent Card 由实际启用 Capability 生成，未实现流式时声明 `streaming: false`；
6. A2A `message/send`、Task 查询、取消和流式与 REST 使用相同 Application Capability；
7. 外部 Agent 受 Actor Policy、能力开关、审批和幂等保护；
8. Agent Card、事件、Artifact 和日志不包含密钥或内部异常堆栈。

### 16.7 真实模型安全验收

- 默认测试和 CI 仍使用确定性 Fake；
- 单元、模块、契约、Graph 节点、组件和普通 Playwright 一律不得调用真实模型；
- 真实模型仅由专用 `tests/live/` 完整链路场景使用；核心功能未完成或确定性全量回归
  未通过时，即使设置了环境变量也不得运行；
- 仅当显式设置 `AI_SIGNAL_RUN_LIVE_MODEL_TESTS=1` 时调用用户已经配置的模型；
- 此处“一轮”只指一个代表性完整产品链路，不是单一模型、模块或协议 Smoke；
- 每轮最多 1–2 次请求，固定超时和小型输出上限，提示词只使用公开非敏感内容；
- 测试只通过公开模型/Agent 入口，不读取或打印 Secret 文件；
- 非确定性断言只检查连接、结构化终态、非空可见文本、模型 ID、耗时和流结束；
- 429、超时和无效模型必须成为 Provider 局部错误，不能抹去已经完成的采集或查询；
- 真实模型不得直接写数据库、绕过 Capability、执行删除或发布。

---

## 17. 成功指标

指标用于验证设计是否有效，不用于构建复杂分析平台。

| 指标 | 目标方向 |
|---|---|
| 首个任务完成时间 | 用户能在数分钟内完成创建、预览和首次运行 |
| 任务规则实际生效率 | 所有结构化字段在执行记录中可验证 |
| 查找耗时 | 用户能从时间线或搜索快速回到已知信息 |
| 状态可信度 | UI 与后端 Run 状态零冲突 |
| 覆盖不足可理解率 | 用户能看到目标、实际和原因 |
| 失败恢复率 | 可重试问题无需重新创建任务 |
| 保存视图复用率 | 常用筛选无需反复配置 |
| Agent 草稿确认率 | Agent 建议能被理解、修改并安全启用 |
| 会话恢复可信度 | 切换、刷新和后台完成后不丢消息、Turn 或结构化结果 |
| Agent 首个可见进展时间 | 用户发送后快速看到已接收、阶段和实时耗时 |
| 部分成功保留率 | 独立步骤失败时，已完成结果仍全部可见且可继续操作 |
| 信息引用可达率 | Agent 结果中的信息按钮都能定位到正确条目和详情 |
| 长列表稳定性 | 分页无重复/遗漏，折叠和深链不破坏阅读位置 |
| 设置回归率 | 进入来源或外观页不会静默修改既有配置 |
| 协议声明一致性 | Agent Card 宣称的能力全部可通过契约测试验证 |

不使用“页面停留越久越好”作为目标；用户更快找到信息和完成处理才是成功。

---

## 18. 非目标

本蓝图不授权以下扩展：

- 通用 Agent 平台；
- 通用低代码或自动化平台；
- 多 Agent 任意协作；
- 微服务、Kafka、Celery 集群；
- 多租户、登录、RBAC、团队空间；
- 插件市场；
- 任意脚本和表达式执行；
- 第一阶段引入向量库；
- 为每个任务创建独立模型链和记忆系统；
- 完整网页正文或图片二进制进入 Graph State；
- 自动物理删除信息；
- 为追求最小数量自动生成或重复内容。

---

## 19. 文档同步清单

实施时按阶段同步：

- 任务产品和用户流程：`docs/00-project/00-02-product-and-user-flows.md`；
- 模块所有权：`docs/00-project/00-04-module-boundaries.md`；
- 时间线任务与查询：`docs/01-module-timeline/`；
- Agent 草稿和确认：`docs/02-module-review-agent/`；
- 卡片、专题和外部接口：`docs/04-module-poster-interop/`；
- 前端框架、组件和主题：`docs/05-platform/`；
- 测试、运行和错误码：`docs/06-quality-operations/`；
- 多会话、Turn 事件和流式结果：同步 Agent 文档、OpenAPI 与前端组件契约；
- A2A Agent Card、Task、Artifact 和 Actor Policy：同步 `04` 模块文档、契约与 TCK；
- JSON Schema、Graph 规格和实现提示词使用一致编号更新。

一个阶段只有在用户可以通过前端完成、Agent 可以通过相同 Capability 完成、开关真实
生效、运行可查看、失败可定位、测试通过且文档同步后，才算完成。
