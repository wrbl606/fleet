# fleet — safe remote AI implementation

fleet lets a team hand real engineering tasks to an AI coding agent **without
trusting the agent**. A task is triggered from the tools the team already uses
(Jira, or a GitHub `/agent` PR comment; Linear stubbed), the agent works inside
a locked-down sandbox on your own hardware, and the change arrives as an
ordinary pull request for human review. The agent never holds a GitHub token,
never gets open network access, and cannot widen its own permissions.

The goal is not "fully autonomous coding" — it is **safe remote
implementation**: delegate the typing while routing, credentials, blast radius,
and merge authority stay under central, human-controlled policy.

## What it defends against

| Attack / risk | Mitigation |
|---|---|
| **Prompt injection** in an issue, PR comment, or repo file weaponizes the agent | The agent runs in a disposable sandbox with only the task repo mounted; the host and its tokens are out of reach, and every change is still a human-reviewed PR. |
| **Malicious repo** exfiltrates secrets or reaches the network | Egress is an allowlist and COI domains/caps come from the trusted registry — not the repo. Untrusted repos get a hardened profile. |
| **Repo widens its own sandbox** | A repo manifest may *request* policy but can never exceed the central `coi` caps or the domain allowlist; the gate fails closed. |
| **Compromised agent** tries to push anywhere it likes | The agent gets **no** GitHub token. A separate trusted publisher stage uses a scoped token to commit/push only to the task branch. |
| **Bare-metal escape** on macOS/Windows (no containers) | Native runs are fail-closed: OS sandbox (Seatbelt/PF, Windows wrapper) plus an explicit repo **and** node allowlist, or they do not run. |
| **Forged or replayed webhooks** start unintended work | Webhooks are token-authenticated; PR-comment triggers are restricted by author association/allowlist and only update an existing PR branch. |
| **Runaway or silent activity** | A bounded setup→agent→verify loop with timeouts and registry caps, every run recorded in the admin panel ledger/ingest log, and delivery only ever via PR. |

## Built on established tooling

fleet is deliberately **glue, not a new platform** — it composes tools you
already run and can inspect:

- **Jenkins** as the trusted control plane: webhook ingress (Generic Webhook
  Trigger), node routing, and per-run credential binding.
- **Incus** with **COI** (containers-on-incus) on Linux, and the native
  **Seatbelt/PF** and **Windows** sandboxes for allowlisted bare-metal nodes.
- **Git** and the **GitHub CLI (`gh`)** for checkout, scoped pushes and PRs.
- **Existing headless CLI agents** (`claude`, `codex`, `opencode`, …), each
  given only the LLM key it needs.
- **Python** (stdlib-first) for the `fleetctl` core and **Phoenix LiveView** for
  the admin panel.

There is no bespoke container runtime, secret store, or agent protocol: routing
is a versioned YAML registry, per-repo behavior is a declarative `.fleet/`
contract, and the same `fleetctl` commands run on a laptop and in CI.

Full design: [`fleet-agent-runner-plan.md`](./fleet-agent-runner-plan.md).
Implements phases **P0–P6**.

```
Jira webhook ─▶ Jenkins (GWT) ─▶ normalize ▶ resolve ▶ clone ▶ plan
                                          │
                                          ▼  node(registry jenkins_label)
                    setup ─▶ agent ─▶ verify ──(fail)──▶ retry (bounded)
                                          │ (pass)
                                          ▼
                       trusted push + `gh pr create` + notify
```

## Concepts

| Concept | What it is |
|---|---|
| `registry.yaml` | Trusted routing (source → repo), native allowlist, COI/native policy and resource caps. Generic examples only — it ships reusable. |
| `.fleet/` | Per-repo contract: `fleet.toml`, prompt template, `setup.sh`, `verify.sh`, PR template |
| `registry.local.yaml` | Optional, **git-ignored** overlay for deployment-specific repos/projects; merged over `registry.yaml` by fleetctl |
| `fleetctl` | Dispatcher core: normalize, resolve, plan, run the bounded loop, publish, notify |
| Runner backends | `coi` (Linux sandbox) and `native` (macOS Seatbelt / Windows wrapper), fail-closed |
| PR-comment trigger | A GitHub `/agent` comment updates the PR's branch and/or replies; policy in `registry.yaml` |
| Admin panel | Phoenix LiveView run ledger, **ingest log**, ingest API, `/api/trigger`, GitOps config PRs (`admin/`) |

