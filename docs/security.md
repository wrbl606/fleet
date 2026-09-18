# Security model

## Trust boundaries

| Zone | Contents | Trust |
|---|---|---|
| Jenkins controller | trigger, routing, credential binding | trusted |
| `fleet-config` registry + Jenkinsfile | routing, allowlist, caps | trusted |
| Source repo + `.fleet/` | prompt, scripts, agent command | **untrusted** |
| COI container (Linux) | agent execution | isolated |
| Bare-metal agent (macOS/Windows) | native execution | isolated only by OS controls |
| Trusted publisher | `git push` + `gh pr create` | trusted |

## Webhook authentication

- **Generic Webhook Trigger token**: the webhook URL includes a token backed by
  the Jenkins credential `fleet-webhook-token`; unauthenticated requests are
  rejected before the pipeline starts.
- **HMAC (optional)**: for sources that sign payloads (e.g. GitHub
  `X-Hub-Signature-256`), verify the signature over the raw body before
  normalizing. Jira Cloud webhooks do not sign by default, so the token is the
  primary control there. Use a per-source secret, rotate regularly, and keep
  the Jenkins job's trigger token separate from the LLM/GitHub credentials.

Unknown sources/events are rejected by the normalizer; every normalized event
must additionally resolve through `registry.yaml` or the run fails.

## Credentials

- **LLM keys**: only the env *name* is in the repo (`[agent].llm_env`). Jenkins
  binds the value per run; COI `forward_env` reads it from the host at session
  start. It never enters the repo, the generated COI config, or logs.
- **GitHub token**: the agent never sees it. `clone` uses a read-only token;
  `push`/`gh pr create` use a separate scoped token (`contents:write`,
  `pull-requests:write`), preferably a short-lived GitHub App installation
  token. COI keeps `.git/config`, hooks, `.husky`, `.vscode`, and
  `.claude/settings*.json` read-only, so the agent cannot alter git
  configuration or exfiltrate credentials through hooks.
- No SSH agent forwarding (`forward_agent = false`).

## Sandbox hardening (Linux / COI)

Generated trusted config (see [`fleetctl/coi_config.py`](../fleetctl/coi_config.py)):

- `network.mode = restricted` by default (internet egress, no LAN); `allowlist`
  for untrusted repos, where the host resolves each domain and blocks DNS.
- `limits.*` — per-container CPU/memory/disk caps and `runtime.max_duration`
  (repo-requested timeout clamped to `registry.coi.timeout_cap`).
- `monitoring` — `auto_pause_on_high` / `auto_kill_on_critical` enabled.
- `security.secret_paths` — masks `.env`, keys, credentials from the agent and
  from itself.
- `security.host_immutable` — immutable attribute on protected paths.
- `git.seed_host_identity = false` + explicit bot identity.
- `--profile hardened` for repos that are not trusted.

Audit: COI writes JSONL threat events (`coi audit`); ship to SIEM in P5.

## Bare-metal security (P4)

Long-lived macOS/Windows nodes are not disposable, so host hardening is
mandatory (plan §8):

1. Least-privilege per-agent service account; no interactive login, no stored
   keys/tokens.
2. No secrets at rest — injected per run via Jenkins binding.
3. Fail-closed allowlist (enforced today in `Registry.resolve`).
4. Optional OS sandbox (Seatbelt / Windows Sandbox) per untrusted repo.
5. Host egress firewall (macOS PF / Windows Defender Firewall) allowlisting LLM
   + package registries only.
6. OS-level resource/runtime kill policies (no COI limits here).
7. Full console capture + OS audit logs → SIEM; FIM on the agent image;
   scheduled rebuild/reimage.
8. Segregated VLAN, separate from the Linux/COI pool.

Implemented in P4: the trusted sandbox policy lives in `registry.yaml` under
`native:` and is applied by `NativeRunnerBackend` (`sandbox-exec` on macOS, the
PowerShell wrapper on Windows). Hardening scripts and the full runbook are in
[`docs/bare-metal-hardening.md`](./bare-metal-hardening.md) and
`scripts/hardening/`. A missing sandbox profile fails the run rather than
executing unisolated.

## Non-goals / guardrails

- No autonomous merge or close of PRs — a human reviews and merges.
- No silent degradation: a task needing an unavailable/unallowlisted platform
  fails rather than running unisolated.
- No credential material in repos, config files, or agent containers.
