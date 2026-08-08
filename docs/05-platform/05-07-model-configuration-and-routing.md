# 05-07 模型配置与对话路由

## 1. 产品边界

第一版提供工作区级模型管理，不建设账号系统、Provider 市场或远程密钥服务。

- 对话页负责切换当前模型，并提供“设定模型”跳转；
- 模型设置页负责创建、编辑、软删除模型，复用提供商、查看能力和切换工作区默认模型，但不占用左侧一级导航；
- 对话页可以为当前会话临时选择模型；
- Provider 保存 API 地址和密钥引用，多个模型可以复用同一个 Provider；
- 新建外部模型必须填写 API Key，或选择一个已经配置密钥的 Provider；不允许保存必然不可调用的空配置；
- 模型保存显示名称、模型 ID、能力声明和最大输出额度；
- 外部模型可被显式设为唯一“搜索模型”，通过 OpenAI 兼容 Responses
  `web_search` 补充网页来源；未选择时保留环境搜索 API 作为备用；
- API Key 写入独立的本地密钥文件，不写数据库、不进入模型文件、不返回前端；
- 当前支持 `heuristic` 与 `openai_compatible` 两类 Provider。

这套交互借鉴 CC Switch 的“Provider 预设/自定义配置 + 明确启用 + 手工模型 ID”，但按本项目的单机部署边界简化。CC Switch 将 Provider 作为可切换配置单元并保存在本地 SQLite；本项目改用可直接管理的 JSON 文件，并把密钥从普通模型参数中再次拆开。

添加模型弹窗内置首批 OpenAI 兼容地址预设：OpenAI / GPT、DeepSeek、阿里云百炼 / 千问。选择后立即填写当前官方 Base URL；地址仍可修改，以支持百炼地域地址、代理或自建网关。已保存的 Provider 直接复用其地址与密钥。

接口地址既接受 Provider Base URL，也接受完整的
`/chat/completions` 地址；运行时会规范化为单一请求地址，避免重复拼接路径。

## 2. 视觉能力校验

`supports_vision` 是部署者创建模型时确认的能力声明，后端不根据模型名称猜测。

```text
普通消息
→ 使用对话页所选模型
→ 未选择时使用工作区默认模型

包含图片的消息
→ 所选模型支持图片：继续使用
→ 所选模型不支持图片：保持当前模型，在助手输出区返回 MODEL-002
```

不能识图的模型保持可选，不禁用、不增加警告图标，只显示 `不支持识图` 文字标签。系统在任何情况下都不自动切换模型；工作区默认模型和对话临时模型只能由用户显式切换。

对话页使用本地文件选择器上传图片，第一版接受 PNG、JPEG 和 WebP；一次最多 4 张，单张最多 5 MB。浏览器读取为受限 Data URL 后随 Agent 请求发送，不写模型配置表。

对话 Composer 同时提供图片上传、模型选择、设定模型跳转和语音转文字。语音按钮调用浏览器 Speech Recognition 能力，将识别结果填入输入框，始终由用户再次确认并点击发送，不自动提交。

## 3. 本地文件与模型记录

运行时使用两个文件：

| 文件 | 内容 | Git |
| --- | --- | --- |
| `config/models.local.json` | Provider、模型、能力和默认项 | 忽略 |
| `config/model-secrets.local.json` | `api_key_ref` 对应的真实密钥 | 忽略 |

可复制的无密钥示例：

- `config/models.example.json`
- `config/model-secrets.example.json`

`AI_SIGNAL_MODEL_CONFIG_PATH` 与 `AI_SIGNAL_MODEL_SECRETS_PATH` 可以修改文件位置。后端每次读取时都以文件内容为准，因此部署者可以停服务后直接编辑；UI 保存使用同目录临时文件和原子替换，避免半写入文件。密钥文件创建后尽可能限制为当前系统用户读写。

旧的 `AI_SIGNAL_LLM_API_KEY`、`AI_SIGNAL_LLM_BASE_URL` 和 `AI_SIGNAL_LLM_MODEL` 保留为首次启动迁移入口：当本地模型文件不存在且环境 Provider 为 `openai_compatible` 时，首次启动会生成对应 Provider、模型与独立密钥文件。之后以本地文件为事实来源。

机器契约：

- `contracts/05-models/model-config.schema.json`
- `contracts/05-models/models.example.json`

关键字段：

| 字段 | 含义 |
| --- | --- |
| `name` | 工作区内唯一的显示名称 |
| `provider_id` | 引用的 Provider |
| `model_id` | 发送给 Provider 的模型标识 |
| `supports_vision` | 是否接受图片输入 |
| `output_token_limit` | 实际传给 Provider 的最大输出 Token；空值表示使用运行时默认 |
| `enabled` | 是否可用于选择 |
| `is_default` | 是否为工作区默认模型 |
| `is_search_model` | 是否承担原生联网搜索；同一工作区最多一个 |