> **Why a Python core?** The plan describes a Groovy shared library. Here the
> pure logic lives in the dependency-light `fleetctl` CLI so it is unit-testable
> and runnable outside Jenkins; `vars/fleetDispatcher.groovy` is a thin wrapper
> for trigger plumbing, node routing and credential binding. Only that one
> Groovy file talks to Jenkins.

## Layout

| Path | Purpose |
|---|---|
| `fleetctl/` | Dispatcher core (Python) |
| `registry.yaml`, `schemas/` | Central config + JSON Schemas |
| `Jenkinsfile`, `vars/` | Jenkins trigger + orchestration |
| `examples/sample-repo/.fleet/` | Reference `.fleet/` contract |
| `tests/` | Unit tests + stub-agent fixture |
| `resources/` | Trusted Seatbelt/PF configs, Windows wrapper, SIEM + JCasC |
| `scripts/` | CI, P0 smoke test, audit shipping, host hardening |
| `scripts/jenkins/` | Local Jenkins install/start (JDK + WAR + plugins + JCasC) |
| `admin/` | Phoenix admin panel (P6) |
| `docs/` | Contract, runners, security, runbooks |

## Setup

### Prerequisites

- **Python 3.11+** with `pip install -r requirements.txt` (PyYAML, jsonschema)
- **git** and **[`gh`](https://cli.github.com/)** on the runner host
- **Linux runners (COI):** Incus + `coi`, user in `incus-admin` — see
  [`docs/p0-runbook.md`](./docs/p0-runbook.md)
- **Admin panel:** Elixir/Erlang via [`mise`](https://mise.jdx.dev/) (pinned in
  `mise.toml`)
- **Jenkins controller + build nodes:** exact tool and credential list in
  [`docs/jenkins-node.md`](./docs/jenkins-node.md)

### Configure the registry

Keep the tracked `registry.yaml` generic; write deployment-specific routing,
allowlists and GitHub comment policy to the git-ignored `registry.local.yaml`
overlay with the helper:

```bash
scripts/configure-registry.sh jira --project ENG --repo acme/engine --labels agent
scripts/configure-registry.sh jira --project PLAT --repo acme/platform \
    --component web=acme/web --platform linux
scripts/configure-registry.sh trusted acme/engine
scripts/configure-registry.sh github --comment-prefix /agent \
    --author-associations OWNER,MEMBER,COLLABORATOR --allow-users ada
scripts/configure-registry.sh show --effective     # merged view
```

It edits `registry.local.yaml` by default; pass `--file registry.yaml` to change
the tracked file instead and `--dry-run` to preview. The same file path can be
explicitly selected at run time with `FLEET_REGISTRY_LOCAL`.

### Run the dispatcher locally

```bash
python3 -m pip install -r requirements.txt

python3 -m fleetctl normalize --source jira \
    --payload-file tests/fixtures/issue-created.json

python3 -m fleetctl plan --registry registry.yaml --repo-dir examples/sample-repo \
    --source jira --payload-file tests/fixtures/issue-created.json --out /tmp/plan.json

python3 -m fleetctl validate --registry registry.yaml \
    --repo-dir examples/sample-repo --coi
```

### Smoke test (no LLM key required)

Runs `setup → agent → verify` **inside a real COI container** with a stub agent:

```bash
bash scripts/p0-smoke.sh     # expected: [p0] PASS
```

### Admin panel

```bash
mise install
bash admin/start.sh                  # 0.0.0.0:4000 (use --host/--port to change)
```

`admin/start.sh --host 0.0.0.0 --port 4000` binds all interfaces and ensures the
DB is migrated. For the raw flow: `cd admin && mix setup && mix phx.server`.

Runtime env (see [`admin/README.md`](./admin/README.md)):
`FLEET_INGEST_TOKEN`, `GITHUB_TOKEN`, `FLEET_WEBHOOK_URL` / `FLEET_WEBHOOK_TOKEN`
(for the **Trigger** page), `FLEET_JENKINS_URL` (link to the Jenkins master),
optional `FLEET_ADMIN_USER` / `FLEET_ADMIN_PASSWORD`.

Pages: `/` run ledger, `/ingest` ingest log, `/trigger` manual trigger,
`/gitops` config PRs.

### Jenkins (installed separately)

> **Jenkins is not bundled with this project and is not installed by the
> standard setup.** The dispatcher core (`fleetctl`) and the admin panel run
> without it, but the webhook → pipeline → PR flow requires a Jenkins you
> install and operate yourself (or provision with the JCasC reference in
> `resources/jenkins/jcasc.yaml`).

**Option A — local Jenkins (WAR), included helper scripts.** Requires a JDK,
which the setup script installs via `mise`:

```bash
bash scripts/jenkins/setup.sh          # JDK + jenkins.war + plugins (local state dir)
bash scripts/jenkins/start.sh          # http://localhost:8080 (admin/admin)

# In another shell: create local git remotes and run the pipeline once.
bash scripts/jenkins/prepare-local.sh
# first build registers the Generic Webhook Trigger, then fire it:
curl -X POST 'http://localhost:8080/generic-webhook-trigger/invoke?token=local-webhook-token&source=jira' \
  -H 'Content-Type: application/json' --data @tests/fixtures/issue-created.json
```

The local JCasC (`scripts/jenkins/jcasc.local.yaml`) labels the controller
`fleet-agent`, loads this repo as the `fleet-config` shared library, and sets
two dev-only overrides:

- `FLEET_GIT_BASE_URL=file://…` — clone the local stub repo instead of GitHub.
- `FLEET_DRY_RUN=1` — run the full loop but skip the real push/PR.

State lives under `$HOME/.local/share/fleet/jenkins/` (override with
`FLEET_JENKINS_STATE_DIR`).

**Option B — your own Jenkins** (Docker, distro package, or `java -jar`).
Install the plugins in `scripts/jenkins/plugins.txt`, then:

1. Add this repo as a global shared library named `fleet-config`.
2. Provide nodes labeled `fleet-agent` (Linux/COI); `fleet-agent-macos` /
   `fleet-agent-windows` + capability labels for bare-metal.
3. Create credentials: `fleet-webhook-token`, `fleet-github-read`,
   `fleet-github-token` (scoped `contents:write`+`pull-requests:write`), and one
   per `[agent].llm_env` (e.g. `ANTHROPIC_API_KEY`).
4. Create a Pipeline-from-SCM job; point Jira at
   `.../generic-webhook-trigger/invoke?token=<fleet-webhook-token>&source=jira`.
5. Add `.fleet/` to each source repo (copy `examples/sample-repo/.fleet/`).

Point the admin panel's Trigger page at the same invoke URL via
`FLEET_WEBHOOK_URL` / `FLEET_WEBHOOK_TOKEN`.

### Webhooks

Everything enters through the Jenkins **Generic Webhook Trigger**, authenticated
by the `fleet-webhook-token` shared secret in the query string.

| Source | URL | Events |
|---|---|---|
| Jira | `POST {jenkins}/generic-webhook-trigger/invoke?token={fleet-webhook-token}&source=jira` | `jira:issue_created`, `jira:issue_updated` (a label change adding the trigger label) |
| GitHub | `POST {jenkins}/generic-webhook-trigger/invoke?token={fleet-webhook-token}&source=github` (content type `application/json`) | `issues`, `issue_comment`, `pull_request_review_comment` — the event name comes from the `X-GitHub-Event` header |
| Linear | `POST {jenkins}/generic-webhook-trigger/invoke?token={fleet-webhook-token}&source=linear` | `Issue` create/update |

The panel also exposes its own endpoints (bearer `FLEET_INGEST_TOKEN`):

- `POST /api/ingest` — run lifecycle + debug events: `run.started`,
  `run.finished`, `audit.event`, `webhook.received`, `normalize.result`,
  `resolve.result`.
- `POST /api/trigger` — trigger a run through the panel (same path as the
  Trigger page).

**Ingest log.** Open `/ingest` in the panel to see every incoming webhook, the
normalization outcome (`ok` / `filtered` / `error`), and the routing decision
(`project → repo`, or the reason it did not resolve). It is the fastest way to
debug why an event did not start a run. The dispatcher reports these events
when the pipeline runs `fleetctl normalize`/`resolve` with `--ingest`.

## Upgrading host machines

fleet is not installed as a package: a host runs from a **git checkout** plus a
**state dir** (`$FLEET_JENKINS_STATE_DIR`, default
`~/.local/share/fleet/jenkins/`) and external tools (Incus/`coi`, Jenkins,
`mise`). Upgrading is therefore: *pull → refresh derived state → migrate →
restart → re-register*. Run every step on each host that executes the
corresponding role.

**0. Preflight / backup** — record the current revision and back up local,
unversioned state before touching anything:

```bash
git -C /path/to/fleet rev-parse HEAD
cp -a "$HOME/.local/share/fleet/jenkins"  "$HOME/.local/share/fleet/jenkins.bak.$(date +%s)"
cp -a /path/to/fleet/registry.local.yaml  "$HOME/registry.local.yaml.bak"   # git-ignored
cp -a /path/to/fleet/admin/fleet_admin_dev.db "$HOME/fleet_admin_dev.db.bak" # if SQLite
```

**1. Dispatcher core (`fleetctl`)** — on every build node:

```bash
git -C /path/to/fleet fetch --tags
git -C /path/to/fleet checkout <tag-or-main>
python3 -m pip install -r /path/to/fleet/requirements.txt   # deps may change
python3 -m fleetctl env-check --platform linux
```

**2. Trusted config** — `git pull` updates `registry.yaml`/schemas; the
git-ignored `registry.local.yaml` overlay is untouched. Re-validate:

```bash
python3 -m fleetctl validate --registry registry.yaml --repo-dir <repo> --coi
```

**3. COI images (Linux/COI nodes)** — refresh the runtime and rebuild images so
toolchain changes land:

```bash
coi update && coi health
coi build                              # base image
coi build --profile fleet-flutter      # each custom profile in use
```

If an earlier version left `chattr +i` behind, clear it (fleet now sets
`host_immutable=false`): `sudo chattr -R -i ~/.coi` and any workspace `.git`
that is immutable.

**4. Jenkins**

*Local WAR install (Option A):*

```bash
bash scripts/jenkins/setup.sh          # refresh jenkins.war + plugins
bash scripts/jenkins/prepare-local.sh  # refresh the fleet-config-git snapshot
bash scripts/jenkins/start.sh --jenkins-url "$JENKINS_URL"   # same env/secrets as before
```

Restarting drops the Generic Webhook Trigger, so run the job once (**Build
now**) to re-register it, then resume the webhook.

*Your own Jenkins (Option B):* update the `fleet-config` shared-library SCM and
the plugins from `scripts/jenkins/plugins.txt`, then rebuild/re-run.

**5. Admin panel** — install the pinned toolchain, migrate **before**
restarting, then start:

```bash
mise install
cd admin && mix deps.get && mix ecto.migrate
bash admin/start.sh --host 0.0.0.0 --port 4000
```

Migrations are additive, so the running panel keeps serving during a pull.

**6. Verify after upgrade**

```bash
bash scripts/ci.sh          # fleetctl + schema validation
bash scripts/ci-admin.sh    # admin compile/format/tests
bash scripts/p0-smoke.sh    # sandbox smoke (no LLM key)
```

Then a real smoke through the flow: use the panel **Trigger** page (or
`POST /api/trigger`) and confirm a run appears in the ledger and a build in
Jenkins.

**7. Rollback** — `git checkout <previous-rev>`, re-run `prepare-local.sh`,
restart Jenkins/panel, and `mix ecto.rollback` the panel migration if needed;
restore the state-dir and DB backups from step 0.

> Secrets never live in git. Keep the host's `secrets.env` (chmod 600) across
> upgrades and rotate any token whose scope changed with the release.

## Contributing

### Ground rules

- Never commit secrets. LLM keys and GitHub tokens are injected by Jenkins; the
  agent must never receive a GitHub token.
- Trusted policy (routing, allowlists, sandbox profiles, caps) lives here, not
  in source repos.
- Keep `registry.yaml` / `.fleet/fleet.toml` and their JSON Schemas in sync, and
  add tests for behavior changes.

### Checks before opening a PR

```bash
bash scripts/ci.sh         # fleetctl unit tests + contract/schema validation
bash scripts/ci-admin.sh   # admin: compile --warnings-as-errors + format + tests
```

### Where to make changes

| Change | Touch |
|---|---|
| New PM source | `fleetctl/normalizers/<source>.py`, register in `normalizers/__init__.py`, add `sources:` mapping in `registry.yaml`, add a payload fixture + test |
| New agent tool | `TOOL_COMMANDS` in `fleetctl/agents.py` (or pin argv via `[agent].command`) |
| Contract field | `fleetctl/models.py` validation, `schemas/fleet.schema.json`, `docs/fleet-contract.md`, tests |
| Registry field | `fleetctl/registry.py`, `schemas/registry.schema.json`, `registry.yaml`, tests |
| Runner/sandbox | `fleetctl/runners.py`, `resources/native/`, `docs/runner-backends.md` + `docs/bare-metal-hardening.md` |
| Panel | `admin/` — run `mix precommit` |

### Style

- Python: stdlib-first, no new runtime deps without discussion, pure logic
  separated from subprocess execution (`fleetctl/exec_.py`).
- Elixir: follow [`admin/AGENTS.md`](./admin/AGENTS.md) (LiveView streams,
  `<.input>`/`to_form`, Req for HTTP).
- Docs live in `docs/`; keep examples runnable.

## Security

Webhooks are token-authenticated; native execution is fail-closed; untrusted
repos cannot widen network/resource policy. Full model:
[`docs/security.md`](./docs/security.md).

## Documentation

| Doc | Contents |
|---|---|
| [`docs/fleet-contract.md`](./docs/fleet-contract.md) | `.fleet/` contract + templating |
| [`docs/runner-backends.md`](./docs/runner-backends.md) | COI / native backends, routing, secret injection |
| [`docs/coi-images.md`](./docs/coi-images.md) | Custom COI images (e.g. the Flutter profile) |
| [`docs/security.md`](./docs/security.md) | Trust boundaries, credentials, hardening |
| [`docs/p0-runbook.md`](./docs/p0-runbook.md) | Install COI, run the P0 MVP |
| [`docs/jenkins-node.md`](./docs/jenkins-node.md) | Jenkins controller + build-node requirements |
| [`docs/jenkins-interaction.md`](./docs/jenkins-interaction.md) | How Jenkins and the fleet project interact |
| [`docs/plans/pr-comment-trigger.md`](./docs/plans/pr-comment-trigger.md) | GitHub `/agent` PR-comment trigger (plan + decisions) |
| [`docs/bare-metal-hardening.md`](./docs/bare-metal-hardening.md) | macOS/Windows host hardening |
| [`docs/scale-observability.md`](./docs/scale-observability.md) | Pools, autoscaling, audit shipping, metrics |
| [`admin/README.md`](./admin/README.md) | Admin panel setup, API, schema |
