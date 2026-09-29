# AGENTS.md

Guidance for agents and contributors working in this repository.

## Project shape

- `fleetctl/` — dispatcher core (Python, stdlib-first): normalize, resolve, plan,
  run, publish, notify.
- `admin/` — Phoenix LiveView admin panel + ingest API (`POST /api/ingest`,
  `POST /api/trigger`, `GET /api/metrics`).
- `website/` — Astro landing page and docs (`/docs`); `website-phoenix/` is the
  retired Phoenix implementation, kept only for reference.
- `Jenkinsfile`, `vars/` — Jenkins trigger + orchestration.
- `docs/` — canonical documentation.

## Documentation must track the implementation

**Keep the docs up to date with the current implementation.** Whenever behavior
changes, update everything that describes it in the same change:

- `README.md`
- `docs/*.md`
- the website docs and copy under `website/src/`

This matters most for the **ingest endpoint and forwarding** path, which has
changed and drifted before. If you touch any of the following, update
[`docs/triggers.md`](./docs/triggers.md), [`docs/installation.md`](./docs/installation.md),
the README "Webhooks" section, and `website/src/pages/docs/triggers.astro`:

- the roles of `POST /api/ingest` (webhook-with-`source` → record + forward vs.
  lifecycle sink without `source`);
- authentication (`FLEET_INGEST_TOKEN` bearer, `FLEET_GITHUB_WEBHOOK_SECRET`
  HMAC, `x-fleet-source` / `x-fleet-event` headers);
- forwarding to the dispatcher (`FLEET_WEBHOOK_URL` / `FLEET_WEBHOOK_TOKEN`,
  passthrough `x-github-*` headers, verbatim body);
- `FLEET_INGEST_PUBLIC_URL`, `/api/trigger`, and the `/ingest` log events;
- trigger configuration for Jira / GitHub / Linear and the Jenkins Generic
  Webhook Trigger variables.

When you add an env var, endpoint, event, or header, document it in the same PR.
The website `/docs` pages are the public-facing mirror of `docs/`; keep them in
sync with the markdown.

## Ground rules

- Never commit secrets. LLM keys and GitHub tokens are injected by Jenkins; the
  agent never receives a GitHub token.
- Trusted policy (routing, allowlists, sandbox profiles, caps) lives in
  `registry.yaml`, not in source repos.
- Keep `registry.yaml` / `.fleet/fleet.toml` and their JSON Schemas in sync, and
  add tests for behavior changes.

## Checks before opening a PR

```bash
bash scripts/ci.sh         # fleetctl unit tests + contract/schema validation
bash scripts/ci-admin.sh   # admin: compile --warnings-as-errors + format + tests
```

Website (if changed):

```bash
cd website && npm run build
```
