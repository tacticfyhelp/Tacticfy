@echo off
setlocal
title Tacticfy installer build
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    echo [ERROR] .venv not found. Run run.bat once first to create it.
    goto :fail
)

set "APP_VERSION="
"%VENV_PY%" -c "from src.app_paths import APP_VERSION; print(APP_VERSION)" > "%TEMP%\tacticfy_version.txt"
set /p APP_VERSION=<"%TEMP%\tacticfy_version.txt"
del "%TEMP%\tacticfy_version.txt" >nul 2>nul
if not defined APP_VERSION (
    echo [ERROR] Could not read APP_VERSION from src\app_paths.py.
    goto :fail
)
echo [INFO] Building Tacticfy %APP_VERSION%

echo [1/4] Ensuring PyInstaller is installed...
"%VENV_PY%" -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 goto :fail

echo [2/4] Running tests...
"%VENV_PY%" -m pytest -q
if errorlevel 1 (
    echo [ERROR] Tests failed - not building.
    goto :fail
)

echo [3/4] Building dist\Tacticfy\Tacticfy.exe with PyInstaller...
"%VENV_PY%" -m PyInstaller build\tacticfy.spec --noconfirm --clean --distpath dist --workpath build\pyinstaller-work
if errorlevel 1 goto :fail
if not exist "dist\Tacticfy\Tacticfy.exe" (
    echo [ERROR] PyInstaller did not produce dist\Tacticfy\Tacticfy.exe.
    goto :fail
)

echo [4/4] Building dist\TacticfySetup.exe with Inno Setup...
set "ISCC="
for /f "delims=" %%i in ('where iscc 2^>nul') do if not defined ISCC set "ISCC=%%i"
if not defined ISCC if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo [WARN] Inno Setup 6 ^(ISCC.exe^) was not found.
    echo        Install it from https://jrsoftware.org/isdl.php ^(or: winget install JRSoftware.InnoSetup^)
    echo        then run build_installer.bat again. The portable app is ready in dist\Tacticfy\.
    goto :fail
)
"%ISCC%" /Q /DAppVersion=%APP_VERSION% build\installer.iss
if errorlevel 1 goto :fail

echo.
echo [DONE] dist\TacticfySetup.exe - upload it to a GitHub Release (v%APP_VERSION%).
if not defined NO_PAUSE pause
endlocal
exit /b 0

:fail
echo [FAILED] Installer build did not complete.
if not defined NO_PAUSE pause
endlocal
exit /b 1
