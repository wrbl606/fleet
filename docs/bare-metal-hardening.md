# Bare-metal hardening runbook (P4)

Long-lived, dedicated macOS/Windows agent nodes are **not** disposable, so host
hardening is mandatory (plan §8). This maps each requirement to an artifact.

| # | Requirement | Artifact |
|---|---|---|
| 1 | Least-privilege service account, no interactive login, no stored keys | `scripts/hardening/macos.sh`, `scripts/hardening/windows.ps1` |
| 2 | No secrets at rest; per-run Jenkins binding | `vars/fleetDispatcher.groovy` (`withCredentials` + `withEnv`) |
| 3 | Fail-closed native allowlist | `fleetctl/registry.py` (`native_repos` / `native_labels`) |
| 4 | Optional OS sandbox per untrusted repo | `resources/native/seatbelt.sb`, `resources/native/windows-sandbox.ps1` |
| 5 | Host egress control | `resources/native/pf-fleet-egress.conf` (macOS PF), firewall in `windows.ps1` |
| 6 | Hard runtime/resource caps | executor timeout + `windows-sandbox.ps1` tree-kill; macOS `launchctl` limits |
| 7 | Audit + integrity | `auditconfig` (macOS) / `auditpol` (Windows) + `resources/siem/` |
| 8 | Segregated network/VLAN | Infrastructure; keep the bare-metal pool off the COI VLAN |

## Routing & sandbox selection

`registry.yaml` owns the trusted OS-sandbox policy; the untrusted repo can only
declare `[platform].os` / `requires`:

```yaml
native:
  macos:
    seatbelt_profile: "resources/native/seatbelt.sb"
  windows:
    wrapper: ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
              "-File", "resources/native/windows-sandbox.ps1", "--"]
```

`Registry.resolve` attaches these to the `Resolution.native_options`; the
`NativeRunnerBackend` wraps every setup/agent/verify command:

- macOS → `sandbox-exec -D WORKSPACE=<ws> -f seatbelt.sb <cmd>`
- Windows → `<wrapper...> <cmd>`

A missing Seatbelt profile **fails closed** (`RunnerError`), as does a Windows
task on a non-Windows host or a native backend for a Linux/COI task.

## Procedure (per node)

```bash
# macOS
sudo scripts/hardening/macos.sh
# Windows (elevated PowerShell)
powershell -ExecutionPolicy Bypass -File scripts/hardening/windows.ps1
```

Then register the node with the capability labels the registry routes on, e.g.

```
fleet-agent-macos macos amd64 xcode-15
fleet-agent-windows windows amd64 msvc-2022
```

## Verifying fail-closed behaviour

```bash
# A macos task for a non-allowlisted repo is rejected before any execution:
python3 -m fleetctl resolve --registry registry.yaml --issue-file ios.json
# -> AllowlistError: ... is not in allowlist.native_repos ...
```

Unit tests cover the wrapper construction and the fail-closed checks:
`tests/test_native_runner.py`, `tests/test_registry.py`.

## Not provided

Enterprise MDM enrolment, VLAN configuration, and SIEM tenant setup are
infrastructure concerns outside this repo. Seatbelt is deprecated by Apple;
migrate to App Sandbox / endpoint-security policy when your macOS baseline
requires it — only `resources/native/seatbelt.sb` and the `-D` invocation in
`NativeRunnerBackend` change.
