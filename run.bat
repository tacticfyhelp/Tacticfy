@echo off
setlocal
title FM27 Scout and Tactical Synergy Optimizer
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python 3.11+ was not found in PATH. Please install Python 3.11+ and check "Add Python to PATH".
        pause
        exit /b 1
    )
    echo [SETUP] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        pause
        exit /b 1
    )
)

if not exist ".venv\.deps_installed" (
    echo [SETUP] Installing dependencies from requirements.txt...
    "%VENV_PY%" -m pip install --upgrade pip
    "%VENV_PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo installed> ".venv\.deps_installed"
)

echo [LAUNCH] Starting FM27 Scout ^& Tactical Synergy Optimizer...
"%VENV_PY%" main.py
set "APP_EXIT=%errorlevel%"
if not "%APP_EXIT%"=="0" (
    echo [ERROR] Application exited with error code %APP_EXIT%.
    pause
)
endlocal
