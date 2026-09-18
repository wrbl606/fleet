#!/usr/bin/env bash
# CI entrypoint: unit tests + contract/schema validation.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[ci] unit tests"
python3 -m unittest discover -s tests -q

echo "[ci] contract validation"
python3 -m fleetctl validate \
  --registry registry.yaml \
  --repo-dir examples/sample-repo \
  --repo-dir tests/fixtures/stub-repo \
  --coi

echo "[ci] OK"
