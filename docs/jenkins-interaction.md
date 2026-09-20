# Jenkins ↔ fleet interaction

fleet deliberately keeps **Jenkins thin**. Jenkins is the trigger and
orchestrator; the `fleet` project (`fleetctl`) owns all the logic. The same
`fleetctl` commands that run in a Jenkins build run identically on a laptop, so
CI behaviour is not special-cased.

## Direction of interaction

```
webhook ─▶ Jenkins (GWT) ─▶ fleetDispatcher.groovy ─▶ fleetctl CLI ─▶ GitHub / COI / panel
                                   ▲                        │
                                   └──── result.json ◀──────┘
```

- **Jenkins → fleet**: starts `fleetctl` stages, binds credentials, routes the
  run to a node, provides the workspace, and reports the final build result.
- **fleet → Jenkins**: each stage prints JSON on stdout that the next stage
  consumes (`issue.json` → `plan.json` → `result.json`); `fleetctl notify`
  reports to the panel; `fleetctl publish` writes back to GitHub.

## The flow, step by step

1. A Jira/GitHub/Linear webhook hits the **Generic Webhook Trigger**:
   `POST {jenkins}/generic-webhook-trigger/invoke?token={fleet-webhook-token}&source={jira|github|linear}`.
   GWT exposes the raw body as `payload`; GitHub's event name arrives in the
   `X-GitHub-Event` header (`x_github_event`).
2. The job's `Jenkinsfile` loads the GitOps config repo as a shared library and
   calls `fleetDispatcher()`:
   ```groovy
   @Library('fleet-config@main') _
   fleetDispatcher()
   ```
3. `vars/fleetDispatcher.groovy` resolves the source (explicit `source` param,
   else inferred from `X-GitHub-Event`) and runs three stages:
   - **Normalize** (`built-in` node): `python3 -m fleetctl normalize` turns the
     webhook into a canonical issue and decides if it is actionable. Non-actionable
     events end the build as `SUCCESS`.
   - **Resolve**: `fleetctl resolve` reads the registry and returns the target
     `repo`, `base_branch`, and `jenkins_label`.
   - **Run** (on the resolved `jenkins_label` node): clones the target repo,
     builds the plan with `fleetctl plan`, checks out the PR head branch for
     comment runs, then executes `fleetctl run` — the bounded COI/native agent
     loop plus publish/PR/reply.
4. `reportResult()` reads `result.json` and sets the Jenkins build result
   (`SUCCESS`, or `FAILURE` on `failed`/`verify_failed`).

## What Jenkins provides to fleet

| Concern | How Jenkins helps |
|---|---|
| Ingress | Generic Webhook Trigger (token auth, JSON parsing, headers) |
| Secrets | `withCredentials` binding `fleet-github-token`, `fleet-github-read`, and the agent's `llm_env` key |
| Routing | `node(plan.jenkins_label)` picks the worker that has the COI/native toolchain |
| Workspace | `checkout scm` + `stash`/`unstash` move `issue.json` between stages |
| Evidence | `archiveArtifacts result.json, plan.json` and the console log |
| Result | `currentBuild.result` from the run outcome |

Fleet code arrives in the workspace via `checkout scm`; the CLI is invoked with
`PYTHONPATH=$WORKSPACE`, and containers are read by `fleetctl` directly, so
Jenkins never needs to know about COI.

## What fleet does (not Jenkins)

Normalization rules, registry/project routing, `.fleet/` manifest + COI config,
the bounded agent loop, git commit/push, PR creation/replies, and panel
notification. This keeps Jenkins plugins out of the critical path: upgrading
fleet means updating `fleetctl` + the config snapshot, not rewriting pipeline
logic.

## Feedback to the panel

Two independent paths:

- `fleetctl notify` → `POST /api/ingest` with `run.started` / `run.finished`
  (ledger rows used by the runs UI).
- `fleetctl normalize` / `resolve` with `--ingest` → `webhook.received`,
  `normalize.result`, `resolve.result`, shown on the panel `/ingest` page for
  debugging normalization and routing.

## Where to look

- Pipeline orchestration: `vars/fleetDispatcher.groovy`, `Jenkinsfile`
- CLI stages: `fleetctl/cli.py` (`normalize`, `resolve`, `plan`, `run`)
- Node/credential requirements: [`jenkins-node.md`](./jenkins-node.md)
- Config contract: [`fleet-contract.md`](./fleet-contract.md)
