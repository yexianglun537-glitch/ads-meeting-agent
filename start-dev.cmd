@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ROOT=%CD%"
set "BACKEND=%ROOT%\backend"
set "PYTHON=%BACKEND%\.venv\Scripts\python.exe"
set "PY_LAUNCHER="
set "PY_VERSION="
set "ENV_FILE=%BACKEND%\.env"
set "FALLBACK_URL=https://github.com/yexianglun537-glitch/ads-meeting-agent/releases"

where py.exe >nul 2>&1
if not errorlevel 1 call :try_py 3.13
if not defined PY_LAUNCHER call :try_py 3.12
if not defined PY_LAUNCHER call :try_py 3.14
if not defined PY_LAUNCHER call :try_py 3.11

if not defined PY_LAUNCHER (
    where python.exe >nul 2>&1
    if not errorlevel 1 (
        python.exe -c "import struct,sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 14) and struct.calcsize('P') * 8 == 64 else 1)" >nul 2>&1
        if not errorlevel 1 set "PY_LAUNCHER=python.exe"
    )
)

if not defined PY_LAUNCHER (
    echo [ERROR] No supported 64-bit Python was found. Python 3.11-3.14 is required.
    goto :fallback
)

if exist "%BACKEND%\.venv" if not exist "%PYTHON%" rmdir /s /q "%BACKEND%\.venv"
if exist "%PYTHON%" (
    "%PYTHON%" -c "import struct,sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 14) and struct.calcsize('P') * 8 == 64 else 1)" >nul 2>&1
    if errorlevel 1 rmdir /s /q "%BACKEND%\.venv"
)

if not exist "%PYTHON%" (
    echo [1/3] Creating the Python environment...
    "%PY_LAUNCHER%" %PY_VERSION% -m venv "%BACKEND%\.venv"
    if errorlevel 1 goto :venv_failed
)

echo [2/3] Installing offline dependencies...
"%PYTHON%" -m pip install --disable-pip-version-check --no-index --find-links "%BACKEND%\wheelhouse" -r "%BACKEND%\requirements-core.txt"
if errorlevel 1 goto :offline_install_failed
"%PYTHON%" -m pip check
if errorlevel 1 goto :dependency_check_failed
if not exist "%ENV_FILE%" copy /y "%BACKEND%\.env.example" "%ENV_FILE%" >nul

echo [3/3] Starting ADS Meeting Agent...
"%PYTHON%" "%ROOT%\packaging\launcher.py" --lightweight --port 8000
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" echo Full Windows release: %FALLBACK_URL%
exit /b %EXIT_CODE%

:try_py
if defined PY_LAUNCHER exit /b 0
py.exe -%1 -c "import struct,sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] <= (3, 14) and struct.calcsize('P') * 8 == 64 else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "PY_LAUNCHER=py.exe"
set "PY_VERSION=-%1"
exit /b 0

:venv_failed
echo [ERROR] Failed to create the Python environment.
goto :fallback

:offline_install_failed
echo [ERROR] Offline dependency installation failed. Keep the backend\wheelhouse directory intact.
goto :fallback

:dependency_check_failed
echo [ERROR] Python dependency verification failed.
goto :fallback

:fallback
echo Full Windows release: %FALLBACK_URL%
exit /b 1
