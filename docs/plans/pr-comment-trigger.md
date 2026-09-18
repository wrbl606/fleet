# Plan: PR-comment trigger (`/agent`)

Status: **P1/P2 implemented; verified end-to-end via Jenkins**
Owner: fleet
Related: `docs/fleet-contract.md`, `docs/security.md`, `docs/runner-backends.md`

## Implemented

- GitHub normalizer (`issues`, `issue_comment`, `pull_request_review_comment`),
  trusted prefix + author policy, bot filtering, PR enrichment for
  `issue_comment`.
- `Issue`/`RunPlan`/`FleetManifest[comment]` model, modes `new_pr | auto |
  update_pr | answer`, fork → answer.
- Publisher pushes agent-authored commits to the existing PR branch (explicit
  fetch refspec, no force) and replies on the PR conversation.
- Jenkins: GWT `X-GitHub-Event`/`X-GitHub-Delivery`, source inference, read-token
  binding for enrichment, PR-head checkout, `disableConcurrentBuilds`.
- Admin panel: run ledger persists `mode`/`comment_url`/`comment_command`/
  `reply_url`; run detail shows them; Trigger page has a GitHub PR-comment preset.

## Remaining

- Idempotency/dedupe (comment id / `X-GitHub-Delivery`) and an ack reaction.
- Per-branch concurrency lock (currently serialized job-wide).
- Fork PRs are reply-only and run against the base checkout.

## Goal

A GitHub `issue_comment` (and `pull_request_review_comment`) webhook on a pull
request whose body starts with a prefix (`/agent` by default) triggers the
agent to:

- **act** on the comment — make changes and push them to the PR's existing head
  branch, and
- **answer** — reply on the PR conversation with a summary/answer.

Unlike the issue flow, this does **not** open a new PR.

## Decisions (locked)

| # | Decision |
|---|---|
| 1 | Replies go to the **PR conversation only**. |
| 2 | Default mode is **auto**: always reply; commit/push only if the agent changed files. |
| 3 | Trigger allowed for `author_association ∈ {OWNER, MEMBER, COLLABORATOR}` **plus** an explicit user allowlist; prefix policy lives in the trusted registry. |
| 4 | **Any non-base branch** may be updated (no `fleet/*`-only restriction); never the base branch. |
| 5 | Inline **review comments** (`pull_request_review_comment`) are in scope. |
| 6 | **Fork PRs are reply-only** (cannot push to the fork). |

## Model

- **Trigger kinds:** `issue` (existing) and `pr_comment` (new).
- **Execution modes** (`RunPlan.mode`):
  - `new_pr` — existing issue flow.
  - `auto` — PR comment: reply always; push to the head branch iff files changed.
  - `update_pr` — force push to the head branch.
  - `answer` — reply only, no git mutations.
- Manifest `[comment]` maps to a mode: `auto` → `auto`, `code` → `update_pr`,
  `answer` → `answer`.

## Pieces

1. **`Issue`** gains `kind`, `pr_number`, `pr_head_branch`, `pr_base_branch`,
   `pr_head_repo`, `pr_state`, `comment_id`, `comment_url`, `comment_body`,
   `command`, `author`, `author_association`.
2. **`GithubIssuesNormalizer`** handles `issues`, `issue_comment`,
   `pull_request_review_comment`; parses the prefix; enforces author policy;
   skips bot authors; returns `None` for non-actionable events.
3. **PR enrichment:** an `issue_comment` payload has no head/base refs, so the
   CLI fetches them via the GitHub API (read token) before planning. Review
   comments already carry `pull_request` and need no fetch.
4. **Trusted policy** in `registry.yaml` `sources.github`: `comment_prefix`,
   `comment_author_associations`, `comment_allow_users`, `comment_bot_logins`.
5. **Manifest `[comment]`** (repo-controlled behavior): `enabled`, `mode`,
   `reply`, `reply_file`.
6. **Prompt context** gains `{{comment.body}}`, `{{comment.command}}`,
   `{{mode}}`, `{{pr.number}}`, `{{pr.head_branch}}`, `{{pr.base_branch}}`,
   `{{pr.url}}`, `{{pr.head_repo}}`.
7. **Publisher:** for `auto`/`update_pr` fetch + checkout the existing head
   branch, **append** a commit (no force), push with the scoped token, then
   reply. For `answer` / no changes: reply only. Never push to the base branch;
   fork PRs are reply-only.
8. **Reply:** `gh pr comment <n> --repo <repo> --body-file …`; body is the
   agent-written `.fleet/<reply_file>` when present, else a generated summary.
9. **Jenkins:** GWT captures `X-GitHub-Event` / `X-GitHub-Delivery`; source is
   inferred (`issues`/`issue_comment`/`pull_request_review_comment` → github);
   Normalize binds the read token for enrichment; the worker fetches + checks
   out the PR head branch after cloning.
10. **Panel:** runs store `comment_url` / `comment_body` / `reply_url`; Trigger
    page gains a GitHub PR-comment preset.

## Security

- Prefix + who-may-trigger come from the **trusted registry**, never the repo.
- Bot/self comments are ignored (loop prevention); dedupe by comment id /
  `X-GitHub-Delivery`.
- Comment text is untrusted input to the agent: sandbox + verify + human merge.
- Reply is public — prefer an agent-authored reply file / generated summary,
  not raw sandbox logs.

## Out of scope (now)

- Auto-merge; multi-turn chat beyond one comment-per-run; non-GitHub chat
  sources; pushing to forks.

## Tests

Normalizer (prefix hit/miss, bot author, unauthorized association, non-PR
comment, edited/deleted events, review comments), registry policy parsing,
planner mode/branch selection, publisher update/append vs answer-only, reply
argv, schema round-trips, panel ingest.
