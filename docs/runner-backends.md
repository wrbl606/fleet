# Runner backends

The dispatcher only knows the `RunnerBackend` interface:

```python
run_setup() -> StepResult
run_agent(prompt) -> StepResult
run_verify() -> StepResult
cleanup()
```

The execution line is the only platform-specific part
([`fleetctl/runners.py`](../fleetctl/runners.py)).

| Host | Backend | Isolation | Invocation |
|---|---|---|---|
| Linux | `CoiRunnerBackend` | Incus system container + active defense | `coi run [--profile P] --workspace W -- <cmd>` |
| macOS | `NativeRunnerBackend` | Seatbelt (deny-default, trusted profile) | `sandbox-exec -D WORKSPACE=<ws> -f seatbelt.sb <cmd>` |
| Windows | `NativeRunnerBackend` | Trusted wrapper (timeout + trimmed env; AppContainer/WinSandbox via host image) | `<wrapper...> <cmd>` |

The native sandbox command is chosen from `registry.yaml` (`native:`) and
attached to `Resolution.native_options`; the repo can never supply or relax it.
A missing Seatbelt profile fails closed. See
[`bare-metal-hardening.md`](./bare-metal-hardening.md).

## Routing

`registry.yaml` (optionally per source entry) sets `platform` and `requires`.
`Resolution.jenkins_label` is derived:

```
linux   -> fleet-agent
macos   -> fleet-agent-macos
windows -> fleet-agent-windows
+ each capability label, AND-joined (`fleet-agent-macos && xcode-15`)
```

The pipeline computes the resolution on a lightweight node, then schedules the
work on `node(plan.jenkins_label)`.

## Fail-closed native execution

`platform != linux` requires the repo to be in `allowlist.native_repos` **or**
to carry a label in `allowlist.native_labels`. Otherwise `Registry.resolve`
raises `AllowlistError` and the job fails — it never silently runs unisolated.
`NativeRunnerBackend` additionally refuses to instantiate for a linux task or
on the wrong OS.

## Agent invocation map

| Tool | Invocation inside `coi run --` |
|---|---|
| claude | `claude -p "<prompt>" --dangerously-skip-permissions` |
| codex | `codex exec --full-auto "<prompt>"` |
| opencode | `opencode run "<prompt>"` |
| pi | `pi run "<prompt>"` |
| custom | `[agent].command` with `{{prompt}}` substituted |

CLI flags drift by tool version: pin exact argv in `[agent].command` when a
tool's flags change. See [`fleetctl/agents.py`](../fleetctl/agents.py).

## Secret injection

- **Linux/COI**: the trusted host-side config sets
  `forward_env = ["<llm_env>"]`; COI reads the value from the host environment
  at session start. Only the declared name is forwarded.
- **Bare-metal**: Jenkins credentials binding + `withEnv`, per run, never
  persisted.

## Current limitation

The bounded loop runs setup/agent/verify as separate `coi run` invocations, so
each step starts an ephemeral container and only the workspace persists through
the mount. This is the isolation-first default from the plan.

Consequence: toolchains installed by `setup.sh` do not reach the agent/verify
steps. Bake language toolchains into a **custom COI image** and select it with
`[coi].profile` — see [`coi-images.md`](./coi-images.md) (the `fleet-flutter`
profile is an example). A future optimisation can pin one session/container
across the three steps via `[container] persistent = true`.
