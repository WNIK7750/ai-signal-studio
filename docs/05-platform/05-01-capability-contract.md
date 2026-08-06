# 05-01 Capability 统一能力契约

## 1. 目的

Capability 是用户端、内置 Agent、LangGraph、MCP、A2A 与测试脚本之间的统一业务入口。

## 2. 基础类型

```python
from typing import Generic, Protocol, TypeVar
from pydantic import BaseModel

InputT = TypeVar("InputT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)

class ExecutionContext(BaseModel):
    request_id: str
    workspace_id: str
    actor_id: str
    actor_type: str          # user | internal_agent | external_agent | system
    agent_id: str | None = None
    idempotency_key: str | None = None
    approval_token: str | None = None

class Capability(Protocol, Generic[InputT, OutputT]):
    manifest: "CapabilityManifest"

    async def execute(
        self,
        input_data: InputT,
        context: ExecutionContext,
    ) -> OutputT: ...
```

## 3. Manifest

每个能力必须声明：

- 唯一 ID 与版本；
- 输入与输出 Schema；
- 是否有副作用；
- 风险等级；
- 默认审批规则；
- 所需权限；
- 依赖能力；
- 可暴露接口；
- 限额字段。

示例见 `contracts/01-capabilities/capability-catalog.yaml`。

## 4. 命名

建议使用：

```text
<domain>.<resource>.<action>
```

例如：

```text
collection.run.start
collection.run.get
intelligence.timeline.query
review.batch.submit
poster.draft.generate
poster.card.render
memory.pack.import
transcription.session.start
```

## 5. 执行管线

```text
resolve capability
→ validate input
→ resolve effective policy
→ authorize actor
→ check approval
→ check limits
→ execute application service
→ validate output
→ record invocation
→ return typed result
```

## 6. 错误模型

统一采用可机器处理的错误：

```json
{
  "code": "CAPABILITY_APPROVAL_REQUIRED",
  "message": "This operation requires user approval.",
  "retryable": false,
  "details": {
    "capability_id": "poster.card.render",
    "approval_request_id": "apr_123"
  }
}
```

主要错误码：

- `CAPABILITY_NOT_FOUND`；
- `CAPABILITY_DISABLED`；
- `CAPABILITY_FORBIDDEN`；
- `CAPABILITY_APPROVAL_REQUIRED`；
- `CAPABILITY_LIMIT_EXCEEDED`；
- `CAPABILITY_INPUT_INVALID`；
- `CAPABILITY_DEPENDENCY_FAILED`；
- `CAPABILITY_EXECUTION_FAILED`；
- `CAPABILITY_OUTPUT_INVALID`；
- `IDEMPOTENCY_CONFLICT`。

## 7. Tool 适配

LangChain Tool 只做：

- 将 Pydantic Input 暴露为 Tool Schema；
- 注入 ExecutionContext；
- 调用 Capability Executor；
- 将结构化结果返回模型。

Tool 中禁止写业务逻辑。

## 8. 版本策略

- Schema 与 Capability 采用显式版本；
- 破坏性变更新增版本，不原地改变旧契约；
- 同一主版本内允许增加可选字段；
- Manifest、示例与契约测试同步更新。

## 9. 最小 TDD

一个新 Capability 通常先写：

1. 成功执行测试；
2. 输入校验失败测试；
3. 开关禁用测试；
4. 需要审批测试；
5. 副作用幂等测试（如适用）。

## 10. 2026-08-06 产品能力面

当前 LangChain Tool 由 `TOOL_SCHEMAS` 通用绑定，统一覆盖信息、来源、任务、运行、
审核、卡片、Agent Pack、Artifact、模型、会话和外观。每个 Tool 仍只映射一个
Capability；来源/任务/卡片等 REST 路径调用同一 Application Service。

每步最多装配 3 个 Domain 与 8 个 Tool。禁用项在装配时不可见，即使模型或客户端伪造
Capability ID，`CapabilityExecutor` 仍返回 `CAPABILITY_DISABLED`。模型列表只返回
`has_api_key`，外观变化只返回 `ClientActionResult`，不允许后端操作 DOM。
