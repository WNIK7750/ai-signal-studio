# AI Signal Studio Agent 与产品收尾发布提示词

你正在 AI Signal Studio 仓库根目录继续开发，下文记为 `<repo-root>`。本任务不是再
完成一个小切片，而是在现有成果上连续完成 **Workspace Agent 主线和当前任务列表中的
其余核心产品任务**，进行一次最终确定性全栈验收，然后安全提交到：

```text
https://github.com/WNIK7750/ai-signal-studio.git
```

不要在完成一个 Epic 后停下。每个阶段采用简单 TDD 和目标测试，阶段通过后直接继续；
所有核心阶段完成后才运行一次最终全栈验证并进入 Git 发布。

---

## 1. 范围边界

### 本任务必须完成

- E2：Agent Turn、事件、耗时、部分成功、后台执行、取消和恢复的通用化；
- E3：长时间线稳定游标、日期折叠、分段加载和 Agent 深链；
- E4：来源新增/编辑 Modal、无副作用测试和稳定错误；
- E7：剩余 Domain Pack、Context/Evidence/Memory Budget 和能力一致性；
- E8：结构化 Plan/Execute/Replan、interrupt/resume、恢复和幂等的完整生产路径；
- E9：筛选、推荐、匹配需求、比较、趋势、覆盖缺口和采集后分析；
- E10：站内信息、审核、卡片、任务、来源、运行、模型、外观和会话能力接入 Agent；
- E11：确定性 Evaluation Harness、版本/图谱一致性和发布回归；
- Module 3：Agent Pack 原子导入/导出、Artifact、文档/图片理解和实时语音转写；
- Module 4 剩余闭环：Poster Graph、卡片编辑、PNG Artifact 和导出；
- 首次部署默认配置、个性化数据隔离、密钥保护和发布文档；
- 最终确定性全栈验证；
- 验证通过后的 Git 分支、提交、推送和 Draft PR。

### 本任务不实现

- `E5` 外部 Agent Gateway。它仍是 Deferred 设计项，见
  `docs/04-module-poster-interop/04-02-external-agent-gateway-design.md`；
- A2A/MCP 运行服务、外部账户系统或公网入口；
- 移动端专用页面；继续使用桌面优先的动态布局；
- 插件市场、工作流画布、微服务、Kafka/Celery、复杂 RBAC 或多 Agent 组织；
- 第二套 Agent Runtime、任意数据库/HTTP/Shell/Python 工具；
- GitHub Release、Tag 或直接推送 `main`。本任务最多创建 Draft PR。

---

## 2. 当前工作树事实

开始时必须重新核对，但当前已知：

- 当前分支为 `main`；
- `origin` 指向
  `https://github.com/WNIK7750/ai-signal-studio.git`；
- 工作树包含 E0、E1、任务工作台和 Workspace Agent 0.4.0 等大量已完成但未提交改动；
- 不得 `reset`、`checkout --`、清理或覆盖这些改动；
- 不得假定所有未跟踪文件都可发布；
- 本机 `.env`、数据库、日志和 `*.local.json` 含部署/个性化数据；
- `gh auth status` 曾显示当前 GitHub 凭据无效，发布前必须重新检查；
- GitHub Connector 曾对目标仓库返回 404，可能是私有仓库未授权；不得据此新建同名仓库。

先运行：

```powershell
git status -sb
git remote -v
git diff --stat
git ls-files --others --exclude-standard
```

只读检查当前改动，不执行暂存、提交、切分历史或远端写入。

---

## 3. 必读文件

按顺序读取，先理解当前实现和未完成状态：

