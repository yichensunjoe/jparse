@echo off
rem ============================================================================
rem  JParse - Windows 打开投递箱 (inbox)
rem ============================================================================
cd /d "%~dp0"
if not exist "%~dp0inbox" mkdir "%~dp0inbox"
explorer.exe "%~dp0inbox"
