# 05-05 设计令牌与主题

## 1. 目标

所有页面共享同一套语义设计令牌。用户可以：

- 一键切换预设主题；
- 选择需要调整的令牌类别；
- 使用 Select、分段选择器、滑动条和颜色控件修改允许的值；
- 在实时预览中查看典型导航、列表、表单、状态和 Agent 消息；
- 保存在当前部署实例的浏览器、导出 JSON 或恢复预设。

机器契约：

- `contracts/05-design-system/design-tokens.schema.json`
- `contracts/05-design-system/themes.example.json`

## 2. 令牌层级

### 原始值

色值、像素、时长等基础值，只在主题文件中出现。

### 语义令牌

组件只消费语义用途，例如：

```text
color.canvas
color.surface
color.text
color.border
color.accent
color.danger
layout.navWidth
layout.inspectorWidth
shape.radius
icon.stroke
```

禁止组件直接使用 `blue-500`、`#ffffff`、任意 `17px` 等主题无法解释的值。

### 组件令牌

只有多个状态确实需要稳定组合时才增加，例如 `nav.item.activeBackground`。组件令牌必须引用语义令牌，不能形成第二套颜色系统。

## 3. 自定义界面

主题设置页使用三段式布局：

```text
令牌类别选择器 → 当前类别控制区 → 实时预览
```

控制方式：

| 类别 | 控件 | 建议范围 |
| --- | --- | --- |
| 模式 | 分段选择器 | Light / Dark / High contrast |
| 字体 | Select | 系统字体、项目内批准字体 |
| 基础字号 | Slider + 数字输入 | 12～18 px，步长 1 |
| 内容密度 | Slider | 0.85～1.15，步长 0.05 |
| 导航宽度 | Slider | 208～320 px，步长 8 |
| 检查器宽度 | Slider | 280～480 px，步长 8 |
| 内容最大宽度 | Slider | 720～1440 px，步长 40 |
| 圆角 | Slider | 0～20 px，步长 2 |
| 图标尺寸 | Slider | 16～24 px，步长 1 |
| 图标线宽 | Slider | 1.25～2.25，步长 0.25 |
| 动效时长 | Slider | 0～300 ms，步长 25 |
| 语义色 | 色板 Select + 色彩控件 | 必须实时检查对比度 |

Slider 必须同时提供当前数值、键盘调整和恢复默认按钮；不能只靠拖动完成精确设置。

## 4. 预设主题

第一版产品界面提供：

- `signal-light`：冷中性浅色，适合日常高密度阅读；
- `paper`：暖中性编辑主题，适合长文和卡片内容；
- `midnight`：石墨深色，保持多层表面可区分；
- `forest`：低饱和绿色主题，适合长时间阅读。

主题切换是一次点击操作，不打开二次确认。切换在前端即时生效并保存到当前浏览器；后续如增加服务端工作区配置，再由部署者显式迁移。

## 5. 作用域与持久化

优先级从低到高：

```text
内置默认主题
→ 部署工作区主题
→ 当前浏览器调整
```

- 预设主题是只读基线；
- 修改预设时仅保存允许的令牌值；
- 本项目不提供登录或多用户偏好合并；
- 浏览器本地存储是第一版唯一的界面偏好持久化位置；
- 导入主题先做 Schema、范围与对比度校验。

## 6. CSS 映射

主题在根节点映射为 CSS 变量：

```css
:root {
  --color-canvas: #f7f7f5;
  --color-surface: #ffffff;
  --color-text: #1f2328;
  --color-border: #d9dce1;
  --color-accent: #2563eb;
  --layout-nav-width: 248px;
  --layout-inspector-width: 360px;
  --shape-radius: 10px;
  --icon-size: 18px;
  --icon-stroke: 1.75;
}
```

React 组件只读取变量或类型化 token 对象，不在运行时拼接任意 Tailwind 类名。

## 7. 实时预览

预览必须同时包含：

- 展开与折叠导航；
- 时间线列表和选中状态；
- 表单、Select 与 Slider；
- 普通、成功、警告、错误状态；
- Agent 消息与 Capability 调用；
- 主按钮、次按钮、危险按钮；
- 焦点、禁用和 Hover 状态。

预览不是缩小版整站，而是覆盖令牌影响面的稳定样本。

## 8. 可访问性与安全边界

- 正文与背景目标对比度至少 4.5:1；
- 大字和非文本 UI 至少 3:1；
- 主题编辑器实时提示不合格组合；
- `high-contrast` 不允许被自动覆盖；
- 危险、成功和警告必须同时使用图标或文字；
- 自定义主题只包含数据，不允许注入 CSS、URL、脚本或任意字体文件。