1. `AGENTS.md`
2. `docs/README.md`
3. `docs/02-module-review-agent/02-00-overview.md`
4. `docs/02-module-review-agent/02-05-final-agent-engineering-blueprint.md`
5. `docs/02-module-review-agent/02-03-agent-context-engineering-and-workflows.md`
6. `docs/02-module-review-agent/02-04-agent-workflow-history.md`
7. `docs/03-module-agent-assets-stt/03-00-overview.md`
8. `docs/03-module-agent-assets-stt/03-01-agent-pack-and-memory.md`
9. `docs/03-module-agent-assets-stt/03-02-data-artifacts-and-images.md`
10. `docs/03-module-agent-assets-stt/03-03-realtime-speech-to-text.md`
11. `docs/04-module-poster-interop/04-00-overview.md`
12. `docs/04-module-poster-interop/04-01-rest-a2a-and-mcp.md`
13. `docs/05-platform/05-01-capability-contract.md`
14. `docs/05-platform/05-02-langgraph-workflows.md`
15. `docs/05-platform/05-03-frontend-architecture.md`
16. `docs/05-platform/05-04-responsive-layout.md`
17. `docs/05-platform/05-05-design-tokens-and-themes.md`
18. `docs/05-platform/05-06-icon-system.md`
19. `docs/06-quality-operations/06-01-simple-tdd-and-testing.md`
20. `docs/06-quality-operations/06-02-observability-and-debugging.md`
21. `docs/06-quality-operations/06-03-security-and-approval.md`
22. `docs/07-delivery/07-01-development-roadmap.md`
23. `docs/07-delivery/07-03-product-and-experience-optimization-blueprint.md`
24. `docs/07-delivery/07-04-optimization-implementation-status.md`
25. `graph-specs/02-module-review-agent/02-agent-task-graph.yaml`
26. `graph-specs/04-module-poster-interop/04-poster-graph.yaml`
27. `contracts/01-capabilities/capability-catalog.yaml`
28. `contracts/02-agent-pack/agent-pack.schema.json`
29. `contracts/03-realtime-transcription/realtime-transcription-protocol.schema.json`
30. `contracts/04-interoperability/openapi-outline.yaml`
31. `vendor_tools/speech_to_text/README.md`
32. `vendor_tools/speech_to_text/whisperlive/INTEGRATION.md`
33. `.gitignore`
34. `.env.example`
35. `config/models.example.json`
36. `config/model-secrets.example.json`
37. `scripts/verify.ps1`
38. `scripts/run_e2e.py`

然后检查已有测试和实际 diff。文档状态是导航，不替代代码核查。

---

## 4. 开发姿态

- 先建立一个覆盖全部阶段的计划，并始终只保留一个 `in_progress` 项；
- 可使用子 Agent 并行审计或处理低冲突模块，但共享工作树时先划定文件所有权；
- 初始只运行一次相关基线，不在每个小修改后跑全量；
- 每个完整用户行为先写 2～6 个关键失败测试，然后立即实现；
- 一个阶段完成后运行该阶段目标测试，继续下一阶段；
- 不因局部问题停掉其他独立任务；保留部分完成并继续可执行工作；
- 只有外部认证、法律许可或确实需要用户选择的事项才暂停；
- 不要求每个普通重构提交 Blueprint Change Proposal；
- 不读取、输出、截图或复制 API Key、Token、Cookie、私有 Prompt 和个人内容；
- 不调用真实模型，直到所有核心开发和确定性全栈验证通过。

### 初始基线

