# AI Signal Studio Web

本目录是 AI Signal Studio 的 Next.js 桌面端界面。依赖版本和一键命令由仓库根目录统一管理，不在本目录单独使用 npm、yarn 或 bun。

在仓库根目录运行：

```powershell
# 首次准备环境
.\scripts\bootstrap.ps1

# 启动完整应用
.\start.ps1

# 仅运行前端测试、检查或构建
.\scripts\pnpm.ps1 --dir apps/web test
.\scripts\pnpm.ps1 --dir apps/web lint
.\scripts\pnpm.ps1 --dir apps/web build
```

项目整体说明见根目录 `README.md`，前端架构、布局、主题和图标约束见 `docs/05-platform/`。
