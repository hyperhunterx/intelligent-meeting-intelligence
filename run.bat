@echo off
REM ============================================================
REM  IMIES launcher
REM  - kills any stale uvicorn servers left running from before
REM  - auto-picks the first free port in 8000-8010
REM  - opens the dashboard in your browser
REM  - starts ONE clean server (Ctrl+C to stop)
REM  Double-click this file, or run it from a terminal.
REM ============================================================
setlocal

REM Always run from this script's folder (the project root).
cd /d "%~dp0"

echo.
echo [1/3] Stopping any stale uvicorn servers...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*uvicorn*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

REM Give Windows a moment to release the TCP ports.
timeout /t 1 /nobreak >nul

REM Find the first free port in 8000-8010 (avoids a busy/zombie socket).
set PORT=
for /f "usebackq tokens=*" %%p in (`powershell -NoProfile -Command "8000..8010 | Where-Object { -not (Get-NetTCPConnection -LocalPort $_ -State Listen -ErrorAction SilentlyContinue) } | Select-Object -First 1"`) do set PORT=%%p
if "%PORT%"=="" set PORT=8000

echo [2/3] Opening http://127.0.0.1:%PORT% in your browser...
start "" "http://127.0.0.1:%PORT%/"

echo [3/3] Starting IMIES server on port %PORT%  (press Ctrl+C to stop)
echo.
python -m uvicorn app.main:app --port %PORT%

endlocal