只运行与当前主线相关的确定性基线：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/modules/agent_runtime tests/api/test_agent_turn_stream.py tests/api/test_agent_conversations.py -q
.\scripts\pnpm.ps1 --dir apps/web test
```

记录基线失败。已有失败与本任务相关时修复；无关且可复现时记录并绕开，不回滚用户
改动。初始阶段不要运行真实模型或完整 Playwright。

---

## 5. 第一阶段：完成 Agent Runtime 耐久主干

主要入口：

```text
apps/api/src/ai_signal_api/agent_runtime/
apps/api/src/ai_signal_api/modules/agent/
apps/api/src/ai_signal_api/routers/agent.py
apps/api/src/ai_signal_api/capabilities/
apps/api/src/ai_signal_api/models.py
apps/api/src/ai_signal_api/database.py
apps/api/src/ai_signal_api/schemas.py
tests/modules/agent_runtime/
tests/api/test_agent_turn_stream.py
```

基于现有真实 LangChain/LangGraph 0.4.0 继续，不建立平行实现。

不要把已有节点名误认为能力已经完成。开始实现前先用测试确认并补齐这些已知缺口：

- N01～N25 虽已注册，但 Fast Plan、复杂度路由、Supervisor、Result Join、
  Failure Control 和 Finalizer 仍可能是空实现；
- N09/N15 必须成为可到达的真实 `interrupt()` / `Command` 恢复节点；
- Scheduler 必须从顺序索引升级为经过校验的依赖 DAG，并支持有界并行与 Replan；
- Action Binder 必须从三个硬编码能力改成 Schema 驱动的通用绑定；
- Harness 必须落实 TurnLease、DeadlineBudget、RetryProfile、WAL、
  RecoveryScanner 和 Artifact 引用；
- 取消必须在节点边界和长 Tool 调用之间持续传播，不能只在 Graph 开始时读取一次；
- `/api/agent-runs` 只能成为同一 Turn Runtime 的兼容 Adapter，不能继续运行第二套关键词
  Agent。

必须完成：

1. Agent Turn 在切换会话、页面刷新和浏览器断开后继续运行；
2. 持久 Event Journal 支持稳定序号和 `Last-Event-ID` 续传；
3. 后台会话显示运行中、等待处理、完成和未读；
4. 停止、恢复和只重试失败步骤保持幂等；
5. `running/waiting/stale` Turn 的启动恢复扫描可定位且不重复副作用；
6. Clarification 与 Approval 使用真实 LangGraph interrupt/resume；
7. Direct Response、Deterministic Fast Plan、Structured LLM Plan 使用同一 `AgentPlan`；
8. DAG 依赖、只读并行、写步骤串行、局部失败、依赖跳过和最多两次 Replan 可验证；
9. Result Inspector 只判断契约和成功条件，不进行无限自我反思；
10. 旧关键词 `_run_action()` 退出生产主路径，只保留明确兼容入口或删除；
11. Tool 只能通过 `CapabilityExecutor`，不能直接访问数据库、Session 或 Repository；
12. Base Prompt、Domain、Tool、workflow 版本写入 Turn Trace，但不记录完整 Prompt 或 Secret；
13. 信息、Run、Task 和 Result Block 只保存小型引用，不把大正文放入 Graph State；
14. 模型或单个 Provider 失败时返回 `partial` 和已完成结果，不让整个回复链消失。

简单 TDD 至少覆盖：

- interrupt/resume；
- 进程重启恢复；
- 已成功步骤不重跑；
- 一项失败、独立步骤继续；
- 取消和幂等；
- 后台会话与 SSE 恢复；
- 禁用 Capability 后 Tool 不可见且伪造调用仍拒绝。

完成本阶段后只运行 Agent Runtime/API 目标测试，不运行全栈。

---

## 6. 第二阶段：完成 Context、Domain 与研究工作流

现有 `collection`、`intelligence` Domain Pack 继续使用。按真实场景增加：

```text
tasking
sources
runs
review
cards
```

只有模块确实拥有独立 Prompt、工具或工作流时才建立 Pack，不创建空目录。

### Context 与 Evidence

- 每次模型调用装配：

```text
Base
+ Workspace Policy
+ Relevant Conversation Summary
+ Selected Domain
+ Current Plan/Step
+ Evidence References
+ Current Tool Schema
+ Response Schema
```

- 未选择 Domain 的 Prompt 与工具不得进入请求；
- Tool Resolver 每步最多激活 3 个 Domain、暴露 8 个 Tool；
- 长期偏好只保存用户明确确认的内容，可查看、撤销和软删除；
- 外部信息作为不可信 Evidence 隔离，不能覆盖 Base Policy；
- 推荐、比较和趋势事实必须引用真实 `information_id`、来源和时间；
- 候选不足时返回较少结果，不伪造补足；
- Context 超预算时先选择、压缩和引用，不增加独立向量数据库。

### E9 研究工作流

完成并在 Agent UI 中交付：

```text
research.filter
research.recommend
research.match_requirements
research.compare
research.trend_brief
research.coverage_gap
collection_then_analyze
```

至少验收：

1. 推荐过去 30 天最值得关注的 5 条 Agent 信息；
2. 按开源、本地部署、Windows 和官方证据筛选；
3. 比较三个 Agent 框架，每个事实带信息引用；
4. 生成一个月趋势、代表信息、反例和资料缺口；
5. 采集后分析，单来源失败仍返回成功来源结果；
6. 每项结果能跳到站内具体 AI 信息。

结果块只能使用后端白名单：

```text
information_list
recommendation_list
comparison_table
trend_summary
evidence_sources
signal_preview
partial_failure
navigation_action
```

不要向 UI 返回任意模型 HTML、脚本、URL 或原始 Tool JSON。

---

## 7. 第三阶段：完成站内全部安全 Agent 能力

把站内用户可理解的业务动作 Capability 化；REST、Agent、Scheduler 共用同一
Application Service。

### 信息

- 查询、详情、已读、收藏、归档、笔记、保存视图和专题；
- 专题板、周报与可导出的引用型交付物；
- 单条显式操作可以直接执行；
- 模型推断的批量写入需要确认；
- 批量结果按项返回成功和失败。

### 审核与卡片

- 查询批次、逐项建议、保留/拒绝/延后、批量提交；
- 待处理页统一展示审核、异常、审批和 Agent 待确认动作；
- 卡片查询、生成、修改、模板和字数校验；
- 单卡失败不阻断其他成功草稿；
- 发布、覆盖编辑和批量渲染必须审批。

### 任务

- 查询、创建草稿、修改、预览、复制、创建版本、启停、运行、取消和重试；
- 启用定时计划必须确认；
- 预览失败不丢草稿，新版本失败不覆盖活动版本；
- REST、Agent 和 Scheduler 都调用 `task.run.start`。

### 来源与运行诊断

- 来源列表、无副作用测试、健康诊断、修复草稿和启停；
- 补齐 Module 1 尚缺的通用网页/搜索 Adapter，并落实 SSRF、防重定向逃逸、超时、
  响应大小和内容类型边界；
- 修改地址、类型或启停先展示影响并确认；
- Run、SourceRunResult 和 Capability Invocation 可查询；
- 支持只重试失败来源，以及按原版本/当前版本重试；
- Provider 失败返回可理解诊断，不表现为 Agent 崩溃。

### 模型、外观和会话

- 模型可查询、测试和为当前会话选择；
- API Key 永不进入模型上下文、事件、结果或日志；
- 新增/修改密钥只打开设置表单，由用户输入；
- 外观变化返回受控客户端 Action，不让后端操作 DOM；
- 会话重命名、置顶、归档和恢复可用；
- 物理删除、长期记忆覆盖不开放。

每个 Agent Tool 必须映射唯一 Capability，具有输入输出 Schema、功能开关、Actor
Policy、审批、幂等和稳定错误。REST 与 Agent 对同一输入应得到同一业务结果。

---

## 8. 第四阶段：完成时间线、来源和全局 UI

### 时间线 E3

后端与前端一起完成：

- `(published_at, id)` 稳定游标；
- `next_cursor`、`has_more` 和每页 50；
- 本地 ISO 日期分组；
- 今天和最近日期默认展开，较早日期可折叠并保存状态；
- 日期显示总数、未读数和重要数；
- IntersectionObserver 与可访问“加载更多”按钮并存；
- 新内容提示不抢滚动位置；
- Agent 深链跨页定位、展开、滚动、高亮和打开详情；
- 不因跨年份相同月日合并。

### 来源 E4

- 复用模型页 Dialog 交互；
- 支持新增与编辑；
- 字段包含类型、名称、地址、单次上限和启用状态；
- 支持取消、无副作用测试、保存；
- 测试结果显示数量和最多 3 条样例；
- URL、仓库、DNS、超时、401、429、解析、空 Feed 和重名使用稳定错误；
- 每一行 testing/saving 状态独立；
- 支持 `role=dialog`、焦点回收、Esc 和未保存保护。

### Agent UI

- 多会话、搜索、重命名、置顶、归档、软删除与撤销继续可用；
- 流式计划、步骤、耗时、来源覆盖、证据和部分失败可折叠；
- 提供停止、继续、重试失败来源、审批、查看全部和运行详情；
- 快捷修改常用方案和定时任务；
- 输出区分用户输入错误、业务错误、Provider 错误、Capability 错误和系统错误；
- 多请求中某项失败不吞掉其他成功结果；
- 不显示评分数字，继续使用颜色、理由和证据。

### 布局与视觉

- 桌面优先，1024px、1360px、1600px 均可用；
- 宽度不足时优先改变框架：左栏收为图标，详情区使用抽屉或覆盖层；
- 左栏、主区和按需详情按任务分配，不强制三栏；
- 所有视觉值使用设计令牌；
- 功能图标使用 Tabler Outline 和可访问名称；
- 不做移动端专用页面，但 CSS 和组件保持动态布局；
- 不堆叠卡片、渐变 Hero 或无意义动效。

每个宏模块至少补一个真实用户行为 Playwright。

---

## 9. 第五阶段：完成 Agent Pack、Artifact 与实时转写

Module 3 当前主要是文档与契约，不能把 Schema 或 Vendor 说明当成运行时完成证据。按
下面三个纵向闭环推进，并让 REST、Capability 与 Agent 共用 Application Service。

### Agent Pack 与长期记忆

完成：

```text
ZIP 导入 → 安全校验 → Diff 预览 → 原子激活 → 编辑/版本/回退 → 导出 → FTS 检索
```

要求：

- 严格按 `contracts/02-agent-pack/agent-pack.schema.json` 校验 manifest、Markdown、
  YAML 和 JSONL；
- 拒绝路径穿越、绝对路径、符号链接逃逸、超限文件和 ZIP Bomb；
- 导入先落临时目录，全部校验和索引成功后再原子切换；失败不能替换当前 Pack；
- Pack 文件是身份、偏好、知识和长期记忆的事实来源，SQLite/FTS 索引可重建；
- 第一版使用 SQLite FTS，不引入向量数据库；
- 用户确认后才写入长期偏好或事实，并保留版本、撤销、软删除和审计；
- 版本库只跟踪通用空模板，例如 `agent-packs/examples/ai-editor/`；首次运行复制到
  已忽略的 `data/agent-packs/ai-editor/`，运行时不得改写版本化示例；
- 导出只包含用户明确选择的 Pack 内容，不夹带数据库、日志、Secret 或 Artifact。

### 文档、图片与 Artifact

完成：

```text
上传 → 本地 Artifact Storage → 类型/大小/摘要校验 → 解析/OCR/Vision →
Artifact ID → Agent 按需检索与引用
```

要求：

- 文件内容保存到 `data/artifacts/` 一类已忽略目录，数据库只保存元数据、Digest、
  权限和小型引用；
- Graph State、SSE 和日志不保存图片二进制、完整网页或大型文档正文；
- Markdown、文本、JSON、YAML 使用原生解析器；复杂文档解析通过可替换 Adapter，
  Docling 等依赖保持可选；
- OCR/Vision 通过项目 Protocol 和模型能力开关调用，不能把 Provider SDK 侵入业务层；
- 文件类型、Magic Bytes、大小、页数、重复 Digest、解析失败和恶意内容返回稳定错误；
- 外部文档内容始终作为不可信 Evidence，不能写入 Base Prompt；
- Artifact 删除默认软删除；导出、覆盖或包含敏感内容的动作执行审批策略。

### 实时语音转写

后端提供：

```text
POST /api/transcription/sessions
GET  /api/transcription/sessions/{id}
WS   /ws/transcription/{session_id}?token=<short-lived-token>
```

统一协议至少包含：

```text
session.started
transcript.partial
transcript.final
warning
error
session.closed
```

要求：

- 业务层定义 `RealtimeTranscriptionProvider` Protocol；Fake Provider 用于所有普通测试；
- WhisperLive 只通过 `vendor_tools/speech_to_text/` 的 Adapter 接入，业务代码不得深度
  import 第三方内部模块；
- Session Token 短时、单会话、不可写日志，WebSocket 校验大小、格式、状态和超时；
- Web 端 MVP 使用 MediaRecorder；除非浏览器兼容证据要求，不先做 AudioWorklet；
- partial 只做临时显示，final 合并到可编辑输入框，绝不自动发送给 Agent；
- 停止、断线、页面切换和组件卸载都释放麦克风 Track、Recorder 和 WebSocket；
- 默认不保存原始音频；如未来允许保存，必须单独开关和审批；
- 浏览器 `SpeechRecognition` 不能作为后端实时转写的完成证据。

简单 TDD 分别覆盖 Agent Pack 原子失败、Artifact 引用，以及 WebSocket
partial/final/error/stop、断线恢复和组件卸载。真实 STT Provider 只做独立手动集成验收，
不进入普通 pytest、组件测试或 Playwright。

---

## 10. 第六阶段：完成 Poster Graph、编辑与 PNG Artifact

保留现有“审核保留项 → 卡片浏览 → 详情 → 原文”闭环，在此基础上完成 Module 4 的
非 Gateway 剩余范围：

1. `graph-specs/04-module-poster-interop/04-poster-graph.yaml` 对应真实 LangGraph；
2. 只有 `keep` 审核项可生成，重复请求按信息与版本幂等；
3. `confirm_draft_generation` 与 `confirm_render` 使用真实 interrupt/resume；
4. 编辑器支持标题、摘要、要点、模板、封面来源和 100～1000 字限制，默认 400；
5. 来源封面合适时可引用原封面，否则使用离线 HTML/CSS 文字封面；
6. 默认模板在六种相近浅天蓝/青绿色与引语/网格底板间稳定随机，不调用生图模型兜底；
7. PNG 通过 Renderer Adapter 生成到本地 Artifact Storage，数据库和 Graph 只保存
   Artifact ID、尺寸、Digest 与状态；
8. 单卡渲染失败不阻断其他卡片，重试不重复生成已成功副作用；
9. Agent 与 UI 都能编辑、审批渲染、下载 PNG 并查看对应信息证据；
10. 增加“采集 → 审核 → 卡片 → 编辑 → PNG → 原文”的确定性端到端流程。

本阶段只实现 Poster Graph 和本机导出。MCP/A2A、外部 Agent Policy 与 Gateway 页面
继续 Deferred，不能因为同属 Module 4 而顺带启用。

---

## 11. 第七阶段：Evaluation Harness 与图谱同步

在 `tests/evals/agent/` 建立少量高质量、确定性评测：

- 查询、推荐、比较、趋势、采集后分析；
- 多意图、缺参、空结果和局部失败；
- 禁用能力、审批拒绝和幂等；
- Prompt Injection、Secret 泄漏和预算耗尽；
- interrupt/resume、取消和重启恢复；
- Context Snapshot 与 Domain/Tool 选择；
- Outcome、Contract、Trajectory、Safety、Reliability、UX 和 Cost/Latency Grader。

测试使用 Fake Model，但必须经过真实 LangChain/LangGraph/Tool/Capability 路径。
LangSmith 只作为可选调试增强，本地 Trace 和 pytest Grader 必须独立可用。

### 工作流图谱

优先在既定 `workflow_version=0.4.0` 内补齐实现，不主动改变拓扑。

如果确实改变了工作流拓扑、Base/Domain 装配、Domain 路由、工具加载、Planner、
Executor、Result Inspector、审批、失败继续或结果合并，则同一增量必须：

1. 提交 Blueprint Change Proposal；
2. 更新 `graph-specs/02-module-review-agent/02-agent-task-graph.yaml`；
3. 向 `docs/02-module-review-agent/02-04-agent-workflow-history.md` 追加版本；
4. 更新 Figma 当前 Agent 工作流图；
5. 更新 `docs/07-delivery/07-04-optimization-implementation-status.md`；
6. 更新 Graph/Contract 测试；
7. 保证所有位置使用相同 `workflow_version`。

没有拓扑变化时只更新实施状态和证据，不制造新版本或重复生成 Figma。

---

## 12. 第八阶段：公开部署默认值与个性化隔离

项目没有登录系统。每位部署者在自己的设备上修改配置，因此版本库只保存安全默认和
示例，不保存当前用户内容。

### 必须提供的默认

- `.env.example`：默认使用 `heuristic`，API Key 为空；
- `config/models.example.json`：只用虚构 Provider、Model ID 和 URL；
- `config/model-secrets.example.json`：所有密钥值为空字符串，不使用 `sk-` 风格假值或
  看起来可能是真实 Token 的随机占位符；
- 来源：提供通用官方来源或 Demo 模板，不包含当前用户订阅；
- 任务：提供未启用的通用任务模板，不能安装后自动产生外部费用；
- Agent Pack：版本库中的 Pack 必须是通用示例，不包含真实用户身份、偏好、知识、
  决策和长期记忆；
- 外观：提供通用默认主题和设计令牌，首次打开不能覆盖用户恢复值；
- 卡片封面：保留六种浅天蓝/青绿色默认模板，不依赖生图服务；
- 模型未配置时，用户仍可浏览、筛选和用确定性功能完成基本流程；
- 用户在设置页部署模型后，无需修改源码即可跑通 Workspace Agent。

### 个性化数据只能保存在本地

以下内容不得提交：

```text
.env
.env.*
**/config/*.local.json
**/config/**/*.local.json
data/
logs/
artifacts/
uploads/
exports/
backups/
agent-packs/local/
*.db
*.db-*
*.sqlite
*.sqlite3
*.log
*.pem
*.key
*.p12
*.pfx
```

此外禁止提交：

- 真实 API Key、GitHub Token、搜索服务 Token、Bearer Token；
- 本机模型注册表和密钥文件；
- 用户来源、任务、保存视图、会话、消息、笔记、收藏和阅读状态；
- Agent Pack 的真实 profile、preferences、facts、observations、decisions；
- 测试截图、Trace、HAR、浏览器 Profile、认证状态、Cookie、Provider 原始响应和含个人
  内容的导出文件；
- `codex-clipboard-*`、Temp 图片、数据库 Dump、备份包和带访问参数的私有来源 URL。

运行时需要可编辑 Agent Pack 时，使用“版本化默认模板 → 首次运行复制到已忽略本地
目录”的方式，不要直接改写仓库中的示例 Pack。

### 发布安全检查

新增 `scripts/check_release_safety.py` 和少量测试，至少检查：

1. `--worktree`、`--tracked`、`--staged` 和 `--history` 四种模式；
2. staged/tracked/history 中不存在上述本地路径；
3. 不包含常见 API Key、Token、Private Key、Authorization Header、带凭据 URL 和本机
   绝对路径模式；
4. 只报告规则 ID、文件路径和行号，不打印匹配到的 Secret；
5. example 文件中的密钥字段为空，测试固定值使用 `test-only-api-key` 一类安全哨兵，
   不模拟 `sk-` 真实密钥格式；
6. `git ls-files` 不包含数据库、日志、local 配置或本地 Agent Pack；
7. `.gitignore` 能命中根目录与嵌套 `config/*.local.json`；
8. Playwright 把模型配置、密钥文件和数据库显式指向临时目录，不能只依赖忽略规则；
9. 新增媒体文件需要显式批准，仓库文档资产使用窄白名单。

同时加入经过审核并固定版本/Commit 的 Gitleaks pre-commit 与 GitHub Action，Action 必须
使用完整 Git 历史。项目 Python Guard 是产品路径和个性化内容门禁，Gitleaks 是 Secret
扫描；两者互补，不能互相代替。若任何历史 Commit 命中真实凭据，先停止发布并提示用户
吊销/轮换，再制定历史清理方案；仅删除当前文件或加入 `.gitignore` 不算修复。

更新 README，写明：

- Windows 11 安装与一键启动；
- 首次运行的安全默认；
- 如何在 UI 配置模型；
- 配置、数据、日志和 Agent Pack 的本地路径；
- 如何备份与重置；
- 不会上传 API Key 或本地数据。

PowerShell 只显示基础服务状态；含中文和主要启动逻辑继续放在 Python 中，避免 GBK
终端编码问题。

如果缺少 LICENSE，不自行选择许可证；在 Draft PR 中把它列为公开仓库前需要用户确认
的事项。

---

## 13. 第九阶段：一次最终确定性全栈验证

各阶段开发时只运行目标测试。全部核心功能完成后，执行一次最终全栈级验证：

```powershell
.\scripts\verify.ps1 -E2E
git diff --check
.\.venv\Scripts\python.exe scripts/check_release_safety.py --worktree
.\.venv\Scripts\python.exe scripts/check_release_safety.py --tracked
.\.venv\Scripts\python.exe scripts/check_release_safety.py --history
```

`verify.ps1 -E2E` 必须覆盖：

- 版本一致性；
- 后端全量 pytest；
- 契约校验；
- 前端单元测试；
- ESLint；
- Next.js 生产构建；
- 使用临时数据库、`heuristic` Provider 和 Demo 来源的 Playwright 全流程。

如果最终全栈验证失败：

1. 只运行失败模块的目标测试定位并修复；
2. 不调用真实模型；
3. 修复完成后再次执行完整命令，直到获得一次最终全绿结果；
4. 记录最终一次完整通过的测试数量、耗时和已知非阻断警告。

不要用局部测试代替最终全栈结果。

---

## 14. 第十阶段：可选的单次真实模型完整链路

确定性全栈全部通过后，才允许考虑真实模型。普通测试、模块测试和协议 Smoke 仍禁止
调用真实模型。

若不存在，增加：

```text
tests/live/test_workspace_agent_full_chain.py
```

要求：

- 标记 `@pytest.mark.live_model`；
- 没有 `AI_SIGNAL_RUN_LIVE_MODEL_TESTS=1` 时跳过；
- 只通过公开 Agent/Turn 入口调用用户已配置模型；
- 使用临时数据库和安全 Fixture，不读取或输出密钥；
- 只执行一个代表性完整链路；
- Harness 最多允许 1～2 次模型请求；
- 验证 Conversation → Turn → Plan → Tool → Capability → Evidence →
  ResultBlock → SSE → UI 跳转；
- 只断言结构、状态、引用、耗时和流结束，不断言逐字输出；
- 429、超时或额度不足记录为 Provider 验收结果，不自动连续重试。

只有环境开关已经由用户显式提供时才运行：

```powershell
$env:AI_SIGNAL_RUN_LIVE_MODEL_TESTS = "1"
.\.venv\Scripts\python.exe -m pytest -m live_model tests/live/test_workspace_agent_full_chain.py -q
```

环境开关未设置时记录“未授权，已跳过”，不要为了完成任务自行开启。

---

## 15. 第十一阶段：Git 发布规划与执行

只有以下条件全部满足后才能开始 Git 写操作：

- 当前任务中的核心功能完成；
- 最终确定性全栈验证通过；
- 文档、契约和任务状态同步；
- Release Safety 检查通过；
- 没有本地配置、个人内容或密钥进入候选文件；
- 已明确真实模型验收是通过还是按规则跳过。

### 15.1 认证与远端

运行：

```powershell
gh --version
gh auth status
git remote get-url origin
gh repo view WNIK7750/ai-signal-studio --json nameWithOwner,visibility,defaultBranchRef,url
```

要求：

- `origin` 必须是用户给定仓库；
- GitHub CLI 必须已认证为有该仓库写权限的账号；
- 如果认证失效，停止 Git 发布阶段并请用户执行
  `gh auth login -h github.com`；
- 登录后如 HTTPS Git 仍不能使用凭据，再执行 `gh auth setup-git`；
- 如果仓库返回 404，不创建替代仓库、不改 remote，报告访问权限问题；
- 开发成果和测试结果保留在工作树，不因认证失败回滚。

同时运行：

```powershell
git config --local --get user.name
git config --local --get user.email
```

当前身份可能仍是其他托管平台的 noreply 邮箱。不得修改全局 Git 配置；如果需要调整
GitHub 提交归属，只在用户确认后设置仓库级 `user.name` / `user.email`。

### 15.2 分支

当前在默认分支时创建：

```powershell
git switch -c codex/agent-product-release
```

如果该分支已存在，检查它是否属于当前工作；不要覆盖或强制重建。不得直接提交到
`main`，不得 force push。

### 15.3 发布前文件审计

```powershell
git status --short --ignored
git diff --stat
git diff --check
.\.venv\Scripts\python.exe scripts/check_release_safety.py --worktree
.\.venv\Scripts\python.exe scripts/check_release_safety.py --tracked
.\.venv\Scripts\python.exe scripts/check_release_safety.py --history
```

特别确认以下文件仍被忽略且未暂存：

```text
.env
config/models.local.json
config/model-secrets.local.json
apps/web/config/models.local.json
data/
logs/
artifacts/
uploads/
exports/
backups/
agent-packs/local/
```

当前工作树是混合的大型增量。不要使用 `git add -A`、`git add .` 或 `git add -u`。
先建立已审阅的发布文件清单，只用显式路径暂存属于本任务和先前已完成产品增量的文件。
发现来源不明或无关改动时，保留未暂存并在交付中说明。

### 15.4 暂存、复查和提交

暂存后必须运行：

```powershell
git diff --cached --name-status
git diff --cached --stat
git diff --cached --check
.\.venv\Scripts\python.exe scripts/check_release_safety.py --staged
```

检查 staged diff 中：

- 没有 Secret 或个人内容；
- 没有数据库、日志、截图和本地配置；
- 示例使用不可用占位值；
- 代码、契约、测试、文档和启动脚本形成同一个可运行版本。

优先创建一个原子发布提交，避免把互相依赖的未验证状态拆成多个提交：

```powershell
git commit -m "feat: complete workspace agent product flow"
```

只有能保证每个提交独立可运行时，才拆分为少量清晰提交。

### 15.5 推送和 Draft PR

```powershell
git push -u origin codex/agent-product-release
```

推送成功后优先使用 GitHub Connector 创建 Draft PR；Connector 无法识别私有仓库时，
使用：

```powershell
gh pr create --draft --base <remote-default> --head codex/agent-product-release --body-file <utf8-pr-body-file>
```

`<remote-default>` 必须来自 `gh repo view`，不能未经核验固定为 `main`。PR 正文使用 Python
生成 UTF-8 临时文件，避免 Windows PowerShell GBK 破坏中文，不把完整日志写入正文。

PR 标题：

```text
Complete Workspace Agent and remaining product workflows
```

PR 正文必须包含：

- 完成的 Agent 和产品闭环；
- 重要架构边界；
- 用户可见变化；
- 默认配置和个性化数据隔离；
- Secret/Release Safety 结果；
- 后端、前端、构建、契约和 Playwright 证据；
- 真实模型完整链路是通过还是按规则跳过；
- 已知非阻断警告；
- `E5` 外部 Agent Gateway 仍为 Deferred；
- LICENSE 若缺失，需要用户在公开仓库前选择。

不要把 PR 直接标为 Ready，不合并，不创建 Tag 或 GitHub Release。

---

## 16. 文档和状态同步

完成后至少更新：

```text
README.md
docs/README.md
docs/02-module-review-agent/
docs/05-platform/
docs/06-quality-operations/
docs/07-delivery/07-04-optimization-implementation-status.md
contracts/01-capabilities/capability-catalog.yaml
contracts/04-interoperability/openapi-outline.yaml
prompts/README.md
```

任务状态只能根据实际测试和 UI 证据更新。不得把未运行的真实模型、未推送的分支、
未创建的 PR 或 Deferred E5 写成已完成。

---

## 17. 完成定义

只有同时满足以下条件，本提示词任务才算完成：

- 用户可以从前端完成全部核心信息管理场景；
- 内置 Agent 可以通过 Capability 完成同一业务场景；
- Agent 使用真实 LangChain/LangGraph、持久 Checkpoint 和动态 Domain/Tool；
- 复杂请求支持 Plan、并行、interrupt、审批、失败继续、恢复和结果合并；
- 信息、任务、来源、Run、审核、卡片、模型、外观和会话能力已接入；
- 时间线和来源 UI 完成；
- Agent Pack、Artifact、实时转写、Poster Graph、编辑与 PNG 导出完成；
- 功能开关、审批、幂等和错误真实生效；
- 关键模块测试和最终全栈验证通过；
- 不包含用户个性化内容或 Secret；
- 首次部署拥有安全默认，配置模型后无需改源码即可跑通；
- 文档、契约、任务状态和必要的工作流图谱同步；
- 已创建 `codex/agent-product-release` 或等价 `codex/` 分支；
- 已提交并推送到用户指定 remote；
- 已创建 Draft PR，或因 GitHub 认证/权限问题明确停在唯一 Git 阻塞点。

---

## 18. 最终交付格式

最终答复必须明确列出：

1. 完成的用户闭环；
2. Agent Runtime、Domain、Tool、Capability 和 UI 变化；
3. 后端、前端、契约、构建和 Playwright 的实际结果；
4. 真实模型调用次数及结果，未授权则明确写 0 次；
5. Release Safety 和未上传本地文件清单；
6. 分支名、Commit SHA、Push 结果和 Draft PR URL；
7. 未完成或 Deferred 项；
8. 唯一仍需用户处理的事项，例如 GitHub 重新登录或 LICENSE 选择。

不要只报告“代码已写”；必须给出可验证的成品、测试和 Git 证据。
