param(
    [switch]$E2E
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pnpm = Join-Path $projectRoot "scripts\pnpm.ps1"

Push-Location $projectRoot
try {
    Write-Host "[CHECK] Versions"
    & $python scripts/validate_versions.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] E1201（版本一致性检查失败）"
        exit $LASTEXITCODE
    }

    Write-Host "[CHECK] Backend and contracts"
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] E1202（后端测试失败）"
        exit $LASTEXITCODE
    }
    & $python scripts/validate_contracts.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] E1203（契约检查失败）"
        exit $LASTEXITCODE
    }

    Write-Host "[CHECK] Web tests, lint and production build"
    & $pnpm --dir apps/web test
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] E1204（前端测试失败）"
        exit $LASTEXITCODE
    }
    & $pnpm --dir apps/web lint
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] E1205（前端代码检查失败）"
        exit $LASTEXITCODE
    }
    $previousDistDirectory = $env:NEXT_DIST_DIR
    $env:NEXT_DIST_DIR = ".next-verify"
    try {
        & $pnpm --dir apps/web build
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] E1206（前端生产构建失败）"
            exit $LASTEXITCODE
        }
    }
    finally {
        $env:NEXT_DIST_DIR = $previousDistDirectory
    }

    if ($E2E) {
        Write-Host "[CHECK] Desktop end-to-end flow"
        & (Join-Path $projectRoot "scripts\run-e2e.ps1")
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[ERROR] E1207（桌面端到端测试失败）"
            exit $LASTEXITCODE
        }
    }
}
finally {
    Pop-Location
}

Write-Host "[PASS] Repository verification"
