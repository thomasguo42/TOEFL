#!/usr/bin/env bash

# TOEFL Vocabulary Studio - Flask Application Runner
# Ensures old processes are terminated before bringing the app back online.

set -euo pipefail

echo "[FLASK] Starting TOEFL Vocabulary Studio..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}"
APP_DIR="${APP_DIR:-${ROOT_DIR}/app/flask_app}"
VENV_DIR="${VENV_DIR:-/venv/main}"
PORT="${PORT:-1111}"
HOST="0.0.0.0"
PUBLIC_HOST="${PUBLIC_HOST:-}"
PUBLIC_PORT="${PUBLIC_PORT:-${PORT}}"

if [[ ! -d "${VENV_DIR}" ]]; then
    echo "[ERROR] Virtual environment not found at ${VENV_DIR}"
    exit 1
fi

terminate_patterns() {
    local pattern
    for pattern in "$@"; do
        [[ -z "${pattern}" ]] && continue
        local pids
        pids="$(pgrep -f "${pattern}" || true)"
        if [[ -n "${pids}" ]]; then
            echo "[FLASK] Terminating processes matching '${pattern}' (${pids// /, })..."
            echo "${pids}" | xargs -r kill 2>/dev/null || true
            sleep 1
            local remaining
            remaining="$(pgrep -f "${pattern}" || true)"
            if [[ -n "${remaining}" ]]; then
                echo "[FLASK] Forcing termination for '${pattern}' (${remaining// /, })..."
                echo "${remaining}" | xargs -r kill -9 2>/dev/null || true
            fi
        fi
    done
}

wait_for_port_release() {
    local port=$1
    local attempts=0
    while lsof -ti :"${port}" >/dev/null 2>&1; do
        attempts=$((attempts + 1))
        if (( attempts > 15 )); then
            echo "[ERROR] Port ${port} is still busy. Aborting restart."
            exit 1
        fi
        echo "[FLASK] Waiting for port ${port} to become free..."
        sleep 1
    done
}

terminate_port() {
    local port=$1
    local pids
    pids="$(lsof -ti :"${port}" || true)"
    if [[ -n "${pids}" ]]; then
        echo "[FLASK] Terminating processes on port ${port} (${pids// /, })..."
        echo "${pids}" | xargs -r kill 2>/dev/null || true
        sleep 1
        local remaining
        remaining="$(lsof -ti :"${port}" || true)"
        if [[ -n "${remaining}" ]]; then
            echo "[FLASK] Forcing termination on port ${port} (${remaining// /, })..."
            echo "${remaining}" | xargs -r kill -9 2>/dev/null || true
        fi
    fi
    wait_for_port_release "${port}"
}

cleanup() {
    if [[ -n "${FLASK_PID:-}" ]]; then
        echo "[FLASK] Shutting down Flask process..."
        kill "${FLASK_PID}" 2>/dev/null || true
        wait "${FLASK_PID}" 2>/dev/null || true
    fi
}

trap cleanup EXIT INT TERM

echo "[FLASK] Activating virtual environment at ${VENV_DIR}..."
source "${VENV_DIR}/bin/activate"

echo "[FLASK] Ensuring previous Flask processes are stopped..."
terminate_patterns "${APP_DIR}/app.py" "flask run.*${APP_DIR}" "gunicorn.*flask_app"
terminate_port "${PORT}"

echo "[FLASK] Installing dependencies..."
cd "${APP_DIR}"
pip install -q -r requirements.txt

export FLASK_APP=app.py
export FLASK_ENV="${FLASK_ENV:-development}"
export PORT="${PORT}"
export GEMINI_API_KEY="AIzaSyAJrbPs_fr5hUqt08qUAporCHztsoZgFzE"  # User's API key

echo "[FLASK] Initializing database..."
python -c "from app import init_database; init_database()"

echo "[FLASK] Application starting on http://${HOST}:${PORT}"
if [[ -n "${PUBLIC_HOST}" ]]; then
    echo "[FLASK] Public access: http://${PUBLIC_HOST}:${PUBLIC_PORT}"
else
    echo "[FLASK] Set PUBLIC_HOST to share access on your network."
fi

python app.py &
FLASK_PID=$!
wait "${FLASK_PID}"
