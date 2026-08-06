# 编程 Agent 实施提示词

提示词按交付模块编号，只作为当前模块的实施入口，不替代 `AGENTS.md`、模块文档、机器契约和测试。

- `01-module-timeline/01-coding-agent-prompt.md`
- `02-module-review-agent/02-workspace-agent-next-slice-coding-agent-prompt.md`
- `02-module-review-agent/02-workspace-agent-complex-task-repair-coding-agent-prompt.md`：
  当前主线；用用户原始失败提示词一次性修复双 Runtime、复杂 Planner、会话上下文、
  目标验收、综合分析和流式结果。
- `03-module-agent-assets-stt/03-realtime-stt-coding-agent-prompt.md`
- `07-delivery/07-complete-agent-and-product-release-coding-agent-prompt.md`：连续完成
  Workspace Agent、剩余核心产品任务、最终全栈验收和安全 Git 发布。

2026-08-06 的发布收尾实现通过了当时的固定 Fixture 验证，但随后发现自然语言复杂任务
仍存在阻断缺陷；当前以 Module 2 复杂任务修复提示词为准。实际发布证据、Deferred E5
和 Git 状态以
`docs/07-delivery/07-04-optimization-implementation-status.md` 为准。
