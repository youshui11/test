@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1

title Test7 - Frontend and Backend

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Project Python environment not found.
    echo Please restore .venv in this project folder first.
    pause
    exit /b 1
)

echo Website: http://127.0.0.1:7777/
echo API docs: http://127.0.0.1:7777/docs
echo.

".venv\Scripts\python.exe" -c "import json, urllib.request; data = json.load(urllib.request.urlopen('http://127.0.0.1:7777/api/health', timeout=2)); assert data.get('status') == 'ok' and data.get('database') == 'ok'" >nul 2>&1
if not errorlevel 1 (
    echo [OK] The project is already running. Open the website above.
    pause
    exit /b 0
)

echo Starting frontend and backend. PostgreSQL must be running.
echo Keep this window open. Press Ctrl+C to stop the service.
echo.
".venv\Scripts\python.exe" -m uvicorn backend.server:app --factory --host 127.0.0.1 --port 7777
set "APP_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%APP_EXIT_CODE%"=="0" echo [ERROR] Startup failed. Check the error above and whether port 7777 is occupied.
pause
endlocal & exit /b %APP_EXIT_CODE%
