# fLEET admin panel (P6)

Phoenix 1.8 + LiveView + Ecto + SQLite (`ecto_sqlite3`) admin panel. It owns the
run ledger, the ingest API the Jenkins dispatcher and the audit shipper post
to, and GitOps-based config write-back.

> The plan's primary choice is Phoenix. It is implemented here with the
> toolchain pinned in the repo-root `mise.toml` (Erlang 28 / Elixir 1.20).

## Setup

```bash
# from the repo root: install Erlang/Elixir via mise
mise install

# Option A — start script (bind address/port configurable)
bash admin/start.sh                      # 0.0.0.0:4000 (all interfaces)
bash admin/start.sh --host 127.0.0.1     # localhost only
bash admin/start.sh --port 4100          # custom port

# Option B — mix directly
cd admin
mix setup          # deps.get + ecto.setup + assets
mix phx.server     # binds 127.0.0.1:4000 unless PHX_IP/PORT are set
```

`admin/start.sh` ensures the DB is migrated and defaults to `--host 0.0.0.0`
so the panel is reachable from other machines. It warns when it binds a
non-loopback address while no `FLEET_ADMIN_PASSWORD` is set. The bind address
and port come from `--host`/`--port` (or `PHX_IP`/`PORT`), read by
`config/dev.exs`.

`mix setup` creates the SQLite DB, runs migrations, and seeds sample runs.

## Configuration (runtime env)

| Env var | Purpose |
|---|---|
| `FLEET_INGEST_TOKEN` | Bearer token required by `POST /api/ingest` and `GET /api/metrics` |
| `FLEET_WEBHOOK_URL` | Endpoint the **Trigger** page posts webhook-like events to (e.g. the Jenkins Generic Webhook Trigger invoke URL) |
| `FLEET_WEBHOOK_TOKEN` | Token appended to the webhook URL and sent as a bearer header |
| `FLEET_JENKINS_URL` | Base URL of the Jenkins master web UI (e.g. `https://jenkins.example.com/`); shown as a nav link and on the Trigger page |
| `GITHUB_TOKEN` | GitOps PRs (`contents:write`, `pull-requests:write`) |
| `FLEET_ADMIN_USER` / `FLEET_ADMIN_PASSWORD` | Optional HTTP Basic auth for the UI |
| `GITHUB_API_BASE_URL` | Override GitHub API (default `https://api.github.com`) |
| `DATABASE_PATH` | SQLite file path (see `config/runtime.exs`) |
| `SECRET_KEY_BASE` | Phoenix secret (prod) |

Wrapped with Jenkins' `post_run_finished`:

```json
POST /api/ingest
Authorization: Bearer $FLEET_INGEST_TOKEN
{"event":"run.finished","issue":{"source":"jira","key":"ENG-1"},
 "repo":"acme/engine-api","branch":"fleet/ENG-1","status":"succeeded",
 "tool":"claude","pr_url":"https://github.com/acme/engine-api/pull/7",
 "build_url":"https://jenkins.example/job/fleet-dispatcher/42/","build_number":42,
 "iterations":[{"n":1,"agent":{"exit_code":0},"verify":{"exit_code":0}}]}
```

Other accepted events: `run.started`, `audit.event` (from
`scripts/ship-audit.sh`).

## Triggering a test run

The **Trigger** page (`/trigger`) lets an admin fire a webhook-like event at the
configured dispatcher endpoint to exercise the pipeline without a real PM tool:

1. Set `FLEET_WEBHOOK_URL` (the Jenkins GWT invoke URL, e.g.
   `https://jenkins/generic-webhook-trigger/invoke`) and `FLEET_WEBHOOK_TOKEN`.
2. Open `/trigger`, pick a source, edit the JSON payload (a Jira
   `issue_created` sample is pre-filled), and click **Trigger run**.
3. Use **Dry run** to preview the exact request (URL + body) without sending.

The request is `POST <url>?source=<source>&token=<token>` with the event name in
the `x-fleet-event` header and the payload as the JSON body, matching the
`Jenkinsfile` Generic Webhook Trigger wiring. The resulting run then appears on
the ledger as Jenkins posts `run.finished` back to `/api/ingest`.

### With the local Jenkins

`admin/start.sh` already points the Trigger page at the local Jenkins created by
`scripts/jenkins/`:

