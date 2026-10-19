$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$binaryDirectory = Join-Path $projectRoot "desktop\src-tauri\binaries"
$buildDirectory = Join-Path $projectRoot ".build\local-api-sidecar"
$schemaPath = Join-Path $projectRoot "storage\schema.sql"
$entryPoint = Join-Path $projectRoot "scripts\run_local_api.py"
$targetTriple = "x86_64-pc-windows-msvc"
$binaryName = "morningbrief-local-api-$targetTriple"
$binaryPath = Join-Path $binaryDirectory "$binaryName.exe"

New-Item -ItemType Directory -Force -Path $binaryDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $buildDirectory | Out-Null

python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is required to build the bundled local API. Install the desktop build requirements first."
}

python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --noconsole `
    --name $binaryName `
    --distpath $binaryDirectory `
    --workpath (Join-Path $buildDirectory "work") `
    --specpath $buildDirectory `
    --paths $projectRoot `
    --add-data "$schemaPath;storage" `
    $entryPoint

if (-not (Test-Path -LiteralPath $binaryPath -PathType Leaf)) {
    throw "Sidecar build did not produce $binaryPath"
}

Write-Host "Built desktop local API sidecar: $binaryPath"
