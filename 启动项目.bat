@echo off
setlocal
cd /d "%~dp0"
call "%~dp0start-dev.cmd"
if errorlevel 1 (
    echo.
    echo Project startup failed.
    pause
    exit /b 1
)
