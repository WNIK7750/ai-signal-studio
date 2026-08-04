$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$launcher = Join-Path $projectRoot "scripts\start_app.py"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "[ERROR] E1001（后端虚拟环境不存在）请先运行 setup.cmd"
    exit 1
}

try {
    & $python $launcher @args
    exit $LASTEXITCODE
}
catch {
    Write-Host "[ERROR] E1099（启动脚本执行失败）"
    Write-Host $_.Exception.Message
    exit 1
}
