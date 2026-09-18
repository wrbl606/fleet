# Custom COI images

The dispatcher runs **setup, agent, and verify as separate ephemeral COI
containers**; only the workspace is bind-mounted and persists between them. A
toolchain installed by `setup.sh` therefore does **not** reach the agent or
verify steps. Per-language toolchains (Flutter, Rust, JVM, …) must be baked into
a custom image instead.

## Build a profile image

Profiles live in `~/.coi/profiles/<name>/` and are built from a
`[container.build]` section:

```bash
mkdir -p ~/.coi/profiles
cp -r resources/coi/fleet-flutter ~/.coi/profiles/
coi build --profile fleet-flutter
```

Then point a repo at it in `.fleet/fleet.toml`:

```toml
[coi]
profile = "fleet-flutter"
```

`Resolution` carries the profile through; `CoiRunnerBackend` invokes
`coi run --profile fleet-flutter -- …`, and the trusted `$COI_CONFIG` is applied
on top (network, limits, monitoring, `forward_env`).

## Included: `fleet-flutter`

`resources/coi/fleet-flutter/` builds `coi-fleet-flutter` from `coi-default`
(Ubuntu 24.04) and adds:

- Flutter SDK (`FLUTTER_VERSION`, default `3.47.4`) at `/opt/flutter`, on
  `PATH` as `flutter`/`dart`
- a warmed Linux artifact cache for the runtime `code` user

A Flutter repo opts in via `.fleet/fleet.toml` (`[coi] profile = "fleet-flutter"`)
and typically runs `flutter pub get && flutter analyze && flutter test` in its
`.fleet/verify.sh`.

## Notes

- The build downloads ~1.5 GB; raise `FLUTTER_VERSION` to match the repo's
  `pubspec.lock` constraint.
- The generated COI policy sets `auto_pause_on_high = false` because allowlist
  mode blocks DNS, and the security monitor reports those blocked attempts as
  high-severity false positives; critical threats still auto-kill.
- Agent/COI runtime artifacts (`.claude/`, `.opencode/`) are added to
  `.git/info/exclude` by the trusted publisher so they never land in a commit.
