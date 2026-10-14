@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================================
echo   Stopping Feishu Bot Background Service...
echo ========================================================

powershell -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -match 'python') -and ($_.CommandLine -like '*feishu_bot_server*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }; Write-Host 'Feishu Bot service stopped.'"

echo Window will close automatically in 2 seconds...
ping 127.0.0.1 -n 3 >nul
exit
