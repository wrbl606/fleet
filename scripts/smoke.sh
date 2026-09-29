#!/usr/bin/env bash
# Smoke test: prove the full dispatcher path against real COI with a
# deterministic stub agent (no LLM key needed).
#
#   plan -> trusted COI config -> coi run setup -> coi run agent -> coi run verify
#
# Exit 0 = the verify gate passed. Requires: coi, incus, python3, git.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[smoke] checking tooling"
python3 -m fleetctl env-check --platform linux >/tmp/fleet-env-check.json || {
  cat /tmp/fleet-env-check.json
  echo "[smoke] missing host tooling" >&2
  exit 1
}

WORK="$(mktemp -d /tmp/fleet-smoke-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

echo "[smoke] staging stub-repo at $WORK/workspace"
cp -r tests/fixtures/stub-repo "$WORK/workspace"

echo "[smoke] normalizing + planning"
python3 -m fleetctl normalize \
  --source jira \
  --payload-file tests/fixtures/issue-created.json \
  --out "$WORK/issue.json" >/dev/null

python3 -m fleetctl plan \
  --registry registry.yaml \
  --repo-dir "$WORK/workspace" \
  --issue-file "$WORK/issue.json" \
  --out "$WORK/plan.json" >/dev/null

echo "[smoke] running bounded loop inside COI"
python3 -m fleetctl run \
  --plan-file "$WORK/plan.json" \
  --workspace "$WORK/workspace" \
  --coi-config-dir "$WORK/coi" \
  --no-publish \
  --no-notify \
  --out "$WORK/result.json"

echo "[smoke] result:"
cat "$WORK/result.json"

python3 - "$WORK/result.json" <<'PY'
import json, sys
result = json.load(open(sys.argv[1]))
assert result["status"] == "succeeded", result
assert len(result["iterations"]) == 1, result
assert result["iterations"][0]["verify"]["exit_code"] == 0, result
print("[smoke] PASS: setup -> agent -> verify succeeded inside COI")
PY
