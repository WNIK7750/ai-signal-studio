# 05-06 线性图标系统

## 1. 选型

第一版统一使用 Tabler Icons 的 Outline 风格。选择理由：

- 基于一致的 24×24 网格和默认 2 px 线宽；
- 线条简洁，适合高密度工具型界面；
- 尺寸、线宽和颜色可通过设计令牌调整；
- 提供 React 使用方式；
- MIT License，可用于个人和商业项目。

不在同一界面混用 Lucide、Heroicons、Emoji、平台原生图标和自绘 SVG。确有缺失图标时，先从 Tabler 同风格图标组合或提交自定义图标，并遵守 24×24 网格。

官方来源：

- 图标浏览与自定义：https://tabler.io/icons
- 源码与许可证：https://github.com/tabler/tabler-icons

## 2. 功能前缀规则

以下位置使用“图标 + 文本”：

- 主导航和设置导航；
- 页面级主要功能；
- 下拉菜单项；
- 批量操作；
- 空状态的推荐动作；
- 状态或风险提示。

常见工具栏在用户熟悉后可只显示图标，但必须提供 Tooltip 和可访问名称。不要用无文字图标承载不可逆或不常见动作。

## 3. 建议映射

| 功能 | Tabler 图标组件 | 用途 |
| --- | --- | --- |
| 时间线 | `IconTimeline` | 主导航、时间线标题 |
| 审核 | `IconChecklist` | 待审核入口 |
| Workspace Agent | `IconMessageChatbot` | Agent 导航与空状态 |
| 卡片 | `IconCards` | 卡片列表与模板 |
| Runs | `IconActivity` | 执行记录与进度 |
| 来源 | `IconRss` | 来源设置 |
| Agent Pack | `IconRobot` | Agent 配置 |
| 外观与主题 | `IconAdjustmentsHorizontal` | 设计令牌设置 |
| 搜索 | `IconSearch` | 搜索入口 |
| 筛选 | `IconFilter` | 时间线与审核筛选 |
| 立即采集 | `IconRefresh` | 发起采集 |
| 实时语音 | `IconMicrophone` | 转写按钮 |
| 审批 | `IconShieldCheck` | Approval Panel |
| 图片与素材 | `IconPhoto` | Artifact 与卡片素材 |

实现前以锁定版本的 `@tabler/icons-react` 导出为准；若组件名发生变化，只修改集中映射，不在业务组件内替换。

## 4. 视觉令牌

```text
icon.size.dense       16 px
icon.size.default     18 px
icon.size.toolbar     20 px
icon.size.empty       24 px
icon.stroke.default   1.75
icon.stroke.range     1.25～2.25
```

- 图标默认继承 `currentColor`；
- 导航选中态使用背景、文字和图标颜色共同表达，不依赖加粗线宽；
- 图标与文字间距使用 8 px 语义间距；
- 状态图标可以使用语义色，功能图标默认继承文字色；
- 同一操作在全站使用同一个图标。

## 5. React 边界

建立集中 Registry：

```ts
export const featureIcons = {
  timeline: IconTimeline,
  review: IconChecklist,
  agent: IconMessageChatbot,
  cards: IconCards,
  runs: IconActivity,
  appearance: IconAdjustmentsHorizontal,
} as const;
```

- 业务组件从 Registry 获取功能图标；
- 普通临时动作可以直接按需导入；
- 禁止全量导入整个图标包；
- SVG 设置 `aria-hidden="true"` 时，相邻文字或按钮必须提供名称；
- 纯图标按钮的点击目标至少 40×40 px。

## 6. 动效

默认图标静态显示。只允许以下高信号动效：

- 采集或刷新中的旋转；
- 麦克风录音中的状态变化；
- 展开/收起方向变化；
- 成功或错误的一次性反馈。

动效不得改变图标占位尺寸，并尊重 `prefers-reduced-motion`。
