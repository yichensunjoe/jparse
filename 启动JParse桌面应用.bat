@echo off
rem ============================================================================
rem  JParse - Windows 桌面应用启动器
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
    echo [错误] 未检测到可用的 Python 环境！
    echo 请先双击运行 "一键安装环境-Windows.bat" 完成初始环境配置。
    echo.
    pause
    exit /b 1
)

echo 正在启动 JParse 桌面端 Studio...
"%PY_BIN%" src/desktop_app_windows.py %*
