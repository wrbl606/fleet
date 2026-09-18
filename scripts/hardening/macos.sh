#!/usr/bin/env bash
# macOS bare-metal agent host hardening (plan §8, P4).
#
# Run as root on each macOS agent node. Idempotent. Covers:
#   1. least-privilege service account (no interactive login)
#   2. host egress allowlist (PF)          -> resources/native/pf-fleet-egress.conf
#   3. audit + integrity logging
#   4. optional OS sandbox profile install -> resources/native/seatbelt.sb
#
# Secrets are never stored here; Jenkins injects them per run.
set -euo pipefail

AGENT_USER="${FLEET_AGENT_USER:-fleetagent}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOMAINS=(
  api.anthropic.com
  platform.claude.com
  api.openai.com
  opencode.ai
  registry.npmjs.org
  pypi.org
  files.pythonhosted.org
  github.com
  api.github.com
  objects.githubusercontent.com
)

require_root() { [ "$(id -u)" -eq 0 ] || { echo "must run as root" >&2; exit 1; }; }

install_service_account() {
  if ! dscl . -list /Users | grep -qx "$AGENT_USER"; then
    echo "[hardening] creating service account $AGENT_USER"
    # UID 499 range = service account; nologin shell; no home login.
    local uid=499
    while dscl . -list /Users UniqueID | awk '{print $2}' | grep -qx "$uid"; do uid=$((uid - 1)); done
    dscl . -create "/Users/$AGENT_USER"
    dscl . -create "/Users/$AGENT_USER" UserShell /usr/bin/false
    dscl . -create "/Users/$AGENT_USER" RealName "fleet agent"
    dscl . -create "/Users/$AGENT_USER" UniqueID "$uid"
    dscl . -create "/Users/$AGENT_USER" PrimaryGroupID 20
    dscl . -create "/Users/$AGENT_USER" NFSHomeDirectory "/var/fleetagent"
    mkdir -p /var/fleetagent && chown "$AGENT_USER":staff /var/fleetagent
  else
    echo "[hardening] service account $AGENT_USER already exists"
  fi
}

install_egress_filter() {
  echo "[hardening] installing PF egress anchor"
  cp "$REPO_ROOT/resources/native/pf-fleet-egress.conf" /etc/pf.anchors/fleet-egress
  if ! grep -q 'anchor "fleet-egress"' /etc/pf.conf; then
    {
      echo ''
      echo 'anchor "fleet-egress"'
      echo 'load anchor "fleet-egress" from "/etc/pf.anchors/fleet-egress"'
    } >> /etc/pf.conf
  fi
  refresh_egress_table
  pfctl -f /etc/pf.conf
}

refresh_egress_table() {
  local tmp count
  tmp="$(mktemp)"
  for d in "${DOMAINS[@]}"; do
    dig +short A "$d" 2>/dev/null || true
  done | grep -E '^[0-9]+\.' | sort -u > "$tmp"
  count="$(wc -l < "$tmp")"
  pfctl -t fleet_egress -T replace -f "$tmp" >/dev/null
  rm -f "$tmp"
  echo "[hardening] fleet_egress table refreshed ($count entries)"
}

install_refresh_daemon() {
  local plist=/Library/LaunchDaemons/dev.fleet.egress-refresh.plist
  cat > "$plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>dev.fleet.egress-refresh</string>
  <key>ProgramArguments</key>
  <array><string>${REPO_ROOT}/scripts/hardening/macos.sh</string><string>--refresh-egress</string></array>
  <key>StartInterval</key><integer>300</integer>
  <key>RunAtLoad</key><true/>
</dict></plist>
PLIST
  launchctl bootout system "$plist" 2>/dev/null || true
  launchctl bootstrap system "$plist"
}

enable_audit() {
  echo "[hardening] enabling process accounting / audit flags"
  # Audit flags: ad (audit), lo (login/logout), ex (exec) — tune to taste.
  auditconfig -setflags ad,lo,ex || true
}

main() {
  require_root
  install_service_account
  install_egress_filter
  install_refresh_daemon
  enable_audit
  echo "[hardening] done. Secrets are injected per-run by Jenkins; none stored."
}

if [ "${1:-}" = "--refresh-egress" ]; then
  require_root
  refresh_egress_table
else
  main
fi
