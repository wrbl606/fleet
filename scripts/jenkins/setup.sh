#!/usr/bin/env bash
# Install the local Jenkins (WAR + plugins) used to run the fLEET dispatcher.
#
# Jenkins is NOT bundled with this project. This script installs a JDK via mise
# and downloads jenkins.war + the plugin manager into a local state directory.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="${FLEET_JENKINS_STATE_DIR:-$HOME/.local/share/fleet/jenkins}"
JENKINS_HOME="$STATE_DIR/jenkins-home"
WAR="$STATE_DIR/jenkins.war"
PLUGIN_MANAGER="$STATE_DIR/jenkins-plugin-manager.jar"
PLUGIN_LIST="$REPO_ROOT/scripts/jenkins/plugins.txt"

mkdir -p "$STATE_DIR" "$JENKINS_HOME"

command -v mise >/dev/null || { echo "mise is required (https://mise.jdx.dev)" >&2; exit 1; }

if ! mise exec -- java -version >/dev/null 2>&1; then
  echo "[jenkins] installing JDK 21 via mise"
  (cd "$REPO_ROOT" && mise use java@21.0.2)
fi

if [ ! -f "$WAR" ]; then
  echo "[jenkins] downloading jenkins.war (latest LTS)"
  curl -fL --retry 3 -o "$WAR" https://get.jenkins.io/war-stable/latest/jenkins.war
fi

if [ ! -f "$PLUGIN_MANAGER" ]; then
  echo "[jenkins] downloading plugin installation manager"
  url="$(curl -fsSL https://api.github.com/repos/jenkinsci/plugin-installation-manager-tool/releases/latest \
    | jq -r '.assets[] | select(.name | endswith(".jar")) | .browser_download_url' | head -1)"
  [ -n "$url" ] || { echo "could not resolve plugin manager URL" >&2; exit 1; }
  curl -fL --retry 3 -o "$PLUGIN_MANAGER" "$url"
fi

echo "[jenkins] installing plugins"
mise exec -- java -jar "$PLUGIN_MANAGER" \
  --war "$WAR" \
  --plugin-file "$PLUGIN_LIST" \
  --plugin-download-directory "$JENKINS_HOME/plugins"

echo "[jenkins] ready"
echo "  JENKINS_HOME=$JENKINS_HOME"
echo "  start with: bash scripts/jenkins/start.sh"
