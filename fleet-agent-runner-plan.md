# `.fleet` Remote Agent Runner — Plan

A scalable system that turns PM-tool webhooks (Jira, Linear, GitHub Issues) into
autonomous coding-agent runs, isolated via **code-on-incus (COI)**, orchestrated by
**Jenkins**, and delivered as GitHub PRs. Repo-specific prompts, environment setup,
and code-quality gates live in each source repo under `.fleet/`. A Phoenix admin
panel configures the system (GitOps) and monitors every run.

---

## 1. Goals & scope

- Receive webhooks from Jira (and other PM tools) and turn each relevant event into a
  coding task.
- Run the task with a chosen CLI agent (`claude`, `codex`, `opencode`, …) in a safe,
  isolated environment.
- Open a GitHub PR with the result using the `gh` CLI.
- Scale horizontally via Jenkins; isolate agents via code-on-incus (Incus system
  containers) on Linux, and via native execution on long-lived bare-metal macOS/Windows
  agents for platform-specific toolchains.
- Keep per-repo behavior declarative in `.fleet/`; keep central routing/allowlist in a
  versioned registry.
- Provide an admin panel to configure the system and monitor runs.

## 2. Non-goals (explicit)

- No autonomous merge/close of PRs — a human reviews and merges.
- No credential material in repos, config files, or agent containers (keys are
  injected per-run from Jenkins).
- No silent degradation: if a task needs a bare-metal platform that is not
  allowlisted/available, the job fails rather than running unisolated.

---

## 3. Architecture

```
Jira / Linear / GitHub Issues ──webhook──▶ Jenkins (Generic Webhook Trigger)
                                              │
                              ┌───────────────▼────────────────┐
                              │  Dispatcher pipeline (from SCM) │
                              │  1. validate + normalize        │
                              │  2. resolve repo (registry)     │
                              │  3. clone + load .fleet         │
                              │  4. render prompt               │
                              │  5. route by platform/labels    │
                              └───────────────┬────────────────┘
                                              │
        ┌─────────────────────────────────────┼───────────────────────────┐
        │                                     │                           │
   Runner backends (per task)          Trusted host step           Notify / clean
   ┌────────────────────────────┐       git commit + push          PR link → issue
   │ linux: coi (Incus ctr)     │       gh pr create               coi clean
   │ macos: native + Seatbelt*  │       (scoped GitHub token)
   │ win:   native + WinSandbox*│
   └─────────────┬──────────────┘        ← bounded loop
                 │                       agent → verify → iterate
        setup.sh / agent CLI / verify.sh
```

### 3.1 Components

| Component | Responsibility | Location |
|---|---|---|
| **Webhook receiver** | Receive/validate PM webhooks (Generic Webhook Trigger plugin) | Jenkins controller |
| **Dispatcher pipeline** | Normalize event → resolve repo → run → verify → publish | `fleet-config` repo (SCM) |
| **Registry** | Map PM source → repo + default platform/labels/allowlist | `fleet-config/registry.yaml` |
| **`.fleet/`** | Per-repo manifest + prompt template + setup/verify scripts | each source repo |
| **Agent runner** | Execute agent CLI in an isolated environment | Jenkins agent nodes |
| **Trusted publisher** | `git push` + `gh pr create` with scoped token (outside sandbox) | Jenkins host step |
| **Admin panel** | Configure (GitOps) + monitor runs | Phoenix app (P6) |
| **Secrets** | LLM keys, GitHub token, webhook HMAC, Jira API token | Jenkins credentials store |

---

## 4. `.fleet/` contract (per source repo)

```
.fleet/
  fleet.toml          # manifest (declarative)
  prompts/task.md     # prompt template, {{var}}-rendered
  setup.sh            # env setup: install deps/toolchain (idempotent)
  verify.sh           # code-quality gate: lint + test (exit 0 = pass)
  pr-template.md      # optional PR body template
```

### 4.1 `fleet.toml`

