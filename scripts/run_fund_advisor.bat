@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if not exist logs mkdir logs
python main.py fund >> logs\fund_advisor.log 2>&1
