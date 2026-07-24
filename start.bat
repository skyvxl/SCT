@echo off
setlocal
cd /d "%~dp0"
uv run sct
if errorlevel 1 pause
