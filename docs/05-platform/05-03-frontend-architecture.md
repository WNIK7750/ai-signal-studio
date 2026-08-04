# 05-03 前端架构

## 1. 原则

- 前端只处理交互、展示和本地编辑状态；
- 权限、能力开关和审批在后端再次校验；
- Agent 与普通页面共享服务端能力；
- 长任务以 Run 为中心展示进度；
- 实时语音仅填充输入框，不自动提交。
- 整体应用壳借鉴 Codex 的稳定导航、聚焦主工作区与按需上下文面板，但每个业务页面按真实任务重新分配空间。
- 视觉值通过设计令牌表达，页面和组件不得散落无法追踪的颜色、间距、圆角和阴影常量。

配套规范：

- `docs/05-platform/05-04-ui-layout-and-components.md`；
- `docs/05-platform/05-05-design-tokens-and-themes.md`；
- `docs/05-platform/05-06-icon-system.md`。
- `docs/05-platform/05-07-model-configuration-and-routing.md`。

## 2. 目录建议

```text
apps/web/src/
├── app/
├── features/
│   ├── timeline/
│   ├── review/
│   ├── agent/
│   ├── poster/
│   ├── settings/
│   ├── runs/
│   └── transcription/
├── components/
├── lib/api/
├── lib/contracts/
├── design-system/
│   ├── tokens/
│   ├── themes/
│   ├── icons/
│   └── primitives/
├── styles/
└── tests/
```

按 feature 组织，不建立一个巨大的全局 components/utils 层。

`design-system/` 只保存跨 feature 的视觉原语、令牌与主题适配；业务组合组件仍留在对应 `features/` 下。

## 3. 服务端状态

使用 TanStack Query：

- 查询时间线、批次、卡片和运行状态；
- mutation 后按资源精确失效；
- 不在多个页面复制后端状态；
- 长任务可轮询或订阅 SSE。

## 4. Agent UI

结构化显示：

- 消息；
- Tool/Capability 调用；
- 运行进度；
- 审批卡片；
- 时间线结果；
- 卡片草稿预览；
- 错误与重试。

不要只显示纯文本聊天记录。

## 5. 实时语音组件

`RealtimeTranscriptionInput` 对外行为：

```ts
value: string
onChange(value: string): void
onStateChange(state): void
```

组件内部处理：

- microphone permission；
- MediaStream lifecycle；
- WebSocket；
- partial/final segment merge；
- pause/resume/stop；
- reconnect；
- cleanup。

该组件可复用于 Agent 输入框、搜索框和卡片编辑器，但默认仅 Agent 输入框启用。

## 6. 海报编辑器

第一版表单字段：

- headline；
- subtitle；
- summary；
- key_points；
- source；
- date；
- image selection；
- template options。

前端预览与服务端渲染使用同一 HTML/CSS 模板契约，避免预览和最终 PNG 差异过大。

## 7. 响应式基线

- `≥ 1280px`：允许导航、主工作区和按需详情面板并存；
- `1024～1279px`：保留主工作区，导航可收窄，详情面板按需覆盖或切换；
- `768～1023px`：单一主工作区，导航使用抽屉，次要面板使用 Sheet；
- `< 768px`：单列任务流，批量操作使用底部操作条，禁止强塞三栏。

断点只定义能力上限；具体页面是否使用第二或第三栏由该页面的任务结构决定。
