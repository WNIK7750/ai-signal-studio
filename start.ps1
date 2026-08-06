$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$launcher = Join-Path $projectRoot "scripts\start_app.py"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "[ERROR] Runtime missing. Run setup.cmd first."
    exit 1
}

try {
    & $python $launcher @args
    exit $LASTEXITCODE
}
catch {
    Write-Host "[ERROR] Launcher failed. See logs."
    exit 1
}
