# The `.fleet/` contract

Every source repository may carry a `.fleet/` directory describing how fleet
agents should work on it. Everything is declarative; no secrets live here.

```
.fleet/
  fleet.toml          # manifest (declarative)
  prompts/task.md     # prompt template, {{var}}-rendered
  setup.sh            # env setup: install deps/toolchain (idempotent)
  verify.sh           # code-quality gate: lint + test (exit 0 = pass)
  pr-template.md      # optional PR body template
```

Reference: [`examples/sample-repo/.fleet/`](../examples/sample-repo/.fleet/).
Schema: [`schemas/fleet.schema.json`](../schemas/fleet.schema.json).

## `fleet.toml`

```toml
version = 1

[agent]
tool           = "claude"            # claude | codex | opencode | pi | custom
prompt_file    = "prompts/task.md"   # exactly one of prompt_file | inline
# inline       = "Fix {{issue.key}}"
# command      = ["my-agent", "--task", "{{prompt}}"]   # custom / pinned flags
max_iterations = 3                   # bounded verify-fail loop
llm_env        = "ANTHROPIC_API_KEY" # NAME only; value lives in Jenkins
# llm_credential_id = "fleet-anthropic"   # optional Jenkins credential id

[setup]
script = "setup.sh"                  # run before the agent, inside the sandbox

[verify]
script = "verify.sh"                 # run after the agent, inside the sandbox

[pr]
branch_prefix = "fleet/"
base          = "main"
title         = "{{issue.key}}: {{issue.summary}}"
labels        = ["agent"]
body_file     = "pr-template.md"

[platform]                           # optional; default = linux
os       = "linux"                   # linux | macos | windows
requires = []                        # capability labels, e.g. ["xcode-15"]
arch     = "amd64"

[coi]                                # Linux-only; cannot widen registry caps
profile = ""                         # empty -> built-in COI default
network = "restricted"               # restricted | allowlist | open
timeout = "30m"                      # clamped to registry.coi.timeout_cap

[comment]                            # optional; PR-comment trigger behavior
enabled   = true                     # whether /agent comments run this repo
mode      = "auto"                   # auto | code | answer
reply     = true                     # post a comment back on the PR
reply_file = "reply.md"              # agent-written reply, else a summary
```

Notes:

- `setup.sh` / `verify.sh` are resolved **relative to `.fleet/`**. `verify.sh`
  is the gate: exit non-zero and the failure output is appended to the next
  agent iteration, up to `max_iterations`; exhausted ⇒ the job fails.
- `[coi].network = "allowlist"` adds the repo's `allowed_domains` to the
  registry's trusted list. `restricted` allows internet egress but no LAN.
- If `[coi].profile` is empty and the repo is not in
  `allowlist.trusted_repos`, the dispatcher applies the registry's
  `coi.untrusted_profile` (default `hardened`).
- Timing/resource limits may be *requested* by the repo but are clamped by the
  registry: the repo can never widen its own CPU/memory/disk/timeout caps.
- Unknown tools require an explicit `[agent].command` containing `{{prompt}}`.

## Prompt templating

`{{...}}` substitution over a canonical context:

```
{{issue.key}} {{issue.summary}} {{issue.description}} {{issue.type}}
{{issue.labels}} {{issue.project}} {{issue.component}} {{issue.team}}
{{issue.reporter}} {{issue.url}}
{{source}} {{repo}} {{platform}} {{pr.title}}
{{mode}} {{pr.number}} {{pr.url}} {{pr.head_branch}} {{pr.base_branch}}
{{pr.head_repo}}
{{comment.body}} {{comment.command}} {{comment.author}} {{comment.url}}
```

Unknown expressions fail the run (strict mode) rather than shipping a blank
instruction. `{{issue.labels}}` renders as a comma-joined list.

### PR-comment triggers

A GitHub `issue_comment` (or `pull_request_review_comment`) whose body starts
with the trusted prefix (`/agent` by default) starts a run against the PR's
existing branch. On a **plain issue** (no pull request), an `/agent` comment
instead starts the normal new-PR issue flow for that issue. `[comment].mode`
selects the behavior:

- `auto` (default) — reply always; push a commit to the PR branch only if the
  agent changed files.
- `code` — require a change and push.
- `answer` — reply only, never touch git.

The prefix and **who may trigger** (`OWNER`/`MEMBER`/`COLLABORATOR` plus a user
allowlist) live in the trusted `registry.yaml` (`sources.github`), not here.
Fork PRs are reply-only. See [`plans/pr-comment-trigger.md`](./plans/pr-comment-trigger.md).

## Validation

```bash
python3 -m fleetctl validate --registry registry.yaml --repo-dir /path/to/repo --coi
```

Validates `registry.yaml` and every `.fleet/fleet.toml` against the JSON
schemas, then generates the trusted COI config and validates it with
`coi validate profile`.
