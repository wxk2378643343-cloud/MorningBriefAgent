@echo off
chcp 65001 >nul
start "" wscript.exe "%~dp0run_bot_silent.vbs"
exit
