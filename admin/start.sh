#!/usr/bin/env bash
# Start the fLEET admin panel (Phoenix).
#
#   bash admin/start.sh [--host HOST] [--port PORT]
#                       [--jenkins-url URL] [--webhook-url URL]
#
# Defaults to --host 0.0.0.0 --port 4000 so the panel is reachable from other
# machines/containers. Use --host 127.0.0.1 to restrict it to localhost, or set
# PHX_IP / PORT in the environment.
#
# The Jenkins and Trigger endpoints default to the local Jenkins created by
# scripts/jenkins/setup.sh (master http://<host>:8080, Generic Webhook Trigger
# token "local-webhook-token"). Override with the flags below or the matching
# env vars; set FLEET_JENKINS_URL / FLEET_WEBHOOK_URL empty to disable.
#
# Other overrides (export before running; empty value disables):
#   FLEET_INGEST_TOKEN, GITHUB_TOKEN, FLEET_ADMIN_USER, FLEET_ADMIN_PASSWORD
set -euo pipefail

cd "$(dirname "$0")"

HOST="${PHX_IP:-0.0.0.0}"
PORT="${PORT:-4000}"

usage() {
  cat <<'EOF'
Start the fLEET admin panel (Phoenix).

  bash admin/start.sh [--host HOST] [--port PORT]
                      [--jenkins-url URL] [--webhook-url URL]

Defaults:
  --host         0.0.0.0
  --port         4000
  --jenkins-url  http://<this host>:8080/
  --webhook-url  <jenkins-url>/generic-webhook-trigger/invoke
  webhook token  local-webhook-token
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --host)         HOST="${2:?--host requires a value}"; shift 2 ;;
    --host=*)       HOST="${1#*=}"; shift ;;
    --port)         PORT="${2:?--port requires a value}"; shift 2 ;;
    --port=*)       PORT="${1#*=}"; shift ;;
    --jenkins-url)  FLEET_JENKINS_URL="${2:?--jenkins-url requires a value}"; shift 2 ;;
    --jenkins-url=*) FLEET_JENKINS_URL="${1#*=}"; shift ;;
    --webhook-url)  FLEET_WEBHOOK_URL="${2:?--webhook-url requires a value}"; shift 2 ;;
    --webhook-url=*) FLEET_WEBHOOK_URL="${1#*=}"; shift ;;
    -h|--help)      usage; exit 0 ;;
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

# Local dev defaults. `-` (not `:-`) so an explicitly empty value disables it.
# These are placeholders, not secrets: set real values before exposing the panel.
# See docs/security.md#local-development-defaults--change-before-any-real-deployment
export FLEET_INGEST_TOKEN="${FLEET_INGEST_TOKEN-local-dev-token}"
export FLEET_JENKINS_URL="${FLEET_JENKINS_URL-http://${LINK_HOST}:8080/}"

# Default the Trigger page at the local Jenkins Generic Webhook Trigger.
if [ -z "${FLEET_WEBHOOK_URL+x}" ] && [ -n "${FLEET_JENKINS_URL:-}" ]; then
  export FLEET_WEBHOOK_URL="${FLEET_JENKINS_URL%/}/generic-webhook-trigger/invoke"
fi
if [ -z "${FLEET_WEBHOOK_TOKEN+x}" ] && [ -n "${FLEET_WEBHOOK_URL:-}" ]; then
  export FLEET_WEBHOOK_TOKEN="local-webhook-token"
fi

if [ ! -d deps/phoenix ]; then
  echo "[start] fetching dependencies"
  mise exec -- mix deps.get
fi

echo "[start] ensuring database is migrated"
mise exec -- mix ecto.create --quiet >/dev/null 2>&1 || true
mise exec -- mix ecto.migrate --quiet

case "$HOST" in
  127.0.0.1 | localhost | ::1) ;;
  *)
    if [ -z "${FLEET_ADMIN_PASSWORD:-}" ]; then
      echo "[start] WARNING: binding $HOST without FLEET_ADMIN_PASSWORD — the admin UI is unauthenticated"
    fi
    ;;
esac

if [ "$HOST" = "0.0.0.0" ] || [ "$HOST" = "::" ]; then
  echo "[start] fLEET admin panel: http://${LINK_HOST}:${PORT} (all interfaces)"
else
  echo "[start] fLEET admin panel: http://${HOST}:${PORT}"
fi

echo "[start] ingest token: ${FLEET_INGEST_TOKEN:-<open, no auth>}"
echo "[start] jenkins master: ${FLEET_JENKINS_URL:-<hidden>}"
echo "[start] trigger endpoint: ${FLEET_WEBHOOK_URL:-<disabled>}"

mise exec -- mix phx.server
