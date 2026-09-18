#!/usr/bin/env bash
# Prepare local git repositories for a Jenkins run of the dispatcher.
#
# Jenkins needs git remotes, so this snapshots this project into a local bare-
# usable repo (for the shared library + Jenkinsfile SCM) and creates a local
# target repo (acme/engine-api) from the deterministic stub fixture. Nothing
# is committed to the project's own working tree.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="${FLEET_JENKINS_STATE_DIR:-$HOME/.local/share/fleet/jenkins}"
CONFIG_GIT="$STATE_DIR/fleet-config-git"
LOCAL_REPOS="$STATE_DIR/fleet-local-repos"
GIT_ID=(-c user.email=fleet@local -c user.name=fleet)

# 1. Snapshot the dispatcher repo (excludes heavy/irrelevant dirs).
echo "[jenkins] snapshotting fleet-config -> $CONFIG_GIT"
rm -rf "$CONFIG_GIT"
mkdir -p "$CONFIG_GIT"
tar -C "$REPO_ROOT" \
  --exclude='./.git' \
  --exclude='./.local' \
  --exclude='./.jenkins' \
  --exclude='./admin/deps' \
  --exclude='./admin/_build' \
  --exclude='./admin/*.db' \
  --exclude='./admin/*.db-*' \
  --exclude='*/__pycache__' \
  -cf - . | tar -C "$CONFIG_GIT" -xf -
git -C "$CONFIG_GIT" init -q -b main
git -C "$CONFIG_GIT" "${GIT_ID[@]}" add -A
git -C "$CONFIG_GIT" "${GIT_ID[@]}" commit -q -m "fleet-config local snapshot"

# 2. Local target repo: bare clone of the stub fixture as acme/engine-api.git.
echo "[jenkins] building target repo acme/engine-api.git"
WORK="$STATE_DIR/target-work/engine-api"
rm -rf "$LOCAL_REPOS/acme" "$WORK"
mkdir -p "$LOCAL_REPOS/acme" "$(dirname "$WORK")"
cp -r "$REPO_ROOT/tests/fixtures/stub-repo" "$WORK"
git -C "$WORK" init -q -b main
git -C "$WORK" "${GIT_ID[@]}" add -A
git -C "$WORK" "${GIT_ID[@]}" commit -q -m "stub repo"
git clone -q --bare "$WORK" "$LOCAL_REPOS/acme/engine-api.git"

echo "[jenkins] ready:"
echo "  shared library + job SCM: $CONFIG_GIT"
echo "  target repos:             $LOCAL_REPOS"
