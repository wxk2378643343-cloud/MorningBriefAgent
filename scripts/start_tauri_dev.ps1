$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Set-Location (Join-Path $projectRoot "desktop")
& npm run dev
