@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   Feishu Bot Background Service Launcher
echo ========================================================

echo [1/3] Checking and cleaning previous instances...
powershell -NoProfile -Command "$p = Get-CimInstance Win32_Process | Where-Object { ($_.Name -match 'python') -and ($_.CommandLine -like '*feishu_bot_server*') }; if ($p) { Write-Host 'Cleaning stale process...'; $p | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }"

echo [2/3] Launching Feishu Bot silently in Windows background...
powershell -NoProfile -Command "Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList 'wscript.exe \"%~dp0scripts\run_bot_silent.vbs\"' | Out-Null"

echo [3/3] Feishu Bot started successfully!
echo Status: Running as independent Windows background process
echo Output log: logs\feishu_bot.log
echo Window will close automatically in 2 seconds...
ping 127.0.0.1 -n 3 >nul
exit
