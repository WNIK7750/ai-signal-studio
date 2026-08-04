# speech_to_text 第三方工具区

本目录只用于实时语音转文字的第三方实现。

默认候选：`whisperlive/`。

应用自有接口位于未来代码目录：

```text
packages/application/.../realtime_speech_to_text.py
packages/adapters/speech_to_text/whisperlive_adapter.py
apps/api/.../websockets/transcription.py
apps/web/.../features/transcription/
```

第三方工具升级不得改变上层 `TranscriptEvent` 契约。
