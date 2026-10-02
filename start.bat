@echo off
rem 一键启动播客生成器
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
  if errorlevel 1 (
    echo Python 3.11+ is required. Install it and enable Add Python to PATH, then retry.
    pause
    exit /b 1
  )
  echo [1/3] 首次运行，创建虚拟环境...
  python -m venv .venv || (echo 创建 venv 失败，请确认已安装 Python & pause & exit /b 1)
)

.venv\Scripts\python -c "import fastapi, uvicorn, httpx, pydantic" >nul 2>&1
if errorlevel 1 (
  echo [2/3] 安装依赖...
  .venv\Scripts\python -m pip install -q -r requirements.txt || (echo 依赖安装失败 & pause & exit /b 1)
)

echo [3/3] 启动服务: http://127.0.0.1:8765  (Ctrl+C 停止)
.venv\Scripts\python run.py
pause
