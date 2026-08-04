# 03-01 Agent Pack 与长期记忆

## 1. 目标

Agent 的可客制化部分不写死在后端代码或仅存在数据库中，而是使用可导入、可编辑、可版本控制的 Agent Pack。

## 2. 目录格式

```text
agent-packs/<agent-id>/
├── agent.yaml
├── system.md
├── behavior.md
├── capabilities.yaml
├── source-policy.yaml
├── scoring-policy.yaml
├── poster-style.md
├── memory/
│   ├── profile.md
│   ├── preferences.md
│   ├── facts.md
│   ├── decisions.md
│   └── observations.jsonl
├── knowledge/
│   ├── topics.md
│   ├── trusted-sources.yaml
│   └── terminology.md
└── examples/
    ├── good-summary.md
    └── poster-examples.json
```

## 3. 事实来源

```text
Agent Pack 文件 = 事实来源
数据库 = 版本、引用、导入状态、权限和索引状态
全文/向量索引 = 可重建派生数据
```

## 4. 两类长期记忆

### 声明式记忆

用户明确编写或导入的偏好、事实和决策。加载时优先级高。

### 观察记忆

Agent 从用户审核行为中总结出的候选观察。默认写入 `observations.jsonl`，状态为 `pending_confirmation`；只有用户确认后才合并到正式文档。

## 5. 导入过程

```text
读取目录/ZIP
→ 校验 agent.yaml 与 Schema
→ 校验必需文件
→ 计算内容摘要
→ 保存版本快照或文件引用
→ 解析 Markdown/YAML/JSONL
→ 更新检索索引
→ 激活版本
```

导入必须是原子操作：失败不替换当前激活版本。

## 6. 修改方式

- UI 表单修改常用配置；
- 内置文本编辑器修改 Markdown/YAML；
- ZIP 导入导出；
- 代码 Agent 直接修改仓库中的 Agent Pack；
- 导入前显示差异。

## 7. 检索

第一版使用：

- 文件路径与标题索引；
- SQLite FTS；
- 标签和简单关键词；

只有真实使用显示语义召回不足时再增加向量索引。不要把向量数据库作为第一版前置条件。

## 8. 上下文组装

Agent 每次运行按需加载：

1. system.md；
2. behavior.md；
3. 与当前任务相关的 capability 配置；
4. 相关偏好和长期记忆片段；
5. 相关知识文档；
6. 少量示例。

不得无条件将整个 Agent Pack 塞入上下文。

## 9. 版本与审计

记录：

- pack_id/version；
- content_digest；
- imported_by；
- imported_at；
- previous_version；
- validation_result；
- activated_at。
