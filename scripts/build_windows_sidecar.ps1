$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$outputDir = Join-Path $repoRoot "desktop\src-tauri\binaries"
$workDir = Join-Path $env:TEMP "morningbrief-pyinstaller"
$schemaPath = Join-Path $repoRoot "storage\schema.sql"

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
New-Item -ItemType Directory -Force -Path $workDir | Out-Null

python -m PyInstaller `
  --noconfirm `
  --clean `
  --onefile `
  --name morningbrief-local-api `
  --distpath $workDir `
  --workpath (Join-Path $workDir "build") `
  --specpath $workDir `
  --add-data "$schemaPath;storage" `
  (Join-Path $repoRoot "scripts\run_local_api.py")

$target = Join-Path $outputDir "morningbrief-local-api-x86_64-pc-windows-msvc.exe"
Copy-Item -LiteralPath (Join-Path $workDir "morningbrief-local-api.exe") -Destination $target -Force
Write-Output $target
