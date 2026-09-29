#!/usr/bin/env bash
# Stop a background instance started with `website/start.sh --daemon`.
#
#   bash website/stop.sh [--port PORT]
#
# Falls back to killing whatever process is listening on PORT (default 4100)
# when no pidfile is present.
set -euo pipefail

cd "$(dirname "$0")"

PORT="${PORT:-4100}"

while [ $# -gt 0 ]; do
  case "$1" in
    --port)   PORT="${2:?--port requires a value}"; shift 2 ;;
    --port=*) PORT="${1#*=}"; shift ;;
    -h|--help)
      echo "usage: bash website/stop.sh [--port PORT]"
      exit 0
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

PIDFILE="tmp/website.pid"
stopped=0

if [ -f "$PIDFILE" ]; then
  pid="$(cat "$PIDFILE")"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    # Kill the whole process group created by start.sh --daemon (setsid).
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
    echo "[stop] stopped pid $pid"
    stopped=1
  fi
  rm -f "$PIDFILE"
fi

if [ "$stopped" = 0 ]; then
  # Fallback: find the listener on PORT via ss, then lsof.
  pid=""
  if command -v ss >/dev/null 2>&1; then
    pid="$(ss -ltnp 2>/dev/null | awk -v p=":$PORT" '$4 ~ p {print $0}' |
      grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2 || true)"
  fi
  if [ -z "$pid" ] && command -v lsof >/dev/null 2>&1; then
    pid="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
  fi

  if [ -n "$pid" ]; then
    kill -TERM "$pid" 2>/dev/null || true
    echo "[stop] stopped pid $pid (port $PORT)"
    stopped=1
  fi
fi

if [ "$stopped" = 0 ]; then
  echo "[stop] nothing running on port $PORT"
fi
