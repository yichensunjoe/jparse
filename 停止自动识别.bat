@echo off
rem ============================================================================
rem  JParse - Windows 停止后台自动监控识别
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
    echo [错误] 未检测到 Python 环境！
    pause
    exit /b 1
)

"%PY_BIN%" src/manage.py stop
echo.
echo 按任意键关闭...
pause >nul
