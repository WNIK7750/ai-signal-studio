# ADR-0002：所有入口共享 Capability Core

状态：Accepted

## 决策

REST、Workspace Agent、LangGraph、MCP、A2A 和测试调用同一 Application Capability。

## 原因

避免重复业务逻辑，保证 Agent 真正能使用应用全部功能，并让代码 Agent 容易追踪调用路径。

## 后果

新增功能必须先定义输入输出和执行服务；传输层只做适配。
