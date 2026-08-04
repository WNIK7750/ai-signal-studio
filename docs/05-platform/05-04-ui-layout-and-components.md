# 05-04 UI 布局与组件分类

## 1. 设计方向

### 目的

AI Signal Studio 是高频阅读、筛选、审核和编辑工具。首屏必须直接呈现当前工作对象，而不是营销式 Hero、装饰性大卡片或大面积空白。

### 受众

主要使用者会重复扫描大量 AI 信息，并在直接操作、Agent 建议和长任务运行之间切换。界面首先服务可扫描性、状态判断和低摩擦操作。

### 语气

安静、紧凑、技术化但不压迫。默认采用中性多层表面和少量语义色；强调色只用于当前选择、主要动作和焦点。

### 记忆点

将“信号”状态做成贯穿 AI 信息、审核和 Agent 结果的细线轨道。第一版不显示具体分数，只使用“重要、关注、普通”三级标识；颜色必须同时配合形状、文字标签或可访问名称。

## 2. 从 Codex 借鉴什么

Codex 的可取之处是信息架构，不是逐像素复制：

- 左侧保留项目、任务和历史入口；
- 中间区域始终聚焦当前任务或当前对象；
- 变更、审阅、运行细节等支持信息只在需要时出现；
- 长任务在原上下文中持续显示状态，切换任务不丢失进度；
- 主输入或主操作保持稳定位置。

AI Signal Studio 不照搬代码 Diff、终端或多 Agent 专用布局。时间线、审核、对话和海报编辑使用不同的空间分配。

## 3. 应用壳

桌面端应用壳允许三种区域，但不要求每页同时显示：

```text
┌──────────────┬──────────────────────────────┬──────────────────┐
│ 全局导航     │ 当前任务主工作区             │ 按需详情/检查器  │
│ 208～288 px  │ minmax(0, 1fr)               │ 300～420 px      │
└──────────────┴──────────────────────────────┴──────────────────┘
```

- 全局导航：AI 信息、审核、对话 Agent、卡片、运行记录、设置；可折叠为仅保留前缀图标的窄栏。
- 主工作区：唯一必须常驻的区域。
- 详情/检查器：筛选、方案、定时、决策、运行详情、属性编辑；支持完全关闭，没有明确次级任务时默认关闭或记忆上次状态。
- 顶部栏：页面标题、范围切换、搜索和页面级主动作，建议高度 48～56 px。
- 底部固定区：只用于 Agent Composer 或移动端批量操作，避免多个固定操作条争夺空间。

## 4. 页面级合理分配

| 页面 | 主对象 | 推荐布局 | 关键理由 |
| --- | --- | --- | --- |
| AI 信息 `/timeline` | 按日期组织的信息流 | 导航 + 宽内容流；筛选器按需作为 288～320 px 侧栏并可完全关闭 | 阅读是主任务，筛选不应永久挤压内容 |
| 审核 `/review` | 待审核条目与批量决策 | 条目区约 65%～72%，决策检查器约 28%～35%，底部批量操作条 | 需要同时看到证据与决策影响 |
| Agent `/agent` | 对话、常用方案与定时 | 居中的对话流；方案/定时以 300～360 px 面板按需打开；Composer 固定在主区底部 | 高频对话保持连续，常用配置可在原上下文快捷修改 |
| 卡片列表 `/cards` | 草稿集合 | 自适应网格或紧凑列表，详情用抽屉 | 浏览和选择优先，不需要常驻检查器 |
| 卡片编辑 `/cards/[id]` | 海报画布 | 素材栏 200～240 px + 弹性画布 + 属性栏 300～360 px | 这是唯一适合稳定三栏的核心页面 |
| 来源设置 | 来源列表与连接状态 | 列表主区 + 编辑抽屉；连接测试靠近当前来源 | 避免表单长期占据半屏 |
| Agent/主题设置 | 配置与实时预览 | 设置导航 200～224 px + 表单 560～720 px；主题页可增加 320～400 px 预览 | 只有需要即时视觉反馈时展示第三栏 |
| Run 详情 `/runs/[id]` | 执行时间线 | 时间线约 60%～68%，调用/错误详情约 32%～40% | 需要并排定位阶段与证据 |

比例是起点，不是硬编码。实现时根据最小可读宽度使用 CSS Grid `minmax()` 和容器查询，不能只按百分比压缩。

## 5. 组件种类

### 5.1 Shell 与导航

- `AppShell`
- `PrimaryNav`
- `WorkspaceSwitcher`
- `PageHeader`
- `CommandMenu`
- `ContextPanel`

### 5.2 操作与输入

- `Button`、`IconButton`、`SplitButton`
- `SearchInput`、`Combobox`、`Select`
- `SliderControl`、`TokenPicker`、`ColorControl`
- `BulkActionBar`
- `RealtimeTranscriptionInput`

### 5.3 数据与状态

- `TimelineGroup`、`SignalItem`
- `DataTable`、`CompactList`
- `StatusBadge`、`SourceBadge`
- `RunProgress`、`InvocationRow`
- `EmptyState`、`Skeleton`

### 5.4 审核与审批

- `ReviewItem`
- `DecisionControl`
- `ApprovalPanel`
- `EvidenceList`
- `DiffPreview`

### 5.5 Agent 与运行

- `ConversationThread`
- `MessageBlock`
- `CapabilityCall`
- `CommonPlanEditor`
- `ScheduleControl`
- `RunTimeline`
- `Composer`

### 5.6 编辑与媒体

- `PosterCanvas`
- `PropertyInspector`
- `AssetPicker`
- `ImagePreview`
- `TemplateSelector`

### 5.7 反馈与浮层

- `Toast`、`InlineAlert`
- `Dialog`、`Drawer`、`Sheet`
- `Tooltip`、`Popover`

不要把同级信息反复包成“卡片里的卡片”。边框、分隔线、表面层级和留白应共同表达结构。

## 6. 布局决策顺序

每个新页面依次回答：

1. 用户此刻操作的唯一主对象是什么？
2. 哪些信息必须与主对象同时可见？
3. 哪些内容只是按需检查器或临时操作？
4. 哪个动作频率最高，是否需要稳定位置？
5. 在 1024 px 以下，次要区域应变成抽屉、Sheet 还是独立步骤？

只有第二问存在强同时可见需求时才启用右侧面板；只有三个区域都需要持续直接操作时才启用稳定三栏。

## 7. 可用性底线

- 图标按钮必须有可访问名称和 Tooltip；
- 键盘焦点始终可见；
- 文本和图标不能只靠颜色表达状态；
- 批量危险动作显示数量、范围和后果；
- 面板打开不能导致主对象突然丢失滚动位置；
- 动效优先解释展开、切换和运行状态，并尊重 `prefers-reduced-motion`。
- 应用壳不得出现登录、账号、个人版或用户菜单；部署后的自定义设置属于单个本地工作区。

## 8. 首版视觉基准

- [AI 信息界面概念图](assets/module-1-ai-information-concept.png)
- [对话与定时界面概念图](assets/module-1-agent-concept.png)
- [主题设置界面概念图](assets/theme-settings-concept.png)

## 9. 参考来源

- OpenAI Codex 产品页：https://openai.com/codex/
- OpenAI Codex App 介绍：https://openai.com/index/introducing-the-codex-app/
- ChatGPT/Codex Quickstart：https://learn.chatgpt.com/docs/quickstart

以上来源用于提取任务导航、主工作区和按需支持面板的原则，不作为品牌视觉或逐像素复刻依据。
