# 07-02 实践来源与项目取舍

本文记录采用了哪些优秀实践，以及为什么没有完整照搬。

## LangChain

采用：

- Tool 使用结构化输入输出；
- Pydantic Schema；
- 动态工具集合；
- Agent 作为能力调用者。

取舍：

- 业务逻辑不放在 Tool 内；
- 不把每个操作都交给自由 Agent 决策。

参考：

- https://docs.langchain.com/oss/python/langchain/tools
- https://docs.langchain.com/oss/python/langchain/structured-output

## LangGraph

采用：

- subgraph；
- persistence/checkpoint；
- interrupt/resume；
- 并行 map-reduce；
- time travel 用于调试。

取舍：

- 普通 CRUD 不进入 Graph；
- State 不保存大文件和完整正文；
- 副作用节点必须幂等。

参考：

- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://docs.langchain.com/oss/python/langgraph/persistence
- https://docs.langchain.com/oss/python/langgraph/use-subgraphs
- https://docs.langchain.com/oss/python/langgraph/use-time-travel

## FastAPI WebSocket

采用：

- WebSocket 双向传输二进制、文本和 JSON；
- 依赖注入与鉴权；
- TestClient 测试 WebSocket。

取舍：

- WebSocket 契约额外维护 JSON Schema，而不是期待 OpenAPI 自动表达。

参考：

- https://fastapi.tiangolo.com/advanced/websockets/
- https://fastapi.tiangolo.com/advanced/testing-websockets/

## 浏览器音频

采用：

- getUserMedia 获取麦克风；
- MediaRecorder 作为 MVP 音频分块；
- 需要 raw PCM 时再使用 AudioWorklet。

参考：

- https://developer.mozilla.org/en-US/docs/Web/API/MediaStream_Recording_API/Using_the_MediaStream_Recording_API
- https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder

## WhisperLive / Whisper-Streaming

采用：

- 不自行从零构建实时 Whisper 分块算法；
- 第三方工具放入独立 vendor 目录；
- 通过 Provider Protocol 隔离；
- 将“近实时”作为第一版目标。

参考：

- https://github.com/collabora/WhisperLive
- https://github.com/ufal/whisper_streaming
- https://github.com/SYSTRAN/faster-whisper

## Docling

采用：

- 复杂文档转换到统一表示的思路；
- 作为可选 Adapter。

取舍：

- Markdown、YAML、JSON 等轻量格式不经过重型解析；
- 不让 Docling 成为系统启动硬依赖。

参考：

- https://docling-project.github.io/docling/
- https://docling-project.github.io/docling/usage/supported_formats/

## MCP

采用：

- Resources 暴露架构、契约、Agent Pack 与运行记录；
- Tools 调用原子能力；
- 输入输出 Schema、错误与审计。

取舍：

- MCP 不绕过 Capability Policy；
- 不把长任务拆成大量低层 Tool 调用。

参考：

- https://modelcontextprotocol.io/specification/2025-11-25
- https://modelcontextprotocol.io/specification/2025-11-25/server/tools

## A2A

采用：

- Agent Card；
- 有状态 Task；
- 高层 Skill；
- 流式任务状态。

取舍：

- 第一版只实现少量结果导向 Skills；
- 原子操作留给 MCP/REST；
- Agent Card 不放密钥或内部实现。

参考：

- https://a2a-protocol.org/latest/
- https://a2a-protocol.org/dev/specification/

## Provider 与本地密钥

采用：

- 借鉴 CC Switch 以 Provider 为复用和切换单元，而不是让每个模型重复保存相同地址与密钥；
- 普通模型参数与本地密钥文件分离；
- Git 忽略密钥文件、限制文件权限、接口不回显密钥；
- 为 OpenAI / GPT、DeepSeek、阿里云百炼 / 千问提供官方 OpenAI 兼容地址预设。

取舍：

- 单用户本地部署优先可直接编辑的 JSON，不引入远程 Secret Manager；
- 不在前端源码、普通模型文件或数据库中保存 API Key；
- 密钥文件不承诺抵御已经取得本机用户权限的攻击者；多人或公网部署应迁移到系统凭据库或专用 Secret Manager。

参考：

- https://github.com/farion1231/cc-switch
- https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- https://platform.openai.com/docs/api-reference/models/object
- https://api-docs.deepseek.com/zh-cn/guides/function_calling/
- https://help.aliyun.com/zh/model-studio/base-url
