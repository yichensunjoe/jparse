@echo off
rem ============================================================================
rem  JParse - Windows 打开成果目录 (outbox)
rem ============================================================================
cd /d "%~dp0"
if not exist "%~dp0outbox" mkdir "%~dp0outbox"
explorer.exe "%~dp0outbox"
