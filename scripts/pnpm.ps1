[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PnpmArgs
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$packageJson = Get-Content -Raw (Join-Path $projectRoot "package.json") |
    ConvertFrom-Json
$expectedVersion = $packageJson.packageManager -replace "^pnpm@", ""
$directPnpm = Get-Command pnpm -ErrorAction SilentlyContinue

if ($directPnpm) {
    $actualVersion = (& $directPnpm.Source --version 2>$null | Select-Object -First 1)
    if (
        $LASTEXITCODE -eq 0 -and
        $actualVersion -and
        $actualVersion.Trim() -eq $expectedVersion
    ) {
        & $directPnpm.Source @PnpmArgs
        exit $LASTEXITCODE
    }
}

$corepack = Get-Command corepack -ErrorAction SilentlyContinue
if ($corepack) {
    $env:COREPACK_HOME = Join-Path $projectRoot ".tools\corepack"
    New-Item -ItemType Directory -Force -Path $env:COREPACK_HOME | Out-Null
    & $corepack.Source pnpm @PnpmArgs
    exit $LASTEXITCODE
}

$npx = Get-Command npx -ErrorAction SilentlyContinue
if ($npx) {
    $env:npm_config_cache = Join-Path $projectRoot ".tools\npm-cache"
    & $npx.Source --yes "pnpm@$expectedVersion" @PnpmArgs
    exit $LASTEXITCODE
}

Write-Host "[ERROR] E1002（未找到 Node.js 包管理器）"
Write-Host "请先安装 Node.js 24 LTS，然后重新运行初始化脚本。"
exit 1
