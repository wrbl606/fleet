#!/usr/bin/env bash
# Ship COI threat-audit JSONL (and optionally OS audit logs) to the admin
# panel ingest API as `audit.event` records (plan §10, P5).
#
# COI writes host-side audit logs to ~/.coi/audit/<container>.jsonl with the
# shape: {ts,sessionId,container,type,pid,comm,args,peer,path,msg,...}
#
# Usage:
#   FLEET_INGEST_URL=https://panel/api/ingest \
#   FLEET_INGEST_TOKEN=... \
#   FLEET_REPO=acme/engine FLEET_ISSUE_KEY=ENG-1 FLEET_BRANCH=fleet/ENG-1 \
#     scripts/ship-audit.sh --follow          # stream live
#
#   scripts/ship-audit.sh --file x.jsonl       # ship an existing file once
#
# For OS-level logs (auth.log, pf logs, Windows Event Log) ship with
# Filebeat/Fluent Bit instead: see resources/siem/.
set -euo pipefail

: "${FLEET_INGEST_URL:?set FLEET_INGEST_URL}"
: "${FLEET_INGEST_TOKEN:?set FLEET_INGEST_TOKEN}"

AUDIT_DIR="${COI_AUDIT_DIR:-$HOME/.coi/audit}"
MODE="follow"
FILE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --follow) MODE="follow" ;;
    --file)   MODE="file"; FILE="${2:?}"; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

now_iso() { date -u +%Y-%m-%dT%H:%M:%SZ; }

ship_line() {
  local line="$1"
  [ -n "$line" ] || return 0
  echo "$line" | jq -e . >/dev/null 2>&1 || return 0

  local payload
  payload="$(printf '%s' "$line" | jq -c \
    --arg repo "${FLEET_REPO:-}" \
    --arg key "${FLEET_ISSUE_KEY:-}" \
    --arg branch "${FLEET_BRANCH:-}" \
    --arg fallback_ts "$(now_iso)" '
    {
      event: "audit.event",
      ts: (.ts // .time // $fallback_ts),
      severity: (.severity // "info"),
      type: (.type // "coi"),
      action: (.action // null),
      msg: (.msg // .args // null),
      container: (.container // .sessionId // null),
      repo: (if $repo == "" then null else $repo end),
      issue_key: (if $key == "" then null else $key end),
      branch: (if $branch == "" then null else $branch end),
      external_id: (
        if $repo != "" and $key != "" and $branch != ""
        then "\($repo)#\($key)@\($branch)"
        else null end)
    }')" || return 0

  curl -fsS -X POST "$FLEET_INGEST_URL" \
    -H "Authorization: Bearer $FLEET_INGEST_TOKEN" \
    -H "Content-Type: application/json" \
    --data "$payload" >/dev/null ||
    echo "[ship-audit] POST failed, dropping one event" >&2
}

if [ "$MODE" = "file" ]; then
  while IFS= read -r line; do ship_line "$line"; done < "$FILE"
  exit 0
fi

echo "[ship-audit] following ${AUDIT_DIR}/*.jsonl -> ${FLEET_INGEST_URL}"
# tail -F tolerates files rotating in/out.
tail -F "${AUDIT_DIR}"/*.jsonl 2>/dev/null | while IFS= read -r line; do
  ship_line "$line"
done
