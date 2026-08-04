# AI Signal Studio

AI Signal Studio 是一个本地部署、可自行配置的模块化 AI 信息工作台。系统能够定时或按需收集 AI 相关信息，生成按日期组织的信息流；内置 Workspace Agent 与界面共用相同能力，并可直接维护常用方案和定时任务。

当前仓库已经具备第一版可运行闭环：Next.js 前端、FastAPI 模块化后端、SQLite 本地数据、采集与去重、AI 信息筛选、批量审核、封面卡片浏览、对话 Agent、工作区模型切换、常用方案、每日定时、运行记录和主题定制。外部互操作、实时转写与 PNG 海报渲染继续按模块迭代。

## 开始阅读

1. [AGENTS.md](AGENTS.md)：项目内 Agent 和开发者必须遵守的工作约束。
2. [docs/README.md](docs/README.md)：按模块编号的完整文档导航。
3. [docs/00-project/00-01-project-charter.md](docs/00-project/00-01-project-charter.md)：产品目标、成功标准与非目标。
4. [docs/07-delivery/07-01-development-roadmap.md](docs/07-delivery/07-01-development-roadmap.md)：四个模块的实施顺序。
5. [docs/05-platform/05-04-ui-layout-and-components.md](docs/05-platform/05-04-ui-layout-and-components.md)：Codex 式应用壳、场景化页面布局与组件分类。

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

## 本地运行

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
刷新页面会恢复消息和 Capability 执行状态；图片只记录数量，不保存图片内容。

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

## 当前范围

第一版已贯通模块 01、审核工作台和卡片浏览核心闭环。Review Graph 的暂停恢复、Approval Token、实时转写、PNG 渲染和外部 A2A/MCP 仍按 [07-01 开发路线图](docs/07-delivery/07-01-development-roadmap.md) 继续推进。
