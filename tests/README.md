# 测试目录说明

建议正式代码中的测试布局：

```text
tests/
├── contract/
│   ├── test_capability_manifests.py
│   ├── test_agent_pack_schema.py
│   └── test_transcription_protocol.py
├── modules/
│   ├── collection/
│   ├── review/
│   ├── poster/
│   └── realtime_transcription/
├── integration/
│   ├── test_api_capabilities.py
│   ├── test_graph_resume.py
│   └── test_whisperlive_adapter_manual.py
└── e2e/
    ├── timeline.spec.ts
    ├── agent-review.spec.ts
    ├── transcription.spec.ts
    └── poster.spec.ts
```

## 实时转写测试注意

自动化测试使用 Fake Provider 和虚拟/预制音频 chunk，不依赖真实麦克风与模型。真实 WhisperLive 测试标记为 manual/integration，不进入普通快速测试。

## 真实模型额度保护

- 单元、模块、契约、Graph、API、组件和普通 Playwright 只使用 Fake、Fixture 或 HTTP
  Mock；
- 本机已经保存真实模型不构成测试授权；
- 普通测试命令不得读取真实模型密钥或访问模型 Provider；
- 真实模型只允许放在未来独立的 `tests/live/` 完整链路验收中；
- 该入口必须同时要求显式 `live_model` 标记与
  `AI_SIGNAL_RUN_LIVE_MODEL_TESTS=1`，缺一即跳过；
- 每次只运行一个完整用户链路，不为单个模块或 Provider 做额度 Smoke。