```bash
bash scripts/jenkins/prepare-local.sh   # local git remotes
bash scripts/jenkins/start.sh           # Jenkins on :8080
bash admin/start.sh                     # panel on :4000, Trigger page enabled
```

It defaults `FLEET_WEBHOOK_URL` to
`http://<this host>:8080/generic-webhook-trigger/invoke` and the token to
`local-webhook-token` (override with `--webhook-url` / `--jenkins-url` or the
env vars).

> **These local defaults (`local-webhook-token`, `local-dev-token`,
> `admin`/`admin`) are placeholders, not secrets.** Set `FLEET_WEBHOOK_TOKEN`,
> `FLEET_INGEST_TOKEN`, and `FLEET_ADMIN_PASSWORD` to real values before the
> panel or Jenkins is reachable by anyone else. See
> [`docs/security.md`](../docs/security.md#local-development-defaults--change-before-any-real-deployment).

`scripts/jenkins/start.sh` likewise defaults Jenkins' root URL to
this host's IP (`--jenkins-url` to change) — that value becomes the `BUILD_URL`
the panel links to, so set it to an address clients can reach when the panel is
accessed remotely. **The Generic Webhook Trigger is registered by the pipeline's
`properties(...)` call**, so run one build first; then the Trigger page can
start runs:

```bash
# register the trigger (first build fails with "no webhook payload" — expected)
curl -u admin:admin -X POST http://localhost:8080/job/fleet-dispatcher/build
```

After that, open `http://<panel>:4000/trigger`, pick `jira` /
`jira:issue_created`, and click **Trigger run**. The sample payload resolves to
`acme/engine-api`, which `prepare-local.sh` provides as a local stub repo, so the
run completes against the deterministic stub agent.

## Routes

| Route | Description |
|---|---|
| `GET /` | Live run ledger (filters by status, streams live updates) |
| `GET /runs/:id` | Run detail: iterations, PR, audit events |
| `GET /trigger` | Send a webhook-like event to the dispatcher to test the pipeline |
| `GET /gitops` | Commit a file change to a branch and open a PR |
| `POST /api/ingest` | Run/audit ingest (bearer) |
| `GET /api/metrics` | Prometheus metrics (bearer) |

## Ledger schema

`runs` (source, issue_key, repo, branch, commit, pr_url, status, tool,
platform, cost, build_url, build_number, timestamps) → `iterations` (run_id, n,
prompt, agent_exit, verify_exit, log_ref) → `audit_events` (run_id, ts,
severity, action, detail, container) → `prs` (run_id, url, number, state). See
`priv/repo/migrations/`.

`build_url` / `build_number` come from the Jenkins `BUILD_URL` /
`BUILD_NUMBER` environment variables (set by `fleetctl run` when it is executed
inside a Jenkins build) and are surfaced as a "Jenkins" link on the run list and
run detail pages.

## Tests

```bash
mix test        # ledger, ingest API, metrics, LiveViews, GitOps (Req.Test)
mix precommit   # compile --warnings-as-errors + format + test
```

LiveView tests subscribe to PubSub and assert live updates; GitOps tests stub
the GitHub REST API with `Req.Test`.

## Auth note

The baseline UI auth is optional HTTP Basic (`FLEET_ADMIN_*`). The plan (§11)
specifies `phx.gen.auth` + Ueberauth GitHub OAuth for per-user accounts; the
`AdminAuth` plug is the single integration point to replace when that is
required.

## Troubleshooting

- **`mise install` fails building Erlang** (`no acceptable C compiler`): the
  box lacks a C toolchain. Install `gcc`/`make`, or extract a precompiled OTP
  from <https://builds.hex.pm/builds/otp/> into
  `~/.local/share/mise/installs/erlang/<version>/` (run its `./Install`).
- **`mix compile` fails on `exqlite`**: `exqlite` ships precompiled NIFs via
  `cc_precompiler`; if your platform has none, install a C compiler +
  `make` (`mise use make`, `mise use zig`, then `CC="zig cc" mix deps.compile`).
- **LiveView tests: `Database busy`**: SQLite + sandbox is single-writer. Keep
  DB/LiveView tests `async: false` (the test config sets `busy_timeout` + WAL).

