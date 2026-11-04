@echo off
rem ============================================================================
rem  JParse - Windows 交互式工作台启动器
rem ============================================================================
chcp 65001 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion

set "PY_BIN="
if exist "%~dp0venv\Scripts\python.exe" set "PY_BIN=%~dp0venv\Scripts\python.exe"
if not defined PY_BIN (
    for %%P in (python py python3) do (
        if not defined PY_BIN (
            %%P --version >nul 2>&1
            if !errorlevel! equ 0 set "PY_BIN=%%P"
        )
    )
)

if not defined PY_BIN (
    echo [错误] 未检测到 Python 环境！请先运行 "一键安装环境-Windows.bat"。
    pause
    exit /b 1
)

echo 正在启动 JParse 交互式工作台 (支持批量拖拽与实时进度)...
"%PY_BIN%" src/web_app.py %*
