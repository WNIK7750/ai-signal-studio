# 00-05 推荐代码仓库布局

```text
ai-signal-studio/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── package.json
├── pnpm-workspace.yaml
├── apps/
│   ├── api/
│   │   └── src/ai_signal_api/
│   │       ├── main.py
│   │       ├── dependencies.py
│   │       ├── routers/
│   │       └── websockets/
│   └── web/
├── packages/
│   ├── domain/src/ai_signal_domain/
│   ├── application/src/ai_signal_application/
│   ├── contracts/src/ai_signal_contracts/
│   ├── orchestration/src/ai_signal_orchestration/
│   ├── agent_runtime/src/ai_signal_agent_runtime/
│   ├── adapters/src/ai_signal_adapters/
│   └── shared/src/ai_signal_shared/
├── modules/
│   ├── collection/
│   ├── intelligence/
│   ├── review/
│   ├── poster/
│   ├── memory/
│   ├── artifacts/
│   └── realtime_transcription/
├── agent-packs/
├── capability-manifests/
├── graph-specs/
├── vendor_tools/
│   └── speech_to_text/
│       └── whisperlive/
├── contracts/
├── migrations/
├── scripts/
├── tests/
│   ├── contract/
│   ├── modules/
│   ├── integration/
│   └── e2e/
└── docs/
```

## 布局说明

- `modules/` 可以先作为业务模块的组合目录；
- `packages/` 保存真正跨模块的稳定层；
- 不必第一天拆成多个可发布 Python package；可先使用单个 uv workspace 或单项目路径依赖；
- 当边界稳定后再物理拆包；
- `vendor_tools/` 绝不放自己的领域逻辑；
- 示例契约与正式代码生成的 Schema 保持同步。
