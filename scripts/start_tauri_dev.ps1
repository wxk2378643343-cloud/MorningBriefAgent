$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$health = $null
try {
    $health = Invoke-WebRequest -Uri "http://127.0.0.1:8765/api/v1/health" -UseBasicParsing -TimeoutSec 1
} catch {
    $health = $null
}

if (-not $health -or $health.StatusCode -ne 200) {
    $python = (Get-Command python -ErrorAction Stop).Source
    $env:PYTHONPATH = $projectRoot
    Start-Process -FilePath $python `
        -ArgumentList "scripts/run_local_api.py", "--port", "8765" `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden
}

Set-Location (Join-Path $projectRoot "desktop")
& npm run dev
