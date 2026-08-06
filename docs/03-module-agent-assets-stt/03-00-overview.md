# 03-00 模块总览：Agent Pack、Artifact 与实时转写

## 成品目标

用户可以导入和编辑 Agent Pack，上传文档与图片供 Agent 使用，并在 Agent 输入框中持续说话得到可编辑文字。

## 核心闭环

```text
导入 Agent Pack / Artifact → 校验、存储与索引 → 按需提供给 Agent
麦克风输入 → WebSocket 增量转写 → 可编辑文字 → 用户手动发送
```

## 本模块范围

- Agent Pack ZIP 导入导出、版本与原子激活；
- Markdown、YAML、JSONL 校验和 SQLite FTS；
- 本地 Artifact Storage、文档解析、图片 OCR/Vision Adapter；
- WhisperLive 的隔离集成；
- FastAPI WebSocket 与 `RealtimeTranscriptionInput`；
- final transcript 填入输入框，默认不保存原始音频。

## 必读资料

1. [03-01 Agent Pack 与长期记忆](03-01-agent-pack-and-memory.md)
2. [03-02 数据、Artifact 与图片](03-02-data-artifacts-and-images.md)
3. [03-03 实时语音转文字](03-03-realtime-speech-to-text.md)
4. [06-03 安全与审批](../06-quality-operations/06-03-security-and-approval.md)

## 机器资料

- [Agent Pack Schema](../../contracts/02-agent-pack/agent-pack.schema.json)
- [实时转写协议 Schema](../../contracts/03-realtime-transcription/realtime-transcription-protocol.schema.json)
- [Agent Pack 示例](../../agent-packs/examples/ai-editor/agent.yaml)
- [实时转写实施提示词](../../prompts/03-module-agent-assets-stt/03-realtime-stt-coding-agent-prompt.md)
- [WhisperLive 集成边界](../../vendor_tools/speech_to_text/whisperlive/INTEGRATION.md)

## 完成证据

- 失败导入不替换当前 Agent Pack；
- 文档和图片能通过 Artifact ID 关联与检索；
- WebSocket 正确处理 partial、final、错误与 stop；
- 组件卸载或结束时释放麦克风和连接；
- 转写文字未经用户操作不会自动发送给 Agent。

## 2026-08-06 实施证据

- ZIP 导入、Diff、原子激活、版本编辑/回退、选择性导出和 SQLite FTS 已共用
  `AgentPackService`；
- Artifact 使用本地 Digest 去重、Magic Bytes 与大小边界；图片发送给 Agent 前先保存
  Artifact，消息只记录 Artifact ID 和图片数量；
- `RealtimeTranscriptionProvider`、Fake Provider、短时单会话 Token、WebSocket
  partial/final/error/stop 与 MediaRecorder 资源释放已完成；
- 普通测试和 Playwright 只使用 Fake 转写，不启动 WhisperLive 或真实模型；
- Module 3 目标测试 `5 passed`，完整 Playwright 中 Agent Pack、Artifact 与转写流程
  均通过。
