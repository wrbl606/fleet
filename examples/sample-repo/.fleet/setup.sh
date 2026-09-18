#!/usr/bin/env bash
# Idempotent environment setup, run inside the sandbox before the agent.
set -euo pipefail

echo "[fleet] setting up sample-repo"
node --version
# No dependencies to install for the sample (node:test is built in).
echo "[fleet] setup complete"
