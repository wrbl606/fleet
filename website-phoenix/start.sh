#!/usr/bin/env bash
# Start the fleet landing page (Phoenix).
#
#   bash website/start.sh [--host HOST] [--port PORT] [--build] [--daemon]
#
# Defaults to --host 0.0.0.0 --port 4100 so the site is reachable from other
# machines/containers. Use --host 127.0.0.1 to restrict it to localhost, or set
# PHX_IP / PORT in the environment.
#
#   --build    force a refresh of dependencies and built assets before starting
#   --daemon   run in the background; state lives in website/tmp/
#              (website.pid + website.log). Stop it with website/stop.sh.
#
# Env overrides: PHX_IP, PORT, MIX_ENV (default dev).
set -euo pipefail

cd "$(dirname "$0")"

HOST="${PHX_IP:-0.0.0.0}"
PORT="${PORT:-4100}"
BUILD=0
DAEMON=0

usage() {
  cat <<'EOF'
Start the fleet landing page (Phoenix).

  bash website/start.sh [--host HOST] [--port PORT] [--build] [--daemon]

Defaults:
  --host   0.0.0.0   (all interfaces; use 127.0.0.1 for localhost only)
  --port   4100
  env      PHX_IP, PORT, MIX_ENV=dev
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --host)    HOST="${2:?--host requires a value}"; shift 2 ;;
    --host=*)  HOST="${1#*=}"; shift ;;
    --port)    PORT="${2:?--port requires a value}"; shift 2 ;;
    --port=*)  PORT="${1#*=}"; shift ;;
    --build)   BUILD=1; shift ;;
    --daemon)  DAEMON=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

export PHX_IP="$HOST"
export PORT="$PORT"
export MIX_ENV="${MIX_ENV:-dev}"

# Pick the address clients use to reach this host: the bind host when it is a
# concrete address, otherwise the first non-loopback IP (remote access).
link_host() {
  case "$HOST" in
    0.0.0.0 | ::) hostname -I 2>/dev/null | awk '{print $1}' ;;
    *) echo "$HOST" ;;
  esac
}

LINK_HOST="$(link_host)"
[ -n "$LINK_HOST" ] || LINK_HOST="localhost"

if [ "$BUILD" = 1 ] || [ ! -d deps/phoenix ]; then
  echo "[start] fetching dependencies"
  mise exec -- mix deps.get
fi

if [ "$BUILD" = 1 ] ||
  [ ! -f priv/static/assets/css/app.css ] ||
  [ ! -f priv/static/assets/js/app.js ]; then
  echo "[start] building assets"
  mise exec -- mix assets.build
fi

if [ "$HOST" = "0.0.0.0" ] || [ "$HOST" = "::" ]; then
  echo "[start] fleet landing page: http://${LINK_HOST}:${PORT} (all interfaces)"
else
  echo "[start] fleet landing page: http://${HOST}:${PORT}"
fi

if [ "$DAEMON" = 1 ]; then
  mkdir -p tmp
  PIDFILE="tmp/website.pid"
  LOGFILE="tmp/website.log"

  if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "[start] already running (pid $(cat "$PIDFILE")); use website/stop.sh" >&2
    exit 1
  fi

  # setsid puts the server in its own process group so stop.sh can kill the
  # whole tree (mise -> mix -> BEAM) in one shot.
  setsid mise exec -- mix phx.server >"$LOGFILE" 2>&1 &
  echo $! >"$PIDFILE"

  sleep 2
  if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "[start] running in background (pid $(cat "$PIDFILE")); logs: $LOGFILE"
  else
    echo "[start] failed to start; last log lines:" >&2
    tail -n 20 "$LOGFILE" >&2 || true
    rm -f "$PIDFILE"
    exit 1
  fi
else
  exec mise exec -- mix phx.server
fi
