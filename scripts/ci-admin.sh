#!/usr/bin/env bash
# Admin panel CI: compile (warnings-as-errors) + format + tests.
# Requires the repo-root mise.toml toolchain (erlang/elixir).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/admin"

echo "[ci-admin] installing toolchain + deps"
mise install >/dev/null
mise exec -- mix deps.get >/dev/null

echo "[ci-admin] precommit"
mise exec -- mix precommit

echo "[ci-admin] OK"
