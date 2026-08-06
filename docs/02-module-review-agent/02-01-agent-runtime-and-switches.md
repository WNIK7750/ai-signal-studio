# 02-01 Agent Runtime、能力开关与客制化

## 1. 基本原则

内置 Agent 理论上可调用应用全部 Capability；实际可用集合由以下因素求交集：

```text
已安装能力
∩ 工作区启用能力
∩ Agent Pack 启用能力
∩ 当前角色权限
∩ 当前运行上下文允许能力
```

## 2. 开关不是简单布尔值

一个能力配置可以包含：

```yaml
poster.card.render:
  enabled: true
  approval: required
  limits:
    max_items_per_call: 10
    max_calls_per_day: 30
  constraints:
    allowed_template_ids: [default-news-v1]
```

支持三种审批策略：

- `never`：无需确认；
- `required`：每次需要确认；
- `policy`：根据数量、风险、来源或调用者动态判断。

## 3. 动态 Tool 列表

每次 Agent Run 开始时：

1. 加载 Agent Pack；
2. 解析工作区配置；
3. 计算有效 Capability；
4. 将可用能力适配为 LangChain Tools；
5. 将禁用原因记录到调试上下文。

不要把全部 Tool 永久绑定给模型后再在 Tool 内静默拒绝；优先只暴露当前可用 Tool，同时仍在执行层做二次校验。

生产装配使用 LangChain Agent Middleware/Structured Tool 和 LangGraph StateGraph。
模型先看到轻量 Domain Index，选定计划步骤后才加载模块自己的 Domain Prompt、
Tool Guidance 和 Tool Schema。完整契约见
[02-05 Workspace Agent 最终工程蓝图](02-05-final-agent-engineering-blueprint.md)和
[02-03 Workspace Agent 上下文工程与动态工作流](02-03-agent-context-engineering-and-workflows.md)。
OpenAI Responses 或其他 Provider 的原生 Tool Search 只能作为节省 Token 的优化，
不能替代本地 Capability Policy。

## 4. Agent 的职责

Agent 负责：

- 理解用户意图；
- 选择能力；
- 组织多步调用；
- 对不确定项提议；
- 将结构化结果解释给用户。

Agent 不负责：

- 直接写数据库；
- 绕过审批；
- 自行改变能力开关；
- 将未经确认的观察写入长期记忆；
- 直接执行物理删除。

## 5. 内置 Agent 类型

第一版只需要一个 `workspace-agent`，通过不同 Agent Pack 配置行为。不要过早创建多个自治 Agent。

后续可增加：

- collector-agent；
- editor-agent；
- poster-agent；

但仍调用相同 Capability。

## 6. 对话中的人工确认

当能力返回 `CAPABILITY_APPROVAL_REQUIRED`：

- Agent 向用户展示动作、范围和风险；
- 用户确认后获取一次性 approval token；
- Agent 使用相同输入和 token 重试；
- 执行层验证 token 与能力、输入摘要、用户和有效期匹配。

## 7. 防止能力漂移

每次 Run 记录：

- Agent Pack 版本；
- Capability Catalog 版本；
- 实际暴露的 Tool 清单；
- 模型配置；
- System Prompt 摘要；
- 开关与审批策略摘要。

## 8. 当前运行增量

`workflow_version=0.4.0` 的首个生产切片已使用真实 LangChain/LangGraph：

- Bootstrap 只带版本化 Base、Capability Snapshot 和 Domain Index；
- 当前步骤才加载 `collection` 或 `intelligence` Domain Prompt 与 Tool Schema；
- `collection.run.start`、`intelligence.timeline.query` 和
  `intelligence.recommend` 通过 LangChain Structured Tool 进入同一
  Capability Executor；
- 禁用能力不会进入步骤 Tool 集合，执行层仍做权威二次拒绝；
- OpenAI-compatible 工作区模型由 `langchain-openai` 适配；Demo/测试工作区使用
  明确的 Fake Chat Model，仍经过真实 Planner、StateGraph、Tool 和 Capability 路径。

其他 Domain、审批 Token 和站内写能力仍按 `07-04` 后续切片扩展。
