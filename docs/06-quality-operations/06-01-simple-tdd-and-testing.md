# 06-01 简单 TDD 与测试策略

## 1. 核心态度

相信编程 Agent 的实现和调试能力。文档提供稳定边界和验收行为，不设置复杂流程门禁。

TDD 的作用是：

- 固定关键行为；
- 让代码 Agent 快速定位回归；
- 支持模块替换；
- 防止接口漂移。

不是追求开发前写出全部测试。

## 2. 模块级 TDD

每次选择一个完整场景，通常先写 2～6 个关键失败测试。

示例：采集模块

1. 手动创建采集 Run；
2. 模拟两个来源返回重复项目；
3. 去重后保存一条信息；
4. Run 状态完成；
5. Agent Tool 能启动同一 Capability。

## 3. 测试层次

### 单元测试

- Domain 规则；
- 评分公式；
- 状态转换；
- 文档解析；
- partial/final transcript merge。

### Capability 测试

- Schema；
- 有效策略；
- 审批；
- 幂等；
- 统一错误。

### Adapter 测试

- Repository；
- HTTP/Search；
- Vendor STT Adapter；
- Renderer。

第三方网络服务使用 fake server 或 fixture，不让日常测试依赖真实网络。

### Graph 测试

- 分支和汇总；
- interrupt/resume；
- 节点失败；
- checkpoint；
- 副作用幂等。

### 前端与 E2E

每个宏模块至少一个 Playwright 冒烟流程。

## 4. Fake 优先

为以下端口提供 Fake：

- FakeLLM；
- FakeSearchProvider；
- FakeFeedCollector；
- FakeRealtimeSTTProvider；
- InMemoryArtifactStorage；
- FakePosterRenderer。

这让编程 Agent 可以离线复现失败。

测试 Fixture 必须显式使用 Fake 配置和临时模型配置文件。即使开发机已经在“模型”页
保存真实模型，普通测试命令也不能自动继承并调用它。

## 5. 真实模型只用于完整链路验收

真实模型不是单元测试、模块测试、契约测试、Graph 节点测试、组件测试或单页
Playwright 的依赖。小测试只能验证确定性行为：

- Context 和 Prompt 是否正确装配；
- Planner/Tool/Graph 轨迹是否符合契约；
- Capability、审批、幂等和错误是否真实执行；
- SSE、恢复、结果块和站内跳转是否正确；
- Provider 调用使用 Fake Chat Model 或 HTTP Mock。

只有同时满足以下条件，才允许调用用户已配置的真实模型：

1. 当前发布范围的核心功能已经形成完整用户链路；
2. 后端全量、前端测试、Playwright、构建和契约校验均已通过；
3. 使用专用 `tests/live/` 完整链路场景，而不是在模块测试中加临时调用；
4. 显式设置 `AI_SIGNAL_RUN_LIVE_MODEL_TESTS=1`；
5. 明确记录模型调用预算、超时、Turn ID、Run ID 和结果，不读取或打印密钥；
6. 每次只执行一个代表性完整链路，模型调用次数由 Harness 设定小型硬预算；
7. 失败作为 Provider 验收结果记录，不覆盖确定性回归结论，也不连续重试消耗额度。

普通 `pytest`、模块测试、前端单元测试、普通 Playwright 和契约校验必须始终跳过
`live_model`。未来专用完整链路入口应同时要求环境开关和显式 `live_model` 标记，
二者缺一即跳过；本地存在模型配置本身不构成授权。

## 6. 契约测试

- JSON/YAML 示例通过 Schema；
- Pydantic Schema 与导出 JSON Schema 一致；
- Capability Catalog 中引用的能力可解析；
- Agent Pack 示例可导入；
- WebSocket 事件符合协议；
- OpenAPI operationId 不重复。

## 7. 不要求

- 第一版不要求 100% 覆盖率；
- 不要求每个私有函数测试；
- 不要求复杂 mutation testing；
- 不要求所有浏览器组合；
- 不要求、也不允许真实 LLM 进入普通 CI 或日常小测试。

## 8. 合并前最低检查

```text
目标模块测试通过
契约验证通过
一个相关 E2E 冒烟通过
git diff --check 通过
无未说明的数据迁移破坏
```
