@echo off
setlocal
cd /d "%~dp0"
set "PWSH="
where pwsh.exe >nul 2>&1 && set "PWSH=pwsh.exe"
if not defined PWSH if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" set "PWSH=%ProgramFiles%\PowerShell\7\pwsh.exe"
if not defined PWSH if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe" set "PWSH=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe"

if not defined PWSH (
    echo PowerShell 7 was not found. Please install PowerShell 7 and try again.
    pause
    exit /b 1
)

"%PWSH%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-dev.ps1"
pause
