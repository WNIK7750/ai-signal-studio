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

## 5. 契约测试

- JSON/YAML 示例通过 Schema；
- Pydantic Schema 与导出 JSON Schema 一致；
- Capability Catalog 中引用的能力可解析；
- Agent Pack 示例可导入；
- WebSocket 事件符合协议；
- OpenAPI operationId 不重复。

## 6. 不要求

- 第一版不要求 100% 覆盖率；
- 不要求每个私有函数测试；
- 不要求复杂 mutation testing；
- 不要求所有浏览器组合；
- 不要求真实 LLM 每次进入 CI。

## 7. 合并前最低检查

```text
目标模块测试通过
契约验证通过
一个相关 E2E 冒烟通过
git diff --check 通过
无未说明的数据迁移破坏
```
