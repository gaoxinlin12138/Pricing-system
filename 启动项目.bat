@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
if exist "%~dp0backend\.venv\Scripts\python.exe" set "PY=%~dp0backend\.venv\Scripts\python.exe"
if not defined PY (
    where py >nul 2>nul && set "PY=py"
)
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo 没有找到 Python，请先安装 Python 3.11 或更高版本。
    pause
    exit /b 1
)
"%PY%" "%~dp0启动.py"
if errorlevel 1 (
    echo.
    echo 启动失败，请查看上面的错误信息。
)
pause
