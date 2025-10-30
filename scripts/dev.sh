#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BACKEND_DIR="${ROOT_DIR}/app/backend"
FRONTEND_DIR="${ROOT_DIR}/app/frontend"

if ! command -v poetry >/dev/null 2>&1; then
  echo "Poetry is required to run the backend. Install it from https://python-poetry.org/docs/#installation" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm is required to run the frontend. Install Node.js (>=18) to proceed." >&2
  exit 1
fi

wait_for_port_release() {
  local port=$1
  local attempts=0
  while lsof -t -i :"${port}" >/dev/null 2>&1; do
    attempts=$((attempts + 1))
    if (( attempts > 10 )); then
      echo "Port ${port} is still in use after waiting. Aborting." >&2
      exit 1
    fi
    echo "Waiting for port ${port} to become free..."
    sleep 1
  done
}

API_PORT="${API_PORT:-${NEXT_PUBLIC_API_PORT:-8000}}"
FRONTEND_PORT="${FRONTEND_PORT:-1111}"
API_ALLOWED_ORIGINS="${API_ALLOWED_ORIGINS:-*}"
PUBLIC_WEB_ORIGIN="${PUBLIC_WEB_ORIGIN:-}"
PUBLIC_HOST="${PUBLIC_HOST:-}"
PUBLIC_API_PORT="${PUBLIC_API_PORT:-${API_PORT}}"
PUBLIC_WEB_PORT="${PUBLIC_WEB_PORT:-${FRONTEND_PORT}}"

if [[ -z "${NEXT_PUBLIC_API_BASE_URL:-}" ]]; then
  if [[ -n "${PUBLIC_HOST}" ]]; then
    NEXT_PUBLIC_API_BASE_URL="http://${PUBLIC_HOST}:${PUBLIC_API_PORT}"
  else
    NEXT_PUBLIC_API_BASE_URL="http://localhost:${API_PORT}"
  fi
fi

if [[ -z "${PUBLIC_WEB_ORIGIN}" && -n "${PUBLIC_HOST}" ]]; then
  PUBLIC_WEB_ORIGIN="http://${PUBLIC_HOST}:${PUBLIC_WEB_PORT}"
fi

echo "==> Installing backend dependencies (Poetry)…"
cd "${BACKEND_DIR}"
poetry install --no-root

echo "==> Terminating existing backend processes on port ${API_PORT}…"
if lsof -t -i :"${API_PORT}" >/dev/null 2>&1; then
  lsof -t -i :"${API_PORT}" | xargs -r kill -9
fi
wait_for_port_release "${API_PORT}"

echo "==> Starting backend on 0.0.0.0:${API_PORT}…"
API_ALLOWED_ORIGINS="${API_ALLOWED_ORIGINS}" poetry run uvicorn app.main:app --host 0.0.0.0 --port "${API_PORT}" --reload &
BACKEND_PID=$!

cleanup() {
  echo "==> Shutting down services…"
  kill "${BACKEND_PID}" "${FRONTEND_PID:-}" 2>/dev/null || true
  wait "${BACKEND_PID}" "${FRONTEND_PID:-}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "==> Installing frontend dependencies (npm)…"
cd "${FRONTEND_DIR}"
npm install

export NEXT_PUBLIC_API_BASE_URL
export NEXT_PUBLIC_API_PORT="${API_PORT}"
if [[ -n "${PUBLIC_WEB_ORIGIN}" ]]; then
  export PUBLIC_WEB_ORIGIN
fi

echo "==> Terminating existing frontend processes on port ${FRONTEND_PORT}…"
if lsof -t -i :"${FRONTEND_PORT}" >/dev/null 2>&1; then
  lsof -t -i :"${FRONTEND_PORT}" | xargs -r kill -9
fi
wait_for_port_release "${FRONTEND_PORT}"

echo "==> Starting frontend on 0.0.0.0:${FRONTEND_PORT}…"
npm run dev -- --hostname 0.0.0.0 --port "${FRONTEND_PORT}" &
FRONTEND_PID=$!

wait "${BACKEND_PID}" "${FRONTEND_PID}"
