$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$requirements = Join-Path $projectRoot "requirements.lock"
$pnpm = Join-Path $projectRoot "scripts\pnpm.ps1"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "[SETUP] Creating Python 3.12 virtual environment"
    $pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if (-not $pythonLauncher) {
        Write-Host "[ERROR] E1101（未找到 Python 3.12）"
        exit 1
    }
    & $pythonLauncher.Source -3.12 -m venv (Join-Path $projectRoot ".venv")
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] E1102（创建后端虚拟环境失败）"
        exit $LASTEXITCODE
    }
}

Write-Host "[SETUP] Installing locked Python dependencies"
& $python -m pip install --requirement $requirements
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] E1103（安装后端依赖失败）"
    exit $LASTEXITCODE
}
& $python -m pip install --editable $projectRoot --no-deps
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] E1104（安装项目后端失败）"
    exit $LASTEXITCODE
}

Write-Host "[SETUP] Installing locked web dependencies"
Push-Location $projectRoot
try {
    & $pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] E1105（安装前端依赖失败）"
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}

Write-Host "[READY] Development environment"
