@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" (
    echo 请先安装 Python，再根据 README.md 创建虚拟环境并安装依赖。
    pause
    exit /b 1
)
".venv\Scripts\python.exe" launch.py
if errorlevel 1 pause
