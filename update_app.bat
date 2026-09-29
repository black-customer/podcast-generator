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
rem Only kill processes that are really this app: some ancestor runs from inside this
rem project (venv python.exe launcher spawns base python as child) AND the listener's
rem own command line is our server. A foreign program on 8765 is never touched.
powershell -NoProfile -Command "$proj=(Get-Location).Path; $foreign=0; Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { $self=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $_); $mine=$false; $cur=$_; for($i=0; $i -lt 8 -and $cur; $i++){ $pp=Get-CimInstance Win32_Process -Filter ('ProcessId=' + $cur); if(-not $pp){ break }; if($pp.ExecutablePath -like ($proj + '*')){ $mine=$true; break }; $cur=$pp.ParentProcessId }; if($self -and $mine -and $self.CommandLine -match 'run\.py|-m uvicorn server\.main'){ taskkill /F /T /PID $_ 2>$null } else { $foreign=1; Write-Host ('[update] PID ' + $_ + ' is using port 8765 but is not IELTS Pod - not killing it.') } }; if($foreign){ exit 2 }"
if errorlevel 1 (
  echo Port 8765 is used by another program. Close it ^(or move IELTS Pod to another port^) and run update again.
  pause
  exit /b 1
)
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
