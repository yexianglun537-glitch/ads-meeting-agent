@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%CD%"
set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"
set "PYTHON=%BACKEND%\.venv\Scripts\python.exe"
set "ENV_FILE=%BACKEND%\.env"
set "DEPS_MARKER=%BACKEND%\.venv\.deps-installed"

where python.exe >nul 2>&1 || (
    echo [ERROR] Python 3.11 or later was not found in PATH.
    exit /b 1
)
where npm.cmd >nul 2>&1 || (
    echo [ERROR] Node.js 20 or later was not found in PATH.
    exit /b 1
)

echo [1/3] Preparing backend...
if not exist "%PYTHON%" (
    python -m venv "%BACKEND%\.venv" || exit /b 1
)
if not exist "%ENV_FILE%" copy /y "%BACKEND%\.env.example" "%ENV_FILE%" >nul
if not exist "%DEPS_MARKER%" (
    "%PYTHON%" -m pip install -r "%BACKEND%\requirements.txt" || exit /b 1
    type nul > "%DEPS_MARKER%"
)

echo [2/3] Preparing frontend...
if not exist "%FRONTEND%\node_modules" (
    pushd "%FRONTEND%"
    call npm install
    if errorlevel 1 (
        popd
        exit /b 1
    )
    popd
)

echo [3/3] Starting services...
curl.exe -fsS "http://127.0.0.1:8000/api/health" >nul 2>&1
if errorlevel 1 start "ADS Backend" /D "%BACKEND%" "%PYTHON%" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

curl.exe -fsS "http://127.0.0.1:5173" >nul 2>&1
if errorlevel 1 start "ADS Frontend" /D "%FRONTEND%" cmd.exe /k "call npm.cmd run dev -- --host 127.0.0.1"

echo.
echo Backend: http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo Close the Backend and Frontend command windows to stop the project.
ping 127.0.0.1 -n 4 >nul
start "" "http://127.0.0.1:5173"
exit /b 0
