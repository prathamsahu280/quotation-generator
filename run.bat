@echo off
REM ============================================================================
REM  Quotation Generator (Supabase + Next.js) launcher
REM  Starts the Python doc-gen service and the Next.js web app in two windows,
REM  then opens the app in your browser.
REM ============================================================================
cd /d "%~dp0"

echo.
echo  Starting Quotation Generator...
echo    - doc-gen service  -^> http://127.0.0.1:8500
echo    - web app          -^> http://localhost:3000
echo.

REM --- 1) Python doc-gen service (renders DOCX/PDF, runs Gemini) ---------------
REM  Runs from the docgen\ folder because its modules import each other directly.
start "Quotation doc-gen (port 8500)" cmd /k "cd /d ""%~dp0docgen"" && python -m uvicorn main:app --port 8500"

REM --- 2) Next.js web app -----------------------------------------------------
REM  First run installs npm dependencies if they're missing.
start "Quotation web (port 3000)" cmd /k "cd /d ""%~dp0web"" && (if not exist node_modules (echo Installing web dependencies... && npm install)) && npm run dev"

REM --- 3) Open the browser once the web server has had time to start ----------
timeout /t 8 /nobreak >nul
start "" http://localhost:3000

echo.
echo  Two terminal windows opened (doc-gen + web). Close them to stop the app.
echo  Make sure docgen\.env and web\.env.local are filled in.
echo.
