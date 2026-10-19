$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

& (Join-Path $PSScriptRoot "build_local_api_sidecar.ps1")
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Push-Location (Join-Path $projectRoot "desktop")
try {
    npm run build
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}
