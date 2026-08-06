$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$launcher = Join-Path $projectRoot "scripts\start_app.py"
$noPause = $false
$launcherArgs = @()

foreach ($argument in $args) {
    if ($argument -eq "--no-pause") {
        $noPause = $true
    }
    else {
        $launcherArgs += $argument
    }
}

function Complete-Launch {
    param([int]$ExitCode)

    if ($ExitCode -ne 0 -and -not $noPause) {
        Write-Host ""
        Write-Host (
            "[PAUSE] Startup failed. Review the numbered error above " +
            "or the logs folder, then press Enter to close this window."
        )
        try {
            [void](Read-Host)
        }
        catch {
            # Redirected or unavailable stdin must not hide the real error.
        }
    }
    exit $ExitCode
}

if (-not (Test-Path -LiteralPath $python)) {
    Write-Host "[ERROR] E1001 (Python runtime missing; run setup.cmd first)"
    Complete-Launch 1
}

try {
    & $python $launcher @launcherArgs
    $launcherExit = $LASTEXITCODE
    if ($launcherExit -ne 0) {
        Write-Host (
            "[ERROR] Startup did not complete. Detailed logs: " +
            (Join-Path $projectRoot "logs")
        )
    }
    Complete-Launch $launcherExit
}
catch {
    Write-Host "[ERROR] E1099 (launcher failure) $($_.Exception.Message)"
    Complete-Launch 1
}
