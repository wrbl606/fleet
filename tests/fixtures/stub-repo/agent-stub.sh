#!/usr/bin/env bash
# Deterministic stand-in for a real agent CLI (no LLM required).
set -euo pipefail
prompt="${1:-}"
echo "[stub-agent] received prompt:"
echo "$prompt"
echo ok > agent-output.txt
