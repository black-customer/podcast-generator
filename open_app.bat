@echo off
rem Desktop entry: if service is up -> open browser; else start it minimized then open
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First run: initializing environment...
  call start.bat
  exit /b 0
)

powershell -NoProfile -Command "try{$r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:8765/api/health';if($r.StatusCode -ne 200){exit 1}}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 goto open

echo Starting server...
start "IELTS Pod Server" /min .venv\Scripts\python run.py --no-open

set /a tries=0
:wait
powershell -NoProfile -Command "try{$r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:8765/api/health';if($r.StatusCode -eq 200){exit 0}else{exit 1}}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 goto open
set /a tries+=1
if %tries% lss 15 (
  timeout /t 1 /nobreak >nul
  goto wait
)
echo Server failed to start. Run start.bat to see the error.
pause
exit /b 1

:open
start "" http://127.0.0.1:8765
exit /b 0
