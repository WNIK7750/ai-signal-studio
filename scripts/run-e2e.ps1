$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$runner = Join-Path $PSScriptRoot "run_e2e.py"

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "[ERROR] Python environment missing."
    exit 1
}

& $python $runner @args
exit $LASTEXITCODE
