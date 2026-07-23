@echo off
setlocal
cd /d "%~dp0"
uv run scmm
if errorlevel 1 pause
