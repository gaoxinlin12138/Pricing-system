@echo off
chcp 65001 >nul
cd /d "%~dp0"
py "%~dp0启动.py"
if errorlevel 1 (
    echo.
    echo 启动失败，请查看上面的错误信息。
)
pause
