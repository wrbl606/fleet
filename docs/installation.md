# Installation

fleet is **glue, not a package**: a host runs from a git checkout plus a state
directory and the external tools it already uses. Install only the pieces you
need — the dispatcher core and the admin panel run without Jenkins.

The website mirrors this guide at `/docs/installation`.

## Prerequisites

- **Python 3.11+** and `pip` (PyYAML + jsonschema).
- **git** and the **GitHub CLI** (`gh`) on the runner host.
- **Linux runners (COI):** Incus and `coi`, with your user in `incus-admin`.
- **Admin panel:** Erlang/Elixir via [`mise`](https://mise.jdx.dev/) (pinned in
  the repo-root `mise.toml`).
- **Website (optional):** Node via `mise`.
- **Jenkins** controller + build nodes — installed separately.

## 1. Get the code

```bash
git clone https://github.com/wrbl606/fleet.git
cd fleet
```

## 2. Dispatcher core (`fleetctl`)

`fleetctl` owns normalize → resolve → plan → run → publish. It is stdlib-first
and runs identically on a laptop and in CI.

```bash
python3 -m pip install -r requirements.txt
python3 -m fleetctl env-check --platform linux
```

## 3. Trusted registry

Keep the tracked `registry.yaml` generic; write deployment-specific routing,
allowlists, and GitHub comment policy to the git-ignored
`registry.local.yaml` overlay.

```bash
scripts/configure-registry.sh jira --project ENG --repo acme/engine --labels agent
scripts/configure-registry.sh trusted acme/engine
scripts/configure-registry.sh show --effective   # merged view
```

## 4. Admin panel

The panel owns the run ledger and the webhook **ingest endpoint** (see
[`triggers.md`](./triggers.md)). It defaults to `0.0.0.0:4000` and migrates the
database on start.

```bash
mise install
bash admin/start.sh --host 0.0.0.0 --port 4000
```

Runtime env (full list in [`admin/README.md`](../admin/README.md)):

| Env var | Purpose |
|---|---|
| `FLEET_INGEST_TOKEN` | Bearer token for `POST /api/ingest`, `POST /api/trigger`, `GET /api/metrics` |
| `FLEET_WEBHOOK_URL` | Dispatcher endpoint inbound webhooks are forwarded to (Jenkins GWT invoke URL) |
| `FLEET_WEBHOOK_TOKEN` | Token appended to the forward URL and sent as a bearer header |
| `FLEET_INGEST_PUBLIC_URL` | Public URL of this panel's ingest endpoint (shown on the Trigger page) |
| `FLEET_GITHUB_WEBHOOK_SECRET` | GitHub webhook secret for `X-Hub-Signature-256` HMAC auth |
| `FLEET_JENKINS_URL` | Jenkins master web UI, linked from the nav and Trigger page |
| `GITHUB_TOKEN` | GitOps config PRs (`contents:write`, `pull-requests:write`) |
| `FLEET_ADMIN_USER` / `FLEET_ADMIN_PASSWORD` | Optional HTTP Basic auth for the UI |

Pages: `/` run ledger, `/ingest` ingest log, `/trigger` manual trigger,
`/gitops` config PRs.

## 5. Jenkins

Jenkins is **not bundled** and is not installed by the standard setup. The
dispatcher core and panel run without it, but the webhook → pipeline → PR flow
requires a Jenkins you operate.

- **Local WAR install:** `bash scripts/jenkins/setup.sh` then
  `bash scripts/jenkins/start.sh`.
- **Your own Jenkins:** install the plugins in
  `scripts/jenkins/plugins.txt`, add this repo as a global shared library named
  `fleet-config`, provide nodes labeled `fleet-agent` (plus
  `fleet-agent-macos` / `fleet-agent-windows` for bare-metal), and create the
  credentials `fleet-webhook-token`, `fleet-github-read`,
  `fleet-github-token`, and one per `[agent].llm_env`.

See [`jenkins-node.md`](./jenkins-node.md) and [`triggers.md`](./triggers.md).

## 6. Landing page (optional)

The marketing site is a static Astro build in `website/`.

```bash
bash website/start.sh            # dev server on 0.0.0.0:4100
bash website/start.sh --build    # production build + preview
bash website/start.sh --daemon   # background; stop with website/stop.sh
```

Set `SITE_URL=https://your.domain` at build time to bake the canonical origin
into the page and sitemap.

## 7. Verify

```bash
bash scripts/smoke.sh    # sandbox smoke test, no LLM key required
bash scripts/ci.sh          # fleetctl unit tests + schema validation
bash scripts/ci-admin.sh    # admin: compile + format + tests
```

## Next

- Configure how tasks enter fleet: [`triggers.md`](./triggers.md).
- Security model and credentials: [`security.md`](./security.md).
