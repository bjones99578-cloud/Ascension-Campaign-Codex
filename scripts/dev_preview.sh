#!/usr/bin/env bash
# Local preview server for manual/Claude-driven testing -- always the same
# port, DB path, and PID file, so start/stop/reset are the exact same
# command every session instead of a fresh ad hoc PORT/DB_PATH each time.
# Never touches the real wiki.db (see DB_PATH below): safe to reset freely.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREVIEW_DIR="/tmp/ascension-codex-preview"
DB_PATH="$PREVIEW_DIR/wiki.db"
UPLOAD_DIR="$PREVIEW_DIR/uploads"
LOG_FILE="$PREVIEW_DIR/server.log"
PID_FILE="$PREVIEW_DIR/server.pid"
PORT=5055
URL="http://localhost:$PORT"
VENV="$ROOT/venv"

ensure_venv() {
  if [ ! -x "$VENV/bin/python3" ]; then
    echo "Creating venv..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q -r "$ROOT/requirements.txt"
  fi
}

is_running() {
  [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

cmd_start() {
  mkdir -p "$PREVIEW_DIR"
  if is_running; then
    echo "Already running (pid $(cat "$PID_FILE")) at $URL"
    return 0
  fi
  ensure_venv
  cd "$ROOT"
  PORT=$PORT DB_PATH="$DB_PATH" UPLOAD_DIR="$UPLOAD_DIR" SECRET_KEY=preview \
    "$VENV/bin/python3" app.py > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  for _ in $(seq 1 20); do
    if curl -s -o /dev/null "$URL/"; then
      echo "Started (pid $(cat "$PID_FILE")) at $URL"
      return 0
    fi
    sleep 0.3
  done
  echo "Server didn't come up in time -- check $LOG_FILE" >&2
  exit 1
}

cmd_stop() {
  if is_running; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    sleep 0.5
  fi
  rm -f "$PID_FILE"
  echo "Stopped."
}

cmd_reset() {
  cmd_stop
  rm -f "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm"
  rm -rf "$UPLOAD_DIR"
  rm -f "$LOG_FILE"
  echo "Wiped preview DB/uploads."
}

cmd_status() {
  if is_running; then
    echo "Running (pid $(cat "$PID_FILE")) at $URL"
  else
    echo "Not running."
  fi
}

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  reset) cmd_reset ;;
  status) cmd_status ;;
  *)
    echo "Usage: $0 {start|stop|restart|reset|status}" >&2
    exit 1
    ;;
esac
