#!/usr/bin/env bash
# Start the local Jenkins (WAR) configured by scripts/jenkins/jcasc.local.yaml.
#
#   bash scripts/jenkins/start.sh [--jenkins-url URL] [--port PORT]
#
# Prerequisites: bash scripts/jenkins/setup.sh
#
# --jenkins-url sets the Jenkins root URL (JCasC location.url) and therefore the
# BUILD_URL that runs report back to the admin panel. Defaults to this host's
# primary IP so links work when the panel is reached from other machines.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="${FLEET_JENKINS_STATE_DIR:-$HOME/.local/share/fleet/jenkins}"
JENKINS_HOME="$STATE_DIR/jenkins-home"
WAR="$STATE_DIR/jenkins.war"
PORT="${JENKINS_PORT:-8080}"

while [ $# -gt 0 ]; do
  case "$1" in
    --jenkins-url)  JENKINS_URL="${2:?--jenkins-url requires a value}"; shift 2 ;;
    --jenkins-url=*) JENKINS_URL="${1#*=}"; shift ;;
    --port)         PORT="${2:?--port requires a value}"; shift 2 ;;
    --port=*)       PORT="${1#*=}"; shift ;;
    -h|--help)
      echo "usage: bash scripts/jenkins/start.sh [--jenkins-url URL] [--port PORT]"
      exit 0
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

[ -f "$WAR" ] || { echo "run scripts/jenkins/setup.sh first" >&2; exit 1; }

# Root URL advertised to Jenkins (used for BUILD_URL and links).
if [ -z "${JENKINS_URL:-}" ]; then
  HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  JENKINS_URL="http://${HOST_IP:-localhost}:${PORT}/"
fi

export JENKINS_HOME
export CASC_JENKINS_CONFIG="$REPO_ROOT/scripts/jenkins/jcasc.local.yaml"

# Values substituted into jcasc.local.yaml.
export FLEET_CONFIG_GIT_REPO="$STATE_DIR/fleet-config-git"
export FLEET_LOCAL_REPOS="$STATE_DIR/fleet-local-repos"
export JENKINS_URL

# NOTE: these are local placeholder credentials, not secrets — change them if
# this Jenkins is reachable by anyone else. See docs/security.md.
echo "[jenkins] ${JENKINS_URL}  (admin/admin)"

if [ "${FLEET_DRY_RUN:-1}" = "0" ] && [ -n "${GH_PUBLISH_TOKEN:-}" ]; then
  echo "[jenkins] publish: real (FLEET_DRY_RUN=0, GH_PUBLISH_TOKEN set)"
elif [ "${FLEET_DRY_RUN:-1}" = "0" ]; then
  echo "[jenkins] WARNING: FLEET_DRY_RUN=0 but GH_PUBLISH_TOKEN is unset — publish will fail"
else
  echo "[jenkins] publish: dry-run (FLEET_DRY_RUN=${FLEET_DRY_RUN:-1}); set FLEET_DRY_RUN=0 to push/PR"
fi

exec mise exec -- java \
  -Djenkins.install.runSetupWizard=false \
  -Dhudson.plugins.git.GitSCM.ALLOW_LOCAL_CHECKOUT=true \
  -jar "$WAR" --httpPort="$PORT"
