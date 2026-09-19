@echo off
rem One-command update: pull latest code, sync deps, restart service, reopen browser.
rem Users just run this (or tell their AI agent to run it). Data in data\ is never touched.
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo No venv found. Run start.bat first to install.
  pause
  exit /b 1
)

echo [1/4] Pulling latest code...
git pull --ff-only
if errorlevel 1 (
  echo git pull failed - please resolve manually ^(local changes or network^).
  pause
  exit /b 1
)

echo [2/4] Syncing dependencies...
.venv\Scripts\python -m pip install -q -r requirements.txt

echo [3/4] Restarting service...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { taskkill /F /T /PID $_ 2>$null }"
timeout /t 2 /nobreak >nul
start "IELTS Pod Server" /min .venv\Scripts\python run.py --no-open

echo [4/4] Waiting for health check...
set /a tries=0
:wait
powershell -NoProfile -Command "try{$r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:8765/api/health';if($r.StatusCode -eq 200){exit 0}else{exit 1}}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 goto done
set /a tries+=1
if %tries% lss 15 (
  timeout /t 1 /nobreak >nul
  goto wait
)
echo Server did not come back. Run start.bat to see errors.
pause
exit /b 1

:done
set VER=
for /f "usebackq delims=" %%v in (`type VERSION`) do set VER=%%v
echo Update complete. Now running version %VER% at http://127.0.0.1:8765
start "" http://127.0.0.1:8765
exit /b 0
