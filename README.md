# AI Signal Studio

AI Signal Studio 是一个本地部署、可自行配置的模块化 AI 信息工作台。系统能够定时或按需收集 AI 相关信息，生成按日期组织的信息流；内置 Workspace Agent 与界面共用相同能力，并可直接维护常用方案和定时任务。

当前仓库已经具备可运行的桌面闭环：Next.js 前端、FastAPI 模块化后端、
SQLite 本地数据、版本化采集任务、真实试运行、定时调度、采集与去重、
统一 AI 信息库、已读/收藏/归档、保存视图、批量审核、封面卡片浏览、
可持久化对话 Agent、结构化任务草稿、来源健康、双状态运行记录、
工作区模型切换、主题定制、Agent Pack、Artifact、实时语音转写，以及经过双重审批的
PNG 海报编辑与导出。外部 Agent Gateway 仍是延后设计项，不随本地产品发布启用。

## 开始阅读

1. [AGENTS.md](AGENTS.md)：项目内 Agent 和开发者必须遵守的工作约束。
2. [docs/README.md](docs/README.md)：按模块编号的完整文档导航。
3. [docs/00-project/00-01-project-charter.md](docs/00-project/00-01-project-charter.md)：产品目标、成功标准与非目标。
4. [docs/07-delivery/07-01-development-roadmap.md](docs/07-delivery/07-01-development-roadmap.md)：四个模块的实施顺序。
5. [docs/07-delivery/07-04-optimization-implementation-status.md](docs/07-delivery/07-04-optimization-implementation-status.md)：最新蓝图的已实现范围、新增任务和下一批边界。
6. [docs/05-platform/05-04-responsive-layout.md](docs/05-platform/05-04-responsive-layout.md)：桌面优先的动态布局约束。

准备实现某个模块时，直接进入对应编号目录：

| 模块 | 目标 | 文档入口 |
| --- | --- | --- |
| 01 | AI 信息与采集 | [01-module-timeline](docs/01-module-timeline/01-00-overview.md) |
| 02 | 审核工作台与 Workspace Agent | [02-module-review-agent](docs/02-module-review-agent/02-00-overview.md) |
| 03 | Agent Pack、Artifact 与实时转写 | [03-module-agent-assets-stt](docs/03-module-agent-assets-stt/03-00-overview.md) |
| 04 | 信息卡片与后续外部接口 | [04-module-poster-interop](docs/04-module-poster-interop/04-00-overview.md) |

## 最高级开发原则

1. **先做成品，再根据真实问题收紧边界。** 按模块交付可使用的前后端闭环，不先建设大型平台底座。
2. **简单 TDD。** 每个模块先写少量关键失败测试，再做最小实现，通过后小步重构。
3. **统一能力入口。** 用户端、内置 Agent、LangGraph、REST、MCP、A2A 和测试脚本调用同一套 Application Capability。
4. **模块化单体优先。** 前后端分离；后端内部低耦合，但在出现明确运行压力前不拆微服务。
5. **Agent 可使用应用全部功能。** 能力开关、权限、额度与人工确认决定某个 Agent 在某次执行中能否调用，而不是为 Agent 另写一套功能。
6. **文档驱动客制化。** Agent 身份、提示词、偏好、知识和长期记忆保存在可导入、可编辑、可版本控制的 Agent Pack 文档中。
7. **第三方工具隔离。** 引入的现成工具统一放在 `vendor_tools/`；业务代码只依赖我们定义的适配接口。
8. **语音仅做实时语音转文字。** 浏览器实时采集麦克风，通过 WebSocket 转写为可编辑文本；不以“上传音频文件”为主要产品路径。
9. **不建设登录系统。** 软件按单工作区本地部署，设置和主题保存在部署实例或当前浏览器，不引入账号、个人版或登录入口。

## 仓库结构

```text
.
├── AGENTS.md                     # 开发与 Agent 工作约束
├── apps/web/                     # Next.js 产品界面
├── apps/api/                     # FastAPI 模块化后端
├── docs/                         # 按 00～07、90、99 编号的设计文档
├── contracts/                    # 按能力域分类的机器可读契约
├── graph-specs/                  # 与模块号对齐的 LangGraph 规格
├── prompts/                      # 与模块号对齐的实施提示词
├── agent-packs/                  # 文档化 Agent Pack 示例
├── vendor_tools/                 # 第三方工具隔离区
└── tests/                        # 后端、能力和契约测试
```

## 使用方式

- 新对话中的编程 Agent：先阅读 `AGENTS.md`，再读取当前模块的 `XX-00-overview.md`。
- 实现前：运行现有测试，新增当前模块最关键的失败测试。
- 实现后：运行模块测试、契约测试和一个端到端冒烟测试。
- 修改 Schema：同步更新 `contracts/`、示例、测试和变更记录。

## Windows 11 安装与一键启动

```powershell
# 首次安装：双击 setup.cmd，或在终端运行
.\scripts\bootstrap.ps1

# 一键启动：双击 start.cmd；终端中也可运行
.\start.ps1
```

