param(
    [switch]$IncludeLogs
)

$ErrorActionPreference = "Stop"

$projectRoot = [System.IO.Path]::GetFullPath(
    (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
).TrimEnd("\")

$targets = @(
    (Join-Path $projectRoot ".corepack"),
    (Join-Path $projectRoot ".corepack-cache"),
    (Join-Path $projectRoot ".pytest_cache"),
    (Join-Path $projectRoot "apps\web\.next-e2e"),
    (Join-Path $projectRoot "apps\web\.next-verify"),
    (Join-Path $projectRoot "apps\web\playwright-report"),
    (Join-Path $projectRoot "apps\web\test-results")
)

$targets += @(
    Get-ChildItem `
        -Path (Join-Path $projectRoot "apps"), `
              (Join-Path $projectRoot "tests"), `
              (Join-Path $projectRoot "scripts") `
        -Recurse `
        -Directory `
        -Filter "__pycache__" `
        -ErrorAction SilentlyContinue |
        ForEach-Object FullName
)

foreach ($target in $targets) {
    $resolved = [System.IO.Path]::GetFullPath($target)
    if (
        -not $resolved.StartsWith(
            $projectRoot + "\",
            [System.StringComparison]::OrdinalIgnoreCase
        )
    ) {
        throw "Unsafe cleanup target: $resolved"
    }
    if (Test-Path -LiteralPath $resolved) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
        Write-Host "[REMOVED] $resolved"
    }
}

$playwrightDatabase = Join-Path $projectRoot "data\playwright-models.db"
if (Test-Path -LiteralPath $playwrightDatabase) {
    Remove-Item -LiteralPath $playwrightDatabase -Force
    Write-Host "[REMOVED] $playwrightDatabase"
}

if ($IncludeLogs) {
    Get-ChildItem -LiteralPath (Join-Path $projectRoot "logs") -File |
        Remove-Item -Force
    Write-Host "[REMOVED] Runtime logs"
}

Write-Host "[PASS] Regenerable files cleaned"