```toml
version = 1

[agent]
tool         = "claude"           # claude | codex | opencode | pi | custom
prompt_file  = "prompts/task.md"  # or inline = "..."
max_iterations = 3                # bounded verify-fail loop
llm_env      = "ANTHROPIC_API_KEY" # NAME only — value lives in Jenkins

[setup]
script = "setup.sh"               # run before the agent, inside the sandbox

[verify]
script = "verify.sh"              # run after the agent, inside the sandbox

[pr]
branch_prefix = "fleet/"
base   = "main"
title  = "{{issue.key}}: {{issue.summary}}"
labels = ["agent"]
body_file = "pr-template.md"

[platform]                        # optional; default = linux
os       = "linux"                # linux | macos | windows
requires = []                     # capability labels, e.g. ["xcode-15", "msvc-2022"]
arch     = "amd64"

[coi]                             # Linux-only overrides
profile = ""                      # empty → use repo .coi/config.toml
network = "restricted"            # restricted | allowlist | open
timeout = "30m"
```

### 4.2 Prompt templating

Templates use `{{...}}` substitution over a canonical context object:

```
{{issue.key}} {{issue.summary}} {{issue.description}} {{issue.type}}
{{issue.labels}} {{source}} {{pr.title}}
```

The repo declares only the LLM key **name** (`llm_env`); the value never enters the
repo or config — Jenkins injects it at runtime (see §6).

---

## 5. Central registry (`fleet-config/registry.yaml`)

```yaml
defaults:
  github_org: acme
  default_branch: main
  platform: linux
  labels: ["fleet-agent"]

allowlist:                       # fail-closed gate for native (bare-metal) execution
  native_repos: ["acme/ios-app", "acme/win-tool"]
  native_labels: ["fleet-agent-macos", "fleet-agent-windows"]

sources:
  jira:
    - project: "ENG"
      repo: "acme/engine"
      components: {backend: "acme/engine-api", web: "acme/engine-web"}
    - project: "PLAT"
      repo: "acme/platform"
  linear:
    - team: "core"
      repo: "acme/core"
  github:
    - fallback_repo_from_issue: true
```

The `fleet-config` repo also holds the `Jenkinsfile`, the shared library
(normalizers, renderer, publisher), and **trusted host-side `$COI_CONFIG` templates**
(never committed into untrusted repos).

---

## 6. COI (code-on-incus) integration — Linux

Installed on every Linux agent node: Incus + `coi`, agent user in `incus-admin`,
`coi build` once for the base image.

### 6.1 Agent invocation (headless, autonomous)

`coi run -- <cmd>` runs any command inside the isolated container and propagates the
exit code. (`coi run --prompt-file` is claude-only; `coi run -- <cmd>` covers all
tools uniformly, so we use it.)

| Tool | Invocation (inside `coi run --`) |
|---|---|
| claude | `claude -p "<prompt>" --dangerously-skip-permissions` |
| codex | `codex exec --full-auto "<prompt>"` |
| opencode | `opencode run "<prompt>"` |

> CLI flags drift by tool version — pin exact non-interactive flags during P3.

### 6.2 Secret injection (LLM key)

1. Jenkins resolves the key from its credentials store and exports it as a host env var
   on the agent node (`withEnv`).
2. A Jenkins-generated **host-side** `$COI_CONFIG` sets
   `[defaults] forward_env = ["<llm_env from fleet.toml>"]`.
3. COI reads the value from the host at session start — never stored in config or repo.

### 6.3 GitHub token

The agent never sees one. It only edits files (and may commit locally — COI protects
`.git/config`, `.husky`, etc. as read-only). Push + PR happen in the trusted step.

### 6.4 Sandbox hardening

- Network `restricted` by default; `allowlist` (LLM API + pypi/npm domains) for
  untrusted repos; `--profile hardened` when the repo is not trusted.
- `[limits.*]`: per-container CPU/memory/disk/runtime caps.
- `[monitoring]` with `auto_pause_on_high` / `auto_kill_on_critical`.
- No SSH-agent forwarding; `[git]` pins bot identity + strips AI attribution trailers.

---

## 7. Runner backends (per-platform)

