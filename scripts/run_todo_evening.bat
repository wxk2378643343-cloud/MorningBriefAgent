@echo off
chcp 65001 >nul
cd /d "%~dp0.."
if not exist logs mkdir logs
python main.py todo-evening >> logs\todo_evening.log 2>&1
