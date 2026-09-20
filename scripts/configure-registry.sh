#!/usr/bin/env bash
# Configure the trusted fleet registry overlay (git-ignored by default).
#
#   scripts/configure-registry.sh jira --project ENG --repo acme/engine
#   scripts/configure-registry.sh jira --project PLAT --repo acme/platform \
#       --component web=acme/web --labels agent --platform linux
#   scripts/configure-registry.sh linear --team core --repo acme/core
#   scripts/configure-registry.sh github --comment-prefix /agent \
#       --author-associations OWNER,MEMBER,COLLABORATOR --allow-users ada
#   scripts/configure-registry.sh trusted acme/engine
#   scripts/configure-registry.sh native --repo acme/ios --label fleet-agent-macos
#   scripts/configure-registry.sh bot --name "fleet-agent[bot]" --email "fleet-agent@users.noreply.github.com"
#   scripts/configure-registry.sh show --effective
#
# By default this edits registry.local.yaml (merged over registry.yaml by
# fleetctl). Pass --file registry.yaml to edit the tracked config instead, and
# --dry-run to preview.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export FLEET_REGISTRY_LOCAL_DEFAULT="${FLEET_REGISTRY_LOCAL_DEFAULT:-$REPO_ROOT/registry.local.yaml}"
export PYTHONPATH="$REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

exec python3 -m fleetctl.registry_tool "$@"
