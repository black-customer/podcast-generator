#!/usr/bin/env bash
# 质量门禁：绿 = 可提交。用法：bash scripts/check.sh [--with-e2e|--release]
#   --with-e2e 附加 Playwright e2e；--release 发布门禁 = e2e + portable zip 打包审计
set -euo pipefail
cd "$(dirname "$0")/.."

PY=.venv/Scripts/python
if [ ! -f "$PY" ]; then PY=python; fi

echo "=== [1/4] ruff lint ==="
if ! "$PY" -m ruff --version > /dev/null 2>&1; then
  echo "错误：ruff 未安装——lint 是硬门禁，不允许跳过（pip install ruff）" >&2
  exit 1
fi
"$PY" -m ruff check server pipeline.py run.py tests

echo "=== [2/4] 单元与 API 测试 ==="
"$PY" -m pytest tests/ -q --ignore=tests/e2e

echo "=== [3/4] 导入冒烟 ==="
"$PY" -c "from server.main import app; print('app import OK, routes:', len(app.routes))"

echo "=== [4/4] 服务启动冒烟 ==="
PORT=8799
SERVER_PID=""
E2E_PID=""
cleanup() {
  if [ -n "$E2E_PID" ]; then kill "$E2E_PID" 2>/dev/null || true; fi
  if [ -n "$SERVER_PID" ]; then kill "$SERVER_PID" 2>/dev/null || true; fi
}
trap cleanup EXIT
# 冒烟端口被占时旧服务会替新代码"假绿"：预检端口，健康检查后还要确认是我们起的进程
if curl -sf "http://127.0.0.1:$PORT/api/health" > /dev/null 2>&1; then
  echo "冒烟端口 $PORT 已被占用（可能是旧服务在跑），拒绝假绿——请先停掉占用进程" >&2
  exit 1
fi
"$PY" -m uvicorn server.main:app --host 127.0.0.1 --port $PORT --log-level error &
SERVER_PID=$!
sleep 3
if ! kill -0 "$SERVER_PID" 2>/dev/null; then
  echo "服务启动冒烟失败（进程已退出）" >&2
  exit 1
fi
if curl -sf "http://127.0.0.1:$PORT/api/health" > /dev/null; then
  echo "health OK"
else
  echo "服务启动冒烟失败" >&2
  exit 1
fi

if [ "${1:-}" = "--with-e2e" ] || [ "${1:-}" = "--release" ]; then
  E2E_PORT="${E2E_PORT:-8877}"
  echo "=== [extra] Playwright e2e（独立端口 $E2E_PORT）==="
  if curl -sf "http://127.0.0.1:$E2E_PORT/api/health" > /dev/null 2>&1; then
    echo "E2E 端口 $E2E_PORT 已被占用，拒绝对旧服务运行测试" >&2
    exit 1
  fi
  "$PY" run.py --no-open --port "$E2E_PORT" > /dev/null 2>&1 &
  E2E_PID=$!
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if ! kill -0 "$E2E_PID" 2>/dev/null; then
      echo "E2E 服务启动失败" >&2
      exit 1
    fi
    if curl -sf "http://127.0.0.1:$E2E_PORT/api/health" > /dev/null; then break; fi
    sleep 1
  done
  if ! curl -sf "http://127.0.0.1:$E2E_PORT/api/health" > /dev/null; then
    echo "E2E 服务健康检查超时" >&2
    exit 1
  fi
  BASE_URL="http://127.0.0.1:$E2E_PORT" "$PY" -m pytest tests/e2e -q
  kill $E2E_PID 2>/dev/null || true
  E2E_PID=""
fi

if [ "${1:-}" = "--release" ]; then
  echo "=== [release] portable zip 打包与审计 ==="
  "$PY" scripts/package.py
fi

echo "=== CHECK GREEN ==="
