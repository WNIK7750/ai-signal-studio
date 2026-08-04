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
