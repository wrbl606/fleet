# Jenkins node requirements

fleet splits work between two roles. Locally they are the same host; in
production they can be separate machines.

- **Jenkins controller** — runs the Jenkinsfile / `fleetDispatcher` shared
  library: trigger plumbing, node routing, credential binding.
- **Build node** — the machine labeled `fleet-agent` where `fleetctl` executes:
  normalize, resolve, plan, the bounded COI/native loop, publish, notify.

Jenkins itself is installed separately (see the README). Verify host tooling
with:

```bash
python3 -m fleetctl env-check --platform linux
```

## Jenkins controller

- Jenkins LTS with a **JDK 17/21**.
- Plugins from [`scripts/jenkins/plugins.txt`](../scripts/jenkins/plugins.txt):
  `configuration-as-code`, `job-dsl`, `workflow-aggregator`,
  `pipeline-utility-steps`, `generic-webhook-trigger`, `git`,
  `credentials-binding`.
- The `fleet-config` **shared library** reachable over SCM. The bundled local
  Jenkins uses a `file://` snapshot in `$FLEET_JENKINS_STATE_DIR/fleet-config-git`
  created by `scripts/jenkins/prepare-local.sh`; a real Jenkins points at the
  git repo instead.
- **Credentials** (bound per run by `vars/fleetDispatcher.groovy`):

  | Credential id | Purpose |
  |---|---|
  | `fleet-webhook-token` | Generic Webhook Trigger token |
  | `fleet-github-read` | read token for `git clone` |
  | `fleet-github-token` | scoped token for `git push` + `gh pr create` |
  | agent `llm_env` name (e.g. `OPENCODE_GO_SUBSCRIPTION_KEY`) | LLM key forwarded into the sandbox |

- `mise` only if you use the bundled helper scripts (`setup.sh` installs the JDK
  through it).

## Linux / COI build node (`fleet-agent`)

- Linux x86_64 (COI is Incus-based).
- **Python 3.11+** and pip, with `PyYAML>=6.0` and `jsonschema>=4.18`
  (`pip install -r requirements.txt`). The pipeline installs them automatically
  if missing. `fleetctl` is **not** installed as a package — it runs from the
  checked-out workspace via `PYTHONPATH`.
- **git** for the host-side clone/commit/push.
- **[`gh`](https://cli.github.com/)** for PR creation; `GH_TOKEN` is injected by
  Jenkins.
- **Incus** installed and initialized (storage pool + network), with the build
  user in the **`incus-admin`** group and an unprivileged default profile:

  ```bash
  sudo adduser "$USER" incus-admin && newgrp incus-admin
  incus profile show default | grep security.privileged   # must be absent/false
  ```

- **`coi`** (code-on-incus, v0.11+) on `PATH`, able to talk to Incus. Build the
  base image once, plus any custom profile image a repo selects:

  ```bash
  coi health
  coi build                              # coi-default
  coi build --profile fleet-flutter      # custom, e.g. resources/coi/fleet-flutter
  ```

- Disk and CPU for ephemeral containers, sized for the images in use.
- Network egress to the git host, to the reachable `FLEET_INGEST_URL`, and —
  inside the sandbox — the allowlisted model/package domains.

Runtime environment on the node (Jenkins env or JCasC):

| Variable | Purpose |
|---|---|
| `FLEET_DRY_RUN` | `0` enables real push + PR; anything else is a dry run |
| `FLEET_REGISTRY_LOCAL` | optional path to a git-ignored `registry.local.yaml` overlay |
| `FLEET_GIT_BASE_URL` | git host base; empty means `https://github.com` |
| `FLEET_INGEST_URL` / `FLEET_INGEST_TOKEN` | admin-panel run notifications |
| `GH_TOKEN`, LLM key | injected per run from Jenkins credentials |

The agent CLI (`opencode`/`claude`/`codex`) does **not** need to be on the node
for COI runs — it lives inside the COI image.

## Native build nodes (`fleet-agent-macos` / `fleet-agent-windows`)

- git, `gh`, Python 3.11+, the **agent CLI**, and the repo's language toolchain.
- macOS: Seatbelt (built-in). Windows: PowerShell plus the trusted wrapper
  [`resources/native/windows-sandbox.ps1`](../resources/native/windows-sandbox.ps1).
- Trusted native sandbox configs live on the host, never in the untrusted repo —
  see [`bare-metal-hardening.md`](./bare-metal-hardening.md).

## Not required

- **Docker** — COI uses Incus.
- The **admin panel** — separate host; Elixir/Erlang are only needed there.
- The **LLM key on disk** — Jenkins injects it per run.
- **root / passwordless sudo** for immutable protection — fleet sets
  `security.host_immutable = false`, keeping the node unprivileged.
