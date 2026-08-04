# Module 3 实时语音转文字实施提示词

先阅读：

- `AGENTS.md`
- `docs/03-module-agent-assets-stt/03-00-overview.md`
- `docs/03-module-agent-assets-stt/03-03-realtime-speech-to-text.md`
- `contracts/03-realtime-transcription/realtime-transcription-protocol.schema.json`
- `vendor_tools/speech_to_text/README.md`
- `vendor_tools/speech_to_text/whisperlive/INTEGRATION.md`

## 目标

在 Workspace Agent 输入框中实现实时麦克风输入，持续转写为可编辑文字。停止转写后文字保留，但不得自动发送给 Agent。

## 实施顺序

1. 写 Fake Provider 与 WebSocket 契约测试；
2. 实现 Transcription Session Application Service；
3. 实现 FastAPI Session REST 与 WebSocket；
4. 实现前端 RealtimeTranscriptionInput；
5. 使用 Fake 完成 E2E；
6. 在 `vendor_tools/speech_to_text/whisperlive` 固定上游版本；
7. 实现 WhisperLiveAdapter；
8. 添加真实 Provider 的手动集成测试。

## 约束

- 默认不保存音频；
- 第三方工具只能放在 vendor_tools；
- 前端不直连 WhisperLive；
- 业务层不 import WhisperLive 内部模块；
- stop/unmount 必须关闭 MediaStreamTrack 与 WebSocket；
- partial 可被修订，final 不可被后续 partial 覆盖；
- 使用短时连接 token；
- 不实现语音合成或语音 Agent 通话。