初始化脚本不依赖全局安装的 pnpm：它会优先使用正确版本的 pnpm，
否则通过 Corepack（或 npx 后备）在项目 `.tools/` 中准备锁定版本。
`start.cmd` 在启动失败时会保留窗口，并以
`报错编号（中文提示）` 显示原因；应用已经运行时，再次双击只会打开现有页面。

项目版本以根目录 `VERSION` 为统一基线，Python 版本记录在
`.python-version`，Node 版本记录在 `.node-version`。Python 依赖锁定在
`requirements.lock`，Web 依赖锁定在 `pnpm-lock.yaml`。完成修改后可运行：

```powershell
# 后端、契约、前端测试、检查与生产构建
.\scripts\verify.ps1

# 额外运行桌面端端到端流程
.\scripts\verify.ps1 -E2E

# 清理可重建缓存、测试产物和旧 Playwright 数据
.\scripts\clean.ps1
```

脚本固定使用项目 `.venv` 启动 API。开发模式会监控后端源码并自动重载；
如果 3000 或 8000 端口已被旧实例占用，脚本会明确报错而不会把新前端连接到
旧后端。脚本就绪后会打开 `http://127.0.0.1:3000`。终端只显示服务状态；
按 `Ctrl+C` 同时停止 API 与 Web。传入 `--no-browser` 可禁止自动打开浏览器，
已有生产构建时可传入 `--production`。页面采用弹性 Grid 与 `minmax()`
分配空间，优先适配不同电脑窗口宽度；手机端专项布局留到最终验收阶段。

普通工作区首次启动会准备 OpenAI 官方 RSS、LangGraph Releases 和
Transformers Releases 三个真实来源；来源可以在设置页停用或继续添加。
固定 Demo 数据仅用于自动化测试。Workspace Agent 对话保存在本地 SQLite，
刷新页面会恢复消息和 Capability 执行状态。上传的文档和图片先经类型、Magic Bytes、
大小与 Digest 校验后保存为本地 Artifact；消息和 Graph State 只保存 Artifact ID。

首次运行默认使用离线 `heuristic` Provider，API Key 为空。没有配置模型时，时间线、
筛选、来源、任务、审核、卡片和确定性研究功能仍可使用；配置支持 Tool Calling 的模型
后，无需修改源码即可使用自然语言 Workspace Agent。

## 接入真实 API Key

Python 依赖安装在 `.venv/`。不要把密钥写进 `.venv`、源码、前端变量或文档。

1. 运行 `.\start.ps1`；
2. 在对话页点击“设定模型”进入 `/settings/models`；
3. 选择 Provider 预设，填写 API Key、模型 ID 与能力；
4. 保存后确认模型显示“密钥已配置”；
5. 点击模型行的连接图标执行真实连接测试。

工作区模型密钥保存在 Git 忽略的
`config/model-secrets.local.json`，模型信息保存在
`config/models.local.json`；两者都不会由 API 返回明文。
`.env` 中的旧 `AI_SIGNAL_LLM_*` 字段只用于首次迁移兼容。
搜索和 GitHub 密钥仍通过根目录 `.env` 配置。

## 本地数据、备份与重置

以下目录和文件只属于当前设备，并已被 Git 与发布 Guard 排除：

```text
.env
config/models.local.json
config/model-secrets.local.json
data/
logs/
exports/
backups/
agent-packs/local/
```

Agent Pack 的版本化示例位于 `agent-packs/examples/`；首次运行会复制到
`data/agent-packs/`，运行时编辑不会改写仓库示例。Artifact、SQLite 数据、Checkpoint
和转写会话也只保存在 `data/`。默认不保存原始麦克风音频。

备份前先停止应用，然后复制 `.env`、`config/*.local.json` 与 `data/` 到受保护位置。
重置时同样先停止应用，再自行备份并删除这些本地路径；下次启动会恢复安全默认。仓库
不会主动上传 API Key、本地数据库、Agent Pack、对话、来源、任务、Artifact 或日志。

## 发布与安全检查

```powershell
.\.venv\Scripts\python.exe scripts/check_release_safety.py --worktree
.\.venv\Scripts\python.exe scripts/check_release_safety.py --tracked
.\.venv\Scripts\python.exe scripts/check_release_safety.py --history
```

Guard 只报告规则、文件和行号，不回显疑似 Secret。Gitleaks 的固定版本 pre-commit 与
完整历史 GitHub Action 是第二道独立门禁。仓库当前未包含 LICENSE；公开分发前需要由
仓库所有者选择许可证。

## 当前范围

任务、统一信息库、审核工作台、卡片/海报、可恢复 Workspace Agent、Agent Pack、
Artifact 与实时转写已经形成桌面核心闭环。E5 外部 A2A/MCP Agent Gateway 继续
Deferred；它不会因本地 Poster Graph 完成而自动开放。最新验证证据见
[07-04 实现状态](docs/07-delivery/07-04-optimization-implementation-status.md)。
