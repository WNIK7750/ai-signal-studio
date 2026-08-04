# WhisperLive 集成设计

## 目标

使用 WhisperLive 提供近实时转写能力，不将其内部 API 暴露给业务层。

## 边界

```text
Browser microphone
→ AI Signal WebSocket
→ WhisperLiveAdapter
→ WhisperLive server
→ normalized TranscriptEvent
```

## 推荐模式

第一版优先让 WhisperLive 作为独立本地进程运行。API 进程持有 Provider Client，并把统一会话映射到 WhisperLive 客户端会话。

## Adapter 责任

- 创建/关闭 Vendor Session；
- 转换音频格式；
- 将 Vendor partial/final 结果映射到统一事件；
- 处理超时、断线和重连；
- 隐藏 Vendor 特有字段；
- 暴露健康检查。

## 不应做

- 不在业务模块 import WhisperLive 内部类；
- 不在前端直接连接 Vendor 服务；
- 不把 Vendor 异常原样泄露给用户；
- 不默认存储音频；
- 不在上游源码中写本项目业务规则。

## TDD Fake

实现 `FakeRealtimeSpeechToTextProvider`，给定音频 chunk 序列后按脚本返回 partial/final 事件。日常测试不启动真实模型。