| Host | Backend | Isolation | Invocation |
|---|---|---|---|
| Linux | `coi` | Incus system container + active defense | `coi run -- <cmd>` |
| macOS | `native` (+ optional Seatbelt) | none → OS sandbox opt-in | `<cmd>` |
| Windows | `native` (+ optional Windows Sandbox/AppContainer) | none → OS sandbox opt-in | `<cmd>` |

The pipeline drives a small `RunnerBackend` interface (`runSetup`, `runAgent`,
`runVerify`) so the execution line is the only platform-specific part. Routing uses
`[platform]` + registry defaults → Jenkins labels
(`fleet-agent`, `fleet-agent-macos`, `fleet-agent-windows`, capability labels).

Secret injection: Linux via COI `forward_env`; bare-metal via Jenkins credentials
binding + `withEnv` (per-run, never persisted).

---

## 8. Bare-metal security (long-lived dedicated macOS/Windows nodes)

Nodes are **not** disposable, so host hardening is mandatory:

1. Least-privilege service account per agent; no interactive login, no stored SSH
   keys/tokens.
2. No secrets at rest — everything injected per-run via Jenkins binding.
3. Fail-closed allowlist — `native` execution only for repos/agents in the registry
   allowlist; otherwise the job fails.
4. Optional OS sandbox (Seatbelt / Windows Sandbox) enabled per-repo for untrusted code.
5. Host egress control — macOS PF / Windows Defender Firewall allowlisting LLM API +
   package registries only.
6. Hard resource caps — runtime timeout + process/memory kill policies (no
   `coi [limits]`/`[monitoring]` here; enforce at OS level).
7. Audit & integrity — full console capture, OS audit logs → SIEM, FIM on agent image,
   scheduled rebuild/reimage.
8. Segregated network/VLAN for bare-metal fleet, separate from the Linux/COI pool.

---

## 9. Jenkins dispatcher pipeline

1. **Receive & validate** — Generic Webhook Trigger; verify HMAC/signature; reject
   unknown sources/events.
2. **Normalize** — adapter turns Jira/Linear/GitHub payload into a canonical
   `TaskRequest`; filter to relevant events (`jira:issue_created`, or update adding an
   `agent` label).
3. **Resolve repo** — registry lookup by project/component/team; else fail fast +
   comment on issue.
4. **Clone & load** — shallow clone; read `.fleet/fleet.toml`; validate; render prompt.
5. **Provision** — generate host-side `$COI_CONFIG`; run `coi run -- bash .fleet/setup.sh`
   (if present).
6. **Bounded loop** (`max_iterations`):
   - `coi run -- <cli> <prompt>` (prompt appends prior verify errors on retries)
   - `coi run -- bash .fleet/verify.sh` → capture stdout/stderr + exit code
   - pass → break; fail → loop; exhausted → job fails
7. **Publish (trusted, no sandbox)** — `git commit` (pinned bot identity) on
   `fleet/<issue-key>` branch → `git push` → `gh pr create` (scoped token:
   `contents:write` + `pull-requests:write`; prefer a short-lived GitHub App
   installation token).
8. **Notify & clean** — comment PR URL back on the issue; POST a run-finished event to
   the admin panel; `coi clean`.

---

## 10. Security model (summary)

- HMAC-validated webhooks; allowlisted sources, events, and repos.
- Least-privilege GitHub token (scoped, short-lived, App-based preferred).
- LLM keys: Jenkins → host env → COI `forward_env`; never in repo/config/logs.
- Agents run isolated in COI (Linux) with active threat defense; bare-metal hardened via
  §8.
- Trusted publisher step outside the sandbox for push/PR.
- Full audit via `coi audit` (JSONL) + OS logs → SIEM; per-run logs archived.

---

## 11. Admin panel (P6)

**Phoenix (Elixir) + LiveView + Ecto + SQLite (`ecto_sqlite3`) + Tailwind**,
GitOps-PR config writes, own run ledger with an ingest API.

