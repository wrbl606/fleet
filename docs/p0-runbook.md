# P0 runbook — sandbox MVP

Goal: prove `coi run -- bash .fleet/setup.sh` → `coi run -- <agent>` →
`coi run -- bash .fleet/verify.sh` end-to-end with a hand-written `.fleet/`,
before any PM-tool wiring.

## 1. Install COI + Incus on one Linux agent

```bash
# Incus (Zabbly repo recommended; Ubuntu's 6.0.x lacks idmapping support)
#   https://github.com/zabbly/incus
sudo adduser "$USER" incus-admin
newgrp incus-admin

# code-on-incus
#   https://github.com/mensfeld/code-on-incus
coi health
coi build            # build the base image once
```

Verify the default profile is unprivileged (COI refuses otherwise):

```bash
incus profile show default | grep security.privileged   # must be absent/false
```

## 2. Validate the repo + tooling

```bash
python3 -m pip install -r requirements.txt
bash scripts/ci.sh                    # unit tests + contract validation
python3 -m fleetctl env-check --platform linux
```

## 3. Run the smoke test

```bash
bash scripts/p0-smoke.sh
```

What it does:

1. `fleetctl normalize` on `tests/fixtures/issue-created.json` (Jira `ENG-123`).
2. `fleetctl plan` resolves `ENG/backend → acme/engine-api`, loads
   `stub-repo/.fleet/fleet.toml`, renders the prompt, generates the trusted COI
   config and validates it with `coi validate profile`.
3. `fleetctl run` executes three `coi run` invocations (setup, stub agent,
   verify) inside ephemeral Incus containers.

Expected tail:

```
[p0] PASS: setup -> agent -> verify succeeded inside COI
```

## 4. Manual COI checks (optional)

```bash
# Confirm network isolation / limits are what the registry dictates
python3 -m fleetctl coi-config --registry registry.yaml \
  --repo-dir tests/fixtures/stub-repo --out /tmp/coi.toml --validate
cat /tmp/coi.toml

# Confirm the agent env never contains the GitHub token:
# GH_TOKEN is bound only around the trusted `fleetctl run` step, and COI
# forwards only `[agent].llm_env`.
```

## 5. Next (P1/P2)

- Add `fleet-config` as a Jenkins shared library and create the pipeline job
  from SCM.
- Create the webhook token credential and point Jira at the GWT invoke URL.
- Add `.fleet/` to a real repo (copy `examples/sample-repo/.fleet/`).
- Watch the first real PR (`fleet/<issue-key>`).

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `could not ensure bridge forwarding rules: sudo ... required` | Cosmetic in restricted mode; COI still applies isolation. For allowlist modes, grant passwordless sudo for nft/iptables or accept that restricted is the floor. |
| `User ... not in incus-admin group` | `sudo adduser $USER incus-admin` then re-login. |
| `secret_paths entry "secrets" is NOT masked` | The path doesn't exist in the repo; harmless. |
| `coi validate profile` fails | The registry/repo config widened an invalid field; the error path is reported by `fleetctl validate`. |
| Agent needs no LLM key (custom/stub) | Leave `llm_env` unset; `forward_env` is omitted. |
