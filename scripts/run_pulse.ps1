<#
.SYNOPSIS
    One-click runner script for Groww Reviews Weekly Pulse Pipeline.

.DESCRIPTION
    Activates the local virtual environment and executes src/orchestrate.py with all forwarded CLI arguments.

.EXAMPLE
    .\scripts\run_pulse.ps1 --dry-run
    .\scripts\run_pulse.ps1 --date 2026-11-01
    .\scripts\run_pulse.ps1 --force
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Warning "Virtual environment python was not found at $VenvPython."
    Write-Host "Please create the virtual environment first:" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv" -ForegroundColor Cyan
    Write-Host "  .venv\Scripts\pip install -r requirements.txt" -ForegroundColor Cyan
    exit 1
}

Push-Location $ProjectRoot
try {
    if ($Arguments -contains "-Serve" -or $Arguments -contains "--serve") {
        Write-Host "Launching Groww Reviews Dashboard UI at http://localhost:8000..." -ForegroundColor Cyan
        & $VenvPython "src\serve.py"
        exit $LASTEXITCODE
    }

    Write-Host "Executing Groww Pulse Pipeline..." -ForegroundColor Cyan
    & $VenvPython "src\orchestrate.py" @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -eq 0) {
        Write-Host "Pipeline completed successfully (Exit Code: $exitCode)." -ForegroundColor Green
    } else {
        Write-Error "Pipeline failed with exit code $exitCode."
    }
}
finally {
    Pop-Location
}

