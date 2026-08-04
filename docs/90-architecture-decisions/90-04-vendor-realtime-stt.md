# ADR-0004：实时语音转文字采用隔离的第三方工具

状态：Accepted

## 决策

浏览器实时麦克风通过 WebSocket 转写；默认候选 WhisperLive。第三方实现位于 `vendor_tools/speech_to_text/`，业务通过 RealtimeSpeechToTextProvider 调用。

## 原因

实时 Whisper 涉及分块、VAD、延迟策略和硬件适配，不应在本项目重新实现。

## 后果

需要维护统一事件协议、Adapter、许可证说明和版本固定；默认不保存原始音频。
