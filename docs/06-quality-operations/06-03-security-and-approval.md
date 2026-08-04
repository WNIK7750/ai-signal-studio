# 06-03 安全与审批

## 1. 安全边界

- 用户浏览器；
- FastAPI；
- 内置 Agent；
- 外部 A2A/MCP Client；
- 第三方搜索/LLM/STT 服务；
- 本地 Artifact 与 Agent Pack 文件。

## 2. 高风险能力

默认需要确认或禁用：

- 物理删除；
- 对外发布；
- 批量渲染大量卡片；
- 修改能力开关；
- 激活新 Agent Pack；
- 将观察写入正式长期记忆；
- 覆盖用户编辑内容；
- 调用有费用的高额度外部服务。

## 3. Approval Token

Token 绑定：

- user_id；
- capability_id；
- input_digest；
- workspace_id；
- expires_at；
- single_use。

Agent 不可把一次确认用于不同输入。

## 4. WebSocket

- 短时连接 token；
- 校验 Origin；
- 限制消息大小；
- 限制连接时长与数量；
- 断线清理 Provider 会话；
- UI 清晰显示麦克风状态；
- stop 时关闭所有 MediaStreamTrack。

## 5. Prompt 与外部内容

采集到的网页、Agent Pack 文档和 MCP Resource 都视为不可信输入：

- 不把网页中的指令当系统指令；
- 工具权限由执行层决定；
- 外部内容只进入受限的数据字段；
- 输出发布前可要求用户确认；
- URL、文件名、MIME 和大小严格校验。

## 6. Secrets

- 不写入 Agent Pack；
- 不写入 Agent Card；
- 不提交仓库；
- 使用环境变量或 Git 忽略的本地 secret store；
- 日志脱敏。

### 6.1 本地配置边界

- 初始部署密钥可以写入仓库根目录的 `.env`；该文件已被 Git 忽略；
- 多 Provider 模型密钥写入 `config/model-secrets.local.json`，普通模型参数写入 `config/models.local.json`，两者均被 Git 忽略；
- 密钥文件仅使用 `api_key_ref` 与 Provider 关联，前端和普通模型文件不保存明文；
- 密钥 API 只返回 `has_api_key`，不回显掩码、末尾字符或原值；空 Key 表示保留已保存值；
- 本地写入使用临时文件后原子替换，密钥文件尽可能限制为当前系统用户读写；
- 非本机部署必须由 HTTPS 反向代理保护模型配置接口，不通过公网明文 HTTP 提交密钥；
- `.env.example` 只保存空值和非敏感默认值；
- 前端 `apps/web/.env*` 只允许公开配置，严禁出现 LLM、搜索或 GitHub 密钥；
- 业务模块、Capability、Agent Tool 和定时任务不得直接调用 `os.getenv()`；
- 所有 Provider 配置经 `ai_signal_api.config.Settings` 读取，再由 `integrations/` Adapter 解析；
- `SecretStr` 用于内存中的密钥字段，健康检查只返回是否配置，不返回原值；
- 测试必须显式使用离线 `heuristic` Provider，避免读取开发者真实密钥或产生费用。

### 6.2 预留变量

| 变量 | 用途 | 是否可为空 |
| --- | --- | --- |
| `AI_SIGNAL_LLM_PROVIDER` | `heuristic` 或 `openai_compatible` | 否 |
| `AI_SIGNAL_LLM_API_KEY` | LLM Provider 密钥 | 离线模式可为空 |
| `AI_SIGNAL_LLM_BASE_URL` | OpenAI 兼容 API 根地址 | 否 |
| `AI_SIGNAL_LLM_MODEL` | 部署者选择的模型 ID | 离线模式可为空 |
| `AI_SIGNAL_MODEL_CONFIG_PATH` | 本地 Provider 与模型文件路径 | 否 |
| `AI_SIGNAL_MODEL_SECRETS_PATH` | 本地 Provider 密钥文件路径 | 否 |
| `AI_SIGNAL_SEARCH_API_KEY` | 后续搜索 Adapter | 可为空 |
| `AI_SIGNAL_GITHUB_TOKEN` | GitHub 限额提升与私有来源 | 可为空 |

只有在 `LLM_PROVIDER=openai_compatible` 且 API Key、模型均存在时，
LLM 才被视为已配置。缺失配置返回 `LLM_PROVIDER_NOT_CONFIGURED`，
不得静默回退并产生难以定位的结果差异。
