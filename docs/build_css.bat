@echo off
rem Compiles the Tailwind CSS for the Tacticfy website (docs/) into docs/assets/site.css.
rem Requires Node.js 18+. Run again after editing docs/index.html or docs/src/input.css.
setlocal
cd /d "%~dp0"
if not exist node_modules\@tailwindcss\cli (
    call npm ci --no-audit --no-fund || call npm install --no-audit --no-fund
    if errorlevel 1 goto :fail
)
call npm run build
if errorlevel 1 goto :fail
echo [DONE] docs\assets\site.css
endlocal
exit /b 0

:fail
echo [ERROR] Tailwind build failed.
endlocal
exit /b 1