同一工作区始终最多只有一个默认模型。创建首个模型时自动设为默认；显式切换时在一个事务中清除旧默认并设置新默认。

## 4. REST 契约

```text
GET  /api/models
GET  /api/providers
POST /api/models
PATCH /api/models/{model_id}
DELETE /api/models/{model_id}
POST /api/models/{model_id}/activate
POST /api/models/{model_id}/activate-search
POST /api/models/{model_id}/test
POST /api/agent-runs
```

`POST /api/agent-runs` 新增：

```json
{
  "message": "请分析这张图",
  "model_id": "model_local",
  "image_urls": ["data:image/png;base64,..."]
}
```

响应返回 `requested_model_id`、`effective_model_id` 与 `model_switched`。当前契约保留 `model_switched` 兼容字段，但产品规则要求它始终为 `false`。

## 5. 错误编号

面向用户的错误统一显示为 `报错编号（中文提示）`：

| 编号 | 提示 |
| --- | --- |
| `MODEL-001` | 未找到指定模型 |
| `MODEL-002` | 当前模型不支持图片 |
| `MODEL-003` | 模型配置不完整 |
| `MODEL-004` | 模型名称已存在 |
| `MODEL-005` | 模型服务调用失败 |
| `MODEL-006` | 模型返回内容无效 |
| `MODEL-007` | 内置模型不可修改 |
| `MODEL-008` | 内置模型无需连接测试 |
| `MODEL-009` | 当前模型不支持原生联网搜索 |
| `PROVIDER-001` | 未找到指定提供商 |
| `PROVIDER-002` | 提供商配置不完整 |
| `PROVIDER-003` | 接口地址或模型 ID 不可用 |
| `PROVIDER-004` | 模型服务请求超时 |
| `PROVIDER-005` | 模型服务请求受限 |
| `SECRET-001` | 模型密钥文件无法读取 |
| `SECRET-002` | 模型密钥文件无法写入 |
| `SECRET-003` | 请填写 API Key |
| `SECRET-004` | API Key 无效或无权限 |
| `IMAGE-001` | 仅支持 PNG、JPEG 和 WebP 图片 |
| `IMAGE-002` | 单张图片不能超过 5 MB |
| `IMAGE-003` | 一次最多上传 4 张图片 |
| `IMAGE-004` | 读取图片失败 |
| `VOICE-001` | 当前浏览器不支持语音转文字 |
| `VOICE-002` | 无法访问麦克风 |
| `VOICE-003` | 语音转文字失败 |
| `API-001` | 请求参数不正确 |
| `SYS-001` | 请求失败或本地服务不可用 |

模型管理 REST 错误使用相同显示文本；对话路由错误使用 HTTP 200 返回，并写入助手输出区，同时在 `result.error_code` 保留机器编号。

## 6. 验收行为

- 创建模型后立即出现在设置列表；
- 创建外部模型时必须具备 API Key，设置页可直接测试真实 Provider 连接；
- 可配置模型支持编辑，API Key 留空时保留原密钥；
- 删除使用二次确认和软删除；被删模型从设置及对话选择中消失，Provider 与密钥继续保留；
- 删除当前默认模型后回退到仍可用模型；内置本地模型不可编辑或删除；
- 可以为不同 Provider 保存不同密钥，也可以让多个模型复用一个 Provider；
- 已保存 Provider 在选择器中列出全部复用模型名称；外部模型可设为搜索模型；
- 模型与 Provider API 只返回 `has_api_key`，不返回密钥、掩码或末尾字符；
- 直接编辑本地模型文件后，下一次请求可以读取新配置；
- 设置页切换默认模型后只有一个 `is_default=true`；
- 对话页下拉项对非视觉模型显示文字标签，但仍可选择；
- 左侧导航不增加独立模型入口，对话 Composer 可跳转到模型设置；
- 对话页可以选择本地图片、显示缩略图并在发送前移除；
- 对话页可以点击麦克风把语音填入输入框，且不会自动发送；
- 非视觉模型携图时保持原选择，助手输出 `MODEL-002（当前模型不支持图片）`；
- 视觉模型携图时图片只发送给用户当前所选模型；
- 数据库和 API 响应中不出现 API Key。

## 7. 当前生效配置与预留能力

设置页只展示已经接入运行时的选项：

- `图片输入`：影响上传校验和模型调用；
- `最大输出`：写入 OpenAI 兼容请求的 `max_tokens`。

工具调用、Provider 推理参数和自定义协议尚未实现，因此不在 UI、REST 响应或机器契约中暴露。等对应 Adapter 能实际消费并有测试后再增加，避免出现只保存但不生效的空壳选项。旧本地 JSON 中存在这些字段时会被忽略。
