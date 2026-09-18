#!/usr/bin/env bash
# 质量门禁：绿 = 可提交。用法：bash scripts/check.sh [--with-e2e]
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/Scripts/python
if [ ! -f "$PY" ]; then PY=python; fi

echo "=== [1/4] ruff lint ==="
if "$PY" -m ruff --version > /dev/null 2>&1; then
  "$PY" -m ruff check server pipeline.py run.py tests
else
  echo "警告：ruff 未安装，lint 被跳过（pip install ruff）" >&2
fi

echo "=== [2/4] 单元与 API 测试 ==="
"$PY" -m pytest tests/ -q --ignore=tests/e2e

echo "=== [3/4] 导入冒烟 ==="
"$PY" -c "from server.main import app; print('app import OK, routes:', len(app.routes))"

echo "=== [4/4] 服务启动冒烟 ==="
PORT=8799
"$PY" -m uvicorn server.main:app --host 127.0.0.1 --port $PORT --log-level error &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT
sleep 3
if curl -sf "http://127.0.0.1:$PORT/api/health" > /dev/null; then
  echo "health OK"
else
  echo "服务启动冒烟失败" >&2
  exit 1
fi

if [ "${1:-}" = "--with-e2e" ]; then
  echo "=== [extra] Playwright e2e（自起 8765 服务）==="
  "$PY" run.py --no-open --port 8765 > /dev/null 2>&1 &
  E2E_PID=$!
  sleep 3
  "$PY" -m pytest tests/e2e -q
  kill $E2E_PID 2>/dev/null || true
fi

echo "=== CHECK GREEN ==="
