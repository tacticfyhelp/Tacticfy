@echo off
rem Compiles the Tailwind CSS for the web app (web\assets\app.css) and the website (docs\assets\site.css).
rem Requires Node.js 18+. Only needed after editing web\*.html, web\app.js, docs\index.html or styles\*.css;
rem the compiled CSS is committed, so running Tacticfy from source does not need Node.
setlocal
cd /d "%~dp0"
if not exist node_modules\@tailwindcss\cli (
    call npm ci --no-audit --no-fund || call npm install --no-audit --no-fund
    if errorlevel 1 goto :fail
)
call npm run build
if errorlevel 1 goto :fail
echo [DONE] web\assets\app.css and docs\assets\site.css
endlocal
exit /b 0

:fail
echo [ERROR] Tailwind build failed.
endlocal
exit /b 1
