@echo off
rem ============================================================================
rem  JParse - Windows 一键环境配置与安装脚本
rem ============================================================================
chcp 65001 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ====================================================================
echo   🚀 JParse 文档智能重构与排版引擎 - Windows 一键安装向导
echo ====================================================================
echo.

rem 1. 查找 Python 解释器
set "PY_CMD="
for %%P in (python py python3) do (
    if not defined PY_CMD (
        %%P --version >nul 2>&1
        if !errorlevel! equ 0 (
            set "PY_CMD=%%P"
        )
    )
)

if not defined PY_CMD (
    echo [❌ 错误] 未找到 Python 环境！
    echo.
    echo 请先安装 Python 3.9 ~ 3.12：
    echo 推荐方式（在 PowerShell 中运行）：
    echo    winget install Python.Python.3.12
    echo 或从官方网站下载：https://www.python.org/downloads/
    echo ⚠️ 安装时请务必勾选 "Add python.exe to PATH"！
    echo.
    pause
    exit /b 1
)

echo [✓] 检测到 Python:
%PY_CMD% --version
echo.

rem 2. 创建或使用虚拟环境
set "VENV_DIR=%~dp0venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo [⏳] 正在创建 Python 虚拟环境 (venv)...
    %PY_CMD% -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo [⚠️ 警告] 虚拟环境创建遇到问题，将使用系统 Python 继续安装。
        set "VENV_PY=%PY_CMD%"
    ) else (
        echo [✓] 虚拟环境创建成功: %VENV_DIR%
    )
) else (
    echo [✓] 已存在虚拟环境: %VENV_DIR%
)
echo.

rem 3. 安装依赖包
echo [⏳] 正在安装与升级依赖库 (PyMuPDF, fonttools 等)...
"%VENV_PY%" -m pip install --upgrade pip
"%VENV_PY%" -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo [❌ 依赖安装失败] 请检查网络连接或尝试配置国内镜像源：
    echo "%VENV_PY%" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
    echo.
    pause
    exit /b 1
)
echo [✓] 核心依赖安装成功！
echo.

rem 4. 检查 Edge / Chrome 桌面窗口支持
set "BROWSER_FOUND=0"
if exist "%PROGRAMFILES(X86)%\Microsoft\Edge\Application\msedge.exe" set "BROWSER_FOUND=1"
if exist "%PROGRAMFILES%\Microsoft\Edge\Application\msedge.exe" set "BROWSER_FOUND=1"
if exist "%PROGRAMFILES%\Google\Chrome\Application\chrome.exe" set "BROWSER_FOUND=1"

if "%BROWSER_FOUND%"=="1" (
    echo [✓] 检测到 Chromium 浏览器 (Edge/Chrome)，支持原生独立桌面应用模式！
) else (
    echo [i] 未定位到 Edge/Chrome，将通过系统默认浏览器呈现交互工作台。
)

rem 5. 检查 Java 运行时 (OpenDataLoader 抽取可选)
where java >nul 2>&1
if !errorlevel! equ 0 (
    echo [✓] 检测到 Java 运行时 (支持 OpenDataLoader-PDF 拓扑抽取)
) else (
    echo [i] 未检测到 Java (可选。如需更强大的学术论文表格抽取，推荐安装 OpenJDK 17+)
)

echo.
echo ====================================================================
echo   🎉 JParse 环境配置完成！
echo ====================================================================
echo.
echo 您现在可以通过以下方式使用 JParse：
echo   1. 双击 "启动JParse桌面应用.bat" 启动独立桌面应用窗口
echo   2. 双击 "启动JParse桌面应用(无黑框).vbs" 纯净静默开启
echo   3. 双击 "打开交互应用.bat" 在默认浏览器打开交互工作台
echo   4. 把 PDF 放入 "inbox" 文件夹，双击 "启动自动识别.bat" 后台监听
echo.
pause
