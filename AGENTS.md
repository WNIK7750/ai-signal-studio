# AGENTS.md

本文件是编程 Agent、代码审阅 Agent 和本项目内置开发 Agent 的首要入口。

## 任务目标

以模块级大步推进方式完成可用产品。不要把任务扩展为通用 Agent 平台、低代码平台、微服务平台或复杂治理系统。

## 必须遵守

- 先读当前模块文档、契约和已有测试。
- 运行测试基线后再修改代码。
- 采用简单 TDD：一个用户行为或能力契约对应少量关键测试，不追求先覆盖全部边角。
- 先完成垂直闭环，再重构抽象。
- API Router、LangChain Tool、LangGraph Node、A2A/MCP Adapter 不复制业务逻辑。
- 所有业务动作落到 Application Capability 或 Application Service。
- Agent Tool 必须通过能力适配器调用，不直接访问数据库。
- LangGraph 负责跨步骤编排、并行、暂停与恢复；普通 CRUD 不强制进入 Graph。
- 第三方源码、脚本或服务包装放在 `vendor_tools/`；业务代码不得深度引用其内部模块。
- Agent Pack 文档是身份、偏好、知识和长期记忆的事实来源；索引和缓存可重建。
- 删除默认是软删除或状态变更；发布、物理删除、覆盖长期记忆等操作需要显式审批策略。
- 外部副作用必须支持幂等键。

## 不要做

- 不要为了“低耦合”提前拆微服务。
- 不要建设插件市场、拖拽工作流、复杂 RBAC、Kafka/Celery 集群。
- 不要为前端、Agent、A2A 和 MCP 分别实现同一业务规则。
- 不要让模型自由返回后端无法验证的核心数据。
- 不要把完整网页正文、图片二进制或大文档塞入 LangGraph State。
- 不要修改第三方工具内部源码来适配业务；优先写 Adapter。
- 不要要求每个小改动经过复杂规格审批。

## 推荐实现循环

```text
1. 选择当前宏模块中的一个完整用户场景
2. 写 2～6 个失败测试
3. 实现最小后端能力
4. 接入 REST 与 Agent Tool
5. 完成前端操作闭环
6. 运行模块测试和端到端冒烟测试
7. 根据已经出现的问题重构
8. 提交一个可运行的增量
```

## 文档路由

- 先从 `docs/README.md` 确认当前模块编号。
- 实现模块前先读 `docs/<模块目录>/<模块号>-00-overview.md`。
- 共享能力、Graph 和前端约束位于 `docs/05-platform/`。
- 测试、可观测性和安全约束位于 `docs/06-quality-operations/`。
- 机器可读契约、Graph 规格和实施提示词使用与模块文档一致的编号。

## UI 实现约束

- 先读 `docs/05-platform/05-03-frontend-architecture.md` 到 `05-06-icon-system.md`。
- 借鉴 Codex 的稳定导航、聚焦主区和按需详情区，但按具体业务任务决定每页栏位，不复用僵硬三栏模板。
- 视觉值必须经过设计令牌；主题切换、用户自定义和高对比模式不能由页面局部样式绕过。
- 功能入口使用统一 Tabler Outline 前缀图标和可见文字；纯图标按钮必须有可访问名称。
- 不要堆叠“卡片里的卡片”，不要用大面积渐变、装饰性 Hero 或无意义动效遮挡主要工作流。

## 测试最低要求

- Domain/Application：纯 Python 单元测试。
- Capability：输入输出 Schema、权限/开关、错误码测试。
- REST：FastAPI TestClient。
- WebSocket：FastAPI WebSocket TestClient。
- LangGraph：节点分支、interrupt/resume、幂等副作用测试。
- 前端：核心交互组件测试；每个宏模块至少一个 Playwright 冒烟流程。
- 契约：JSON Schema 示例必须通过验证。

## 完成定义

一个模块只有在以下条件同时成立时才算完成：

- 用户可以通过前端完成核心场景。
- 内置 Agent 可以通过能力接口完成同一场景。
- 功能开关能实际阻止或允许能力。
- 关键流程有测试。
- 失败会返回可定位的错误，不静默吞掉。
- 执行记录可查看。
- 文档与机器可读契约已同步。

## 首选命令约定

项目代码落地后建议统一：

```powershell
# 后端（首次安装见 scripts/bootstrap.ps1）
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest tests/modules/<module_name> -q

# 前端
.\scripts\pnpm.ps1 install --frozen-lockfile
.\scripts\pnpm.ps1 --dir apps/web test
.\scripts\pnpm.ps1 --dir apps/web test:e2e

# 契约
.\.venv\Scripts\python.exe scripts/validate_contracts.py
```

实际命令以仓库后续脚本为准，但必须保持“一条命令可运行某模块测试”。
