# speech_to_text 第三方工具区

本目录只用于实时语音转文字的第三方实现。

默认候选：`whisperlive/`。

应用自有接口与隔离 Adapter 位于：

```text
apps/api/src/ai_signal_api/modules/agent_assets/transcription.py
apps/api/src/ai_signal_api/routers/agent_assets.py
apps/web/src/features/agent/agent-screen.tsx
vendor_tools/speech_to_text/whisperlive/adapter.py
```

第三方工具升级不得改变上层 `TranscriptEvent` 契约。
