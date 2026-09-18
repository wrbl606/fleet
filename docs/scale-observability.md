# Scale & observability (P5)

## Scaling the pool (plan §12)

- **Linux / COI** scales horizontally: many Incus containers per node,
  second-scale start, resource-capped per container. Add nodes with the
  `fleet-agent` label; the dispatcher's `node(plan.jenkins_label)` schedules
  onto any of them.
- **macOS / Windows** pools are bounded by machine count. Only tasks whose
  registry entry sets that `platform` (and that pass the allowlist) route
  there; everything else stays on the default Linux path.
- **Queueing** is Jenkins'. For bursts, add ephemeral nodes with the same
  label — see `resources/jenkins/jcasc.yaml` (EC2 spot example). Optionally
  use Throttle Concurrent Builds or the lockable-resources plugin to cap
  per-node containers.

The dispatcher spends no controller time on the sandbox: the plan is computed
on a lightweight node, the loop runs on the routed worker.

## Audit shipping

COI writes host-side threat events to `~/.coi/audit/<container>.jsonl`
(`coi audit`). Two shipping paths:

1. **To the admin panel** as `audit.event` records (drives the run detail's
   audit table and the `fleet_runs_*` metrics):

   ```bash
   FLEET_INGEST_URL=https://panel/api/ingest \
   FLEET_INGEST_TOKEN=... \
   FLEET_REPO=acme/engine FLEET_ISSUE_KEY=ENG-1 FLEET_BRANCH=fleet/ENG-1 \
     scripts/ship-audit.sh --follow
   ```

2. **To a SIEM** (Elastic/Logstash) with Filebeat or Fluent Bit, alongside OS
   audit logs: `resources/siem/filebeat.yml`, `resources/siem/fluent-bit.conf`.

## Dashboards

- **Live panel** (P6): the Run LiveView streams updates over WebSockets as
  `run.finished` / `audit.event` payloads arrive at `/api/ingest`.
- **Prometheus/Grafana**: scrape `GET /api/metrics` (bearer
  `FLEET_INGEST_TOKEN`). Exposes:

  ```
  fleet_runs_total{status="succeeded"} 12
  fleet_runs_total{status="failed"} 1
  fleet_runs_active 3
  fleet_runs_tracked_total 16
  ```

  Suggested alerts: `fleet_runs_active` stuck high (leaked containers),
  rising `failed` rate, and `verify_failed` ratio per repo.

## Data flow

```
Jenkins pipeline ──POST run.finished──▶ panel /api/ingest ──▶ SQLite ledger
coi audit JSONL ──ship-audit.sh───────▶ panel /api/ingest ──▶ audit_events
panel /api/ingest ──PubSub "runs"─────▶ Run LiveView (browser)
panel /api/metrics ◀── scrape ────────── Prometheus ──▶ Grafana
```

## Sizing notes

- COI per-container caps come from `registry.yaml` (`coi.limits`) and are
  clamped, so a repo cannot starve a node.
- Keep `numExecutors` on Linux nodes ≥ expected concurrent containers; the
  container, not the executor, is the unit of isolation.
- Bare-metal nodes run one job at a time (`mode: EXCLUSIVE`) because they are
  not disposable.
