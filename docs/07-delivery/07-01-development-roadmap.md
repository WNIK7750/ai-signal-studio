# 07-01 开发路线图：模块级大步快跑

## 总原则

不是先完成所有架构底座，而是每一步交付一个能实际使用的成品模块。抽象只做到支撑当前模块，并为下一模块留下清晰接口。

---

## Module 1：可用的 AI 情报时间线

### 成品目标

用户可以配置少量来源，手动或定时采集 AI 信息，在前端按日期查看去重、摘要和评分后的时间线。

### 实现范围

- FastAPI 与 Next.js 基础项目；
- 响应式 AppShell、全局导航与页面标题栏；
- 设计令牌运行时、Signal Light/Dark 预设、一键主题切换和基础外观设置；
- SQLite、Alembic；
- SourceConfig；
- 手动采集与 APScheduler；
- RSS、GitHub Releases、一个通用网页/搜索 Adapter；
- Collection Graph；
- 标准化与确定性去重；
- LangChain 结构化摘要、分类、评分；
- Timeline API/UI；
- 场景化时间线布局、统一线性功能图标；
- Run 调试页面基础版；
- Capability Core 的最小实现；
- Workspace Agent 能调用 `collection.run.start` 和 `intelligence.timeline.query`。

### 简单 TDD

- 创建采集 Run；
- 重复内容去重；
- LLM 结构化输出校验；
- 时间线按日期返回；
- Agent Tool 调用相同 Capability；
- 一个“点击采集并看到结果”的 E2E。
- 一个“切换主题、刷新后仍保持选择”的前端测试。

### 暂不做

- A2A/MCP；
- 复杂事件聚类；
- 向量库；
- 海报；
- 文档/图片/语音。

---

## Module 2：审核工作台与全功能 Agent

### 成品目标

用户与 Workspace Agent 都能对情报进行保留、拒绝、延后、编辑和批量确认；能力开关与审批真实生效。

### 实现范围

- ReviewBatch 与 ReviewDecision；
- Review Graph interrupt/resume；
- 批量审核 UI；
- 审核条目区、决策检查器和批量操作条的专用布局；
- 状态流转；
- Agent Pack 基础加载；
- Capability Policy；
- 动态 LangChain Tools；
- 审批 Token；
- Agent 结构化 UI；
- 聚焦对话流、稳定 Composer 和按需运行/审批详情面板；
- 完整 Capability Invocation 记录。

### 简单 TDD

- 禁用能力不可调用；
- Agent 和 REST 使用相同审核服务；
- interrupt 后可恢复；
- 拒绝不物理删除；
- 审批 Token 绑定输入；
- 一个“Agent 发起批量审核、用户确认”的 E2E。

---

## Module 3：Agent Pack、文档、图片与实时语音输入

### 成品目标

用户可导入/编辑 Agent Pack；上传文档与图片供 Agent 使用；在 Agent 输入框实时说话并得到可编辑文字。

### 实现范围

- Agent Pack ZIP 导入导出；
- Agent、Artifact 与外观设置的分组导航；
- Markdown/YAML/JSONL 校验与版本；
- SQLite FTS 检索；
- Artifact Storage；
- Markdown/Text/JSON 原生解析；
- 可选 Docling Adapter；
- 图片上传、OCR/Vision Adapter；
- `vendor_tools/speech_to_text/whisperlive` 集成；
- FastAPI WebSocket；
- RealtimeTranscriptionInput；
- final transcript 填入 Agent 输入框；
- 默认不保存音频。

### 简单 TDD

- Agent Pack 原子导入；
- 失败导入不替换当前版本；
- 文档检索；
- 图片 Artifact 关联；
- WebSocket partial/final；
- stop 后释放麦克风；
- 文字不会自动发送。

---

## Module 4：信息卡片成品与外部 Agent 接口

### 成品目标

用户批量确认后先获得可浏览的信息卡片成品；卡片浏览稳定后再加入 PNG 海报与 A2A/MCP。

### 实现范围

- 审核保留项到卡片的幂等生成；
- 六种浅青蓝文字封面与两种 HTML/CSS 底板；
- 原始封面优先、模板封面离线兜底；
- 月份、日期 Tab、左侧筛选和按需详情布局；
- 100～1000 字详情摘要上限；
- “采集到卡片详情”的 Playwright 闭环；
- 后续增量：Poster Graph、编辑器、PNG 渲染；
- A2A Agent Card 与三个 Skills；
- MCP Resources/Tools；
- OpenAPI 完善；
- 外部 Agent 策略；
- 导出与审计。

### 简单 TDD

- 未保留内容不能生成；
- 卡片重复生成幂等；
- 摘要上限和日期时区正确；
- 文字模板索引在 0～5 内且不依赖生图模型；
- A2A/MCP 无法绕过 Policy；
- 一个完整“采集到卡片详情”的 E2E；
- PNG 上线时再增加“采集到 PNG”的 E2E。

---

## 成品后的问题发现阶段

完成四个模块后再基于真实使用评估：

- 是否需要向量检索；
- 是否需要独立 Worker；
- 是否需要把 STT 拆成独立服务；
- 是否需要多用户/多工作区；
- 是否需要更多海报模板；
- 是否需要更复杂事件聚类；
- 是否需要独立插件系统。

没有真实问题支持时，不提前实施。
