#!/usr/bin/env bash
# Build script for the coi-fleet-flutter-3.24 image (runs during `coi build`).
#
# Pinned to the last Flutter line that still ships the synthetic
# `package:flutter_gen` l10n package, for repos that import it. Newer Flutter
# removed it, which turns every `flutter analyze` into hard `uri_does_not_exist`
# errors. Override with FLUTTER_VERSION if a repo needs another 3.x release.
set -euo pipefail

FLUTTER_VERSION="${FLUTTER_VERSION:-3.24.5}"
FLUTTER_HOME=/opt/flutter

export DEBIAN_FRONTEND=noninteractive

echo "[image] installing base packages"
apt-get update
apt-get install -y --no-install-recommends ca-certificates git curl xz-utils unzip
rm -rf /var/lib/apt/lists/*

echo "[image] downloading Flutter ${FLUTTER_VERSION}"
curl -fL --retry 3 -o /tmp/flutter.tar.xz \
  "https://storage.googleapis.com/flutter_infra_release/releases/stable/linux/flutter_linux_${FLUTTER_VERSION}-stable.tar.xz"
tar -xJf /tmp/flutter.tar.xz -C /opt
rm -f /tmp/flutter.tar.xz

# The runtime container runs as the unprivileged `code` user (uid 1000).
id code >/dev/null 2>&1 || useradd -m -u 1000 code
chown -R code:code "$FLUTTER_HOME"
git config --system --add safe.directory "$FLUTTER_HOME"

# Make flutter/dart available on PATH for all shells/users.
ln -sf "$FLUTTER_HOME/bin/flutter" /usr/local/bin/flutter
ln -sf "$FLUTTER_HOME/bin/dart" /usr/local/bin/dart

echo "[image] warming Flutter cache as code"
su -s /bin/bash code -c '
  set -euo pipefail
  export HOME=/home/code
  export PUB_CACHE="$HOME/.pub-cache"
  cd "$HOME"
  flutter config --no-analytics >/dev/null 2>&1 || true
  flutter precache --linux
'

echo "[image] installed:"
/opt/flutter/bin/flutter --version
