# 06-02 可观测性与调试

## 1. 目标

用户与代码 Agent 能回答：

- 这次任务为什么这样执行？
- Agent 看到了哪些 Tool？
- 哪个开关阻止了能力？
- Graph 停在哪个节点？
- 哪个来源或 Provider 失败？
- 哪个输入生成了这张卡片？

## 2. 统一记录

### Run

表示采集、Agent、卡片或导入等长任务。

### CapabilityInvocation

记录：

- capability_id/version；
- actor；
- input/output digest；
- 状态与耗时；
- approval；
- error code；
- idempotency key；
- graph thread/checkpoint。

### TraceEvent

记录节点开始/完成、模型调用摘要、Tool 调用、Provider 错误、重试和警告。

## 3. 隐私与体积

- 默认记录摘要和 digest，不记录完整敏感 Prompt；
- 不记录实时音频；
- partial transcript 默认只在短期内存；
- 文件内容引用 Artifact ID；
- 可配置开发环境记录更详细数据。

## 4. TraceSink

```python
class TraceSink(Protocol):
    async def record(self, event: TraceEvent) -> None: ...
```

实现：

- DatabaseTraceSink；
- JsonlTraceSink；
- LangSmithTraceSink（可选）；
- CompositeTraceSink。

项目不将 LangSmith 设为必需运行依赖。

## 5. 调试页面

`/runs/[id]` 展示：

- Run 状态；
- 时间线；
- Capability 调用；
- Graph 节点；
- 审批；
- 错误与重试；
- 输入输出引用；
- 重新运行入口（受限）。

## 6. 代码 Agent 资源

MCP Resource 可提供：

```text
app://runs/{id}
app://runs/{id}/capability-invocations
app://runs/{id}/graph-state
```

对外返回前进行脱敏和权限校验。