| Layer | Pick |
|---|---|
| Framework | Phoenix + LiveView (live run status, per-iteration updates, log tailing via WebSockets, no client JS framework) |
| DB | SQLite via `ecto_sqlite3` (WAL); Litestream backup |
| Background | OTP supervision + GenServer poller for Jenkins/GitHub/`coi audit` |
| Config write-back | GitOps PR via `Tentacat`/`Req` → `fleet-config`/source repo |
| Auth | `phx.gen.auth` + Ueberauth GitHub OAuth |
| Integrations | `Req` HTTP client → Jenkins REST, GitHub, Incus/COI |

### 11.1 Data flow

```
Jenkins pipeline ──POST run-finished──▶ Phoenix /api/ingest ──▶ SQLite ledger
                                                       │
coi audit / Jenkins logs ──(GenServer poll)────────────┴─▶ LiveView broadcast ─▶ browser
```

### 11.2 Ledger schema (sketch)

`runs` (source, issue_key, repo, commit, pr_url, status, tool, cost, timestamps) →
`iterations` (run_id, n, prompt, verify_exit, log_ref) →
`audit_events` (run_id, ts, severity, action, detail) →
`prs` (run_id, url, state).

### 11.3 Fallback

**Next.js + SQLite (`better-sqlite3`/Drizzle) + shadcn/ui** — same GitOps-PR + ledger
design; LiveView → SSE, GenServer → route handler/queue. Use only if the team is
JS-only and won't maintain Elixir.

---

## 12. Scalability model

- **Linux pool** scales via COI: many Incus containers per node (lightweight,
  second-scale start), resource-capped per container.
- **macOS/Windows pools** bounded by machine count; route only platform-specific tasks
  there, keep the default Linux path for everything else.
- **Queueing** by Jenkins; optional Throttle Concurrent Builds or EC2/spot autoscaling
  for burst.
- **Isolation** = one Incus container per task (Linux) / one native job per agent
  (bare-metal), with per-run resource caps.

---

## 13. Implementation roadmap

| Phase | Deliverable |
|---|---|
| **P0 — Sandbox MVP** | Install Incus+coi on one agent; prove `coi run -- claude -p …` + `coi run -- bash verify.sh` end-to-end on a sample repo with a hand-written `.fleet`. |
| **P1 — Dispatcher** | `fleet-config` repo; `registry.yaml` + `Jenkinsfile` + shared lib; wire Generic Webhook Trigger to a test Jira webhook; resolver + renderer; freeze `fleet.toml`/`registry.yaml` schemas. |
| **P2 — Verify loop + publisher** | Bounded iterate-on-verify; trusted push/PR step; issue notify; emit run-finished events. |
| **P3 — Multi-tool & Linux hardening** | codex/opencode invocation map; `$COI_CONFIG` secret injection; `--profile hardened`; limits/monitoring; pin CLI flags. |
| **P4 — Bare-metal backends** | `native` backend; `[platform]` routing; macOS/Windows agents + labels; host-hardening runbook; Seatbelt/WinSandbox profiles. |
| **P5 — Scale & observability** | Multi-node agent pool; autoscaling; audit-log shipping (`coi audit` + OS logs) → SIEM; dashboards. |
| **P6 — Admin panel** | Phoenix app: run ledger + ingest API, live monitoring, GitOps config editing. |

### 13.1 Dependencies

- Panel monitoring can start after P1 (run-finished events); GitOps config editing after
  schemas are frozen (P1); live log/audit tailing after P4 (`coi audit` + hardening).

---

## 14. Open items / remaining decisions

- **GitHub auth**: PAT vs. GitHub App installation token (recommend App for
  scoped/short-lived).
- **Exact PM sources first**: Jira-only MVP vs. also Linear/GitHub Issues (affects P1
  adapter work).
- **`fleet.toml`/`registry.yaml` schema freeze**: confirm field names before scaffolding.
- **Standard Seatbelt/WinSandbox profiles** and the trigger policy for untrusted repos
  (P4).
- **Elixir team skills**: confirm Phoenix ownership, else fall back to Next.js (P6).
