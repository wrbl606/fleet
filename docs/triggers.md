# Triggers & ingest

A task starts when a PM-tool webhook reaches the dispatcher. Senders POST to the
admin panel's **ingest endpoint**, which records the event and forwards it
verbatim to the Jenkins **Generic Webhook Trigger** — or you can point senders
straight at Jenkins.

The website mirrors this guide at `/docs/triggers`.

## How a trigger flows

```
Jira / GitHub / Linear
        │  POST {panel}/api/ingest?source=<source>
        ▼
Admin panel   ── record webhook.received ──▶ run ledger / ingest log
        │  POST {FLEET_WEBHOOK_URL}?source=<source>&token=<token>
        ▼  headers: x-fleet-event, x-github-event, x-github-delivery
Jenkins Generic Webhook Trigger
        │
        ▼
fleetDispatcher → fleetctl normalize → resolve → run → publish
```

## The ingest endpoint

`POST /api/ingest` has two roles, selected by whether a `source` is present.
This is the current logic: a webhook that carries a source is **recorded and
forwarded**; everything else is a ledger sink.

| Request | Behaviour |
|---|---|
| `POST /api/ingest?source=<source>` | **Inbound webhook.** Records `webhook.received` (source, event, payload) and forwards the raw body to `FLEET_WEBHOOK_URL`. The source may also arrive as an `x-fleet-source` header. |
| `POST /api/ingest` (no source) | **Ledger sink.** Records dispatcher lifecycle + debug events (`run.started`, `run.finished`, `audit.event`, `webhook.received`, `normalize.result`, `resolve.result`). Never forwarded. |
| `POST /api/trigger` | Low-level: forward to the dispatcher *without* the ingest hop (same path the Trigger page and scripts use). Restricted to `jira`, `linear`, `github`; injects the `webhookEvent` field. |
| `GET /api/metrics` | Prometheus text-format ledger metrics. |

### Event name

- Set with `?event=` or the `x-fleet-event` header.
- For GitHub the dispatcher derives it from the passed-through
  `X-GitHub-Event` header.
- The normalizer decides whether an event is actionable; unknown sources/events
  are rejected there.

### Authentication

- `Authorization: Bearer <FLEET_INGEST_TOKEN>` — the panel's own calls, the
  dispatcher, scripts, and PM tools that can set headers.
- `X-Hub-Signature-256` HMAC over the raw body — for GitHub, whose webhooks
  cannot set custom headers. Set the shared secret as
  `FLEET_GITHUB_WEBHOOK_SECRET` (same value as the GitHub webhook's **Secret**).
- Comparison is constant-time. When neither the token nor the secret is
  configured the API is open — **dev only**.
- Invalid/missing credentials return `401`; invalid payloads return `422`.

### Response

```
201 {"ok": true, "id": 42, "forward": {"status": 200}}
201 {"ok": true, "id": 42, "forward": {"dry_run": true}}
201 {"ok": true, "id": 42, "forward": {"error": "webhook endpoint not configured"}}
```

## Forwarding to Jenkins

The panel forwards the payload **unchanged** — no field injection — so the
dispatcher sees exactly what the PM tool sent. Retries are disabled.

```
POST {FLEET_WEBHOOK_URL}?source=<source>&token=<FLEET_WEBHOOK_TOKEN>
Authorization: Bearer <FLEET_WEBHOOK_TOKEN>
x-fleet-event: <event>
x-github-event: <passthrough, GitHub only>
x-github-delivery: <passthrough, GitHub only>
Content-Type: application/json

<raw webhook body, unchanged>
```

The forwarding target is trusted configuration (`FLEET_WEBHOOK_URL` /
`FLEET_WEBHOOK_TOKEN`) and is never supplied by the caller. The public URL of
the panel's own ingest endpoint is `FLEET_INGEST_PUBLIC_URL` (falls back to the
panel's endpoint URL).

## Configure a source

### GitHub (recommended path)

GitHub authenticates with its webhook **Secret**; the panel records and forwards
it.

```
Payload URL:  {FLEET_INGEST_PUBLIC_URL}?source=github
Content type: application/json
Secret:       <FLEET_GITHUB_WEBHOOK_SECRET>
Events:       issues, issue_comment, pull_request_review_comment
```

### Jira

If Jira can set an `Authorization` header on webhooks, point it at the panel.
Jira Cloud cannot set custom headers, so send Jira webhooks **directly to
Jenkins** — the Generic Webhook Trigger authenticates with the token in the
query string.

```
POST {panel}/api/ingest?source=jira
Authorization: Bearer <FLEET_INGEST_TOKEN>

# or directly to Jenkins (no panel ingest-log entry):
POST {jenkins}/generic-webhook-trigger/invoke?token=<fleet-webhook-token>&source=jira
```

### Linear

Same trade-off as Jira: use the panel with a bearer header when supported, or
send events straight to the Jenkins trigger URL with `&source=linear`.

```
POST {panel}/api/ingest?source=linear
Authorization: Bearer <FLEET_INGEST_TOKEN>
Events: Issue create / update
```

## Jenkins Generic Webhook Trigger

The trigger is declared by the pipeline's `properties(...)` block, so it
registers on the first build. Create a Jenkins string credential named
`fleet-webhook-token`; its value is the `token` in the invoke URL and in
`FLEET_WEBHOOK_TOKEN`.

```groovy
properties([
  disableConcurrentBuilds(),
  pipelineTriggers([[
    $class: 'GenericTrigger',
    genericVariables: [[key: 'payload', value: '$', expressionType: 'JSONPath']],
    genericRequestVariables: [[key: 'source', regexpFilter: '']],
    genericHeaderVariables: [
      [key: 'x-fleet-event', regexpFilter: ''],
      [key: 'x-github-event', regexpFilter: ''],
      [key: 'x-github-delivery', regexpFilter: '']
    ],
    tokenCredentialId: 'fleet-webhook-token',
    causeString: 'Fleet webhook ($source)'
  ]])
])
```

See [`jenkins-interaction.md`](./jenkins-interaction.md) for the full pipeline.

## Panel trigger page & API

The `/trigger` page and `POST /api/trigger` fire a webhook-like event through the
dispatcher without a real PM tool — useful for end-to-end tests. Use `dry_run` to
preview the exact request.

```bash
curl -X POST {panel}/api/trigger \
  -H "Authorization: Bearer $FLEET_INGEST_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"source":"jira","event":"jira:issue_created","payload":{"issue":{"key":"ENG-1"}}}'
```

## Local development

The bundled local Jenkins and panel wire this up with placeholder tokens —
change them before exposing either host
([`security.md#local-development-defaults`](./security.md#local-development-defaults--change-before-any-real-deployment)).

```bash
bash scripts/jenkins/setup.sh && bash scripts/jenkins/start.sh
bash scripts/jenkins/prepare-local.sh
bash admin/start.sh            # FLEET_WEBHOOK_URL defaults to the local Jenkins
```

## Debugging

The `/ingest` page shows every incoming webhook, the normalization outcome
(`ok` / `filtered` / `error`), and the routing decision — the fastest way to see
why an event did not start a run. The dispatcher reports these events when
`fleetctl normalize` / `resolve` run with `--ingest`.

## Where to look

- Endpoint + forwarding: `admin/lib/fleet_admin/ingest.ex`,
  `admin/lib/fleet_admin/trigger.ex`, `admin/lib/fleet_admin_web/controllers/ingest_controller.ex`
- Auth: `admin/lib/fleet_admin_web/plugs/api_auth.ex`
- Jenkins wiring: `Jenkinsfile`, `vars/fleetDispatcher.groovy`
