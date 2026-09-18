"""Trusted publisher step (P2).

Runs **outside** the sandbox, on the Jenkins host, after the agent loop. The
agent never receives a GitHub credential: it only edits files. Here we commit
with a pinned bot identity, push the ``fleet/<issue-key>`` branch, and open a
PR with the scoped token supplied via ``GH_TOKEN`` / ``GITHUB_TOKEN``.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

from .errors import PublishError
from .exec_ import Executor
from .models import RunPlan

_SANITIZE = re.compile(r"[^A-Za-z0-9._-]+")

#: Agent/COI runtime artifacts that may appear in the workspace; excluding them
#: host-side keeps them out of commits without editing the target repo.
RUNTIME_EXCLUDE_PATTERNS = (".claude/", ".opencode/", ".codex/", ".fleet-tmp/")


def _write_runtime_excludes(workspace: str) -> None:
    exclude = Path(workspace) / ".git" / "info" / "exclude"
    if not exclude.parent.is_dir():
        return
    existing = exclude.read_text() if exclude.is_file() else ""
    additions = [p for p in RUNTIME_EXCLUDE_PATTERNS if p not in existing]
    if not additions:
        return
    with exclude.open("a") as fh:
        if existing and not existing.endswith("\n"):
            fh.write("\n")
        fh.write("\n# fleet agent runtime artifacts\n")
        for pattern in additions:
            fh.write(pattern + "\n")



@dataclass
class PublishResult:
    status: str  # succeeded | no_changes
    branch: str
    pr_url: Optional[str] = None
    changed_files: list[str] = field(default_factory=list)
    reply_url: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "branch": self.branch,
            "pr_url": self.pr_url,
            "changed_files": self.changed_files,
            "reply_url": self.reply_url,
        }


def branch_name(plan: RunPlan) -> str:
    key = _SANITIZE.sub("-", plan.issue.key).strip("-")
    return f"{plan.manifest.pr.branch_prefix}{key}"


def changed_files(executor: Executor, workspace: str) -> list[str]:
    result = executor.run(
        ["git", "status", "--porcelain"], cwd=workspace, timeout=60
    )
    files = []
    for line in result.stdout.splitlines():
        line = line.rstrip()
        if not line:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path)
    return files


def publish(
    plan: RunPlan,
    workspace: str,
    executor: Executor,
    *,
    bot_name: str,
    bot_email: str,
    body: str,
    base_branch: Optional[str] = None,
    dry_run: bool = False,
) -> PublishResult:
    base = base_branch or plan.manifest.pr.base
    branch = plan.branch()
    wants_reply = plan.issue.is_pr_comment and plan.manifest.comment.reply

    # Keep agent/COI runtime artifacts out of the commit (host-side, untracked).
    _write_runtime_excludes(workspace)

    files = changed_files(executor, workspace)

    # For PR updates the agent may have committed inside the sandbox, so a clean
    # working tree is not "no changes": count commits ahead of the PR head too.
    env: Optional[Mapping[str, str]] = None
    ahead = 0
    if plan.update_existing_branch and plan.head_branch and not dry_run:
        env = _token_env()
        # Explicit refspec: single-branch shallow clones do not create
        # refs/remotes/origin/<branch> for other branches otherwise.
        fetch = executor.run(
            [
                "git",
                "fetch",
                "--depth",
                "50",
                "origin",
                f"+{plan.head_branch}:refs/remotes/origin/{plan.head_branch}",
            ],
            cwd=workspace,
            env=env,
            timeout=600,
        )
        if fetch.exit_code != 0:
            raise PublishError(
                f"git fetch failed (exit {fetch.exit_code}): "
                f"{fetch.stderr.strip() or fetch.stdout.strip()}"
            )
        ahead = _rev_count(executor, workspace, env, f"origin/{plan.head_branch}..HEAD")
        if ahead:
            files = _diff_files(
                executor, workspace, env, f"origin/{plan.head_branch}..HEAD"
            )

    have_changes = bool(files) or ahead > 0

    if plan.mode == "new_pr" and not files:
        return PublishResult(status="no_changes", branch=branch)

    # Reply-only: forced ``answer``, or ``auto`` with nothing to push.
    if plan.mode == "answer" or (plan.mode == "auto" and not have_changes):
        if wants_reply:
            reply = body or _reply_body(plan, workspace, files, pushed=False)
            reply_url = None
            if not dry_run:
                reply_url = _comment_on_pr(plan, reply, _token_env(), executor, workspace)
            return PublishResult(
                status="succeeded",
                branch=branch,
                pr_url=plan.pr_url,
                changed_files=files,
                reply_url=reply_url,
            )
        return PublishResult(
            status="no_changes", branch=branch, pr_url=plan.pr_url, changed_files=files
        )

    if dry_run:
        return PublishResult(
            status="succeeded",
            branch=branch,
            pr_url=plan.pr_url or "(dry-run)",
            changed_files=files,
        )

    if env is None:
        env = _token_env()

    def run(argv: list[str], *, name: str, timeout: float = 300) -> None:
        res = executor.run(argv, cwd=workspace, env=env, timeout=timeout)
        if res.exit_code != 0:
            raise PublishError(
                f"{name} failed (exit {res.exit_code}): {res.stderr.strip() or res.stdout.strip()}"
            )

    if plan.update_existing_branch and plan.head_branch:
        if ahead == 0:
            # No agent commits: align to the PR head, then commit the changes.
            run(
                ["git", "checkout", "-B", branch, f"origin/{branch}"],
                name="git checkout",
            )
    else:
        run(["git", "checkout", "-B", branch], name="git checkout")

    run(["git", "add", "-A"], name="git add")
    # The agent may have committed already (``ahead`` > 0, nothing staged); only
    # create a commit when the working tree has changes to record.
    if _has_staged(executor, workspace, env):
        # Identity is passed per-command (-c) rather than written to .git/config:
        # the COI sandbox protects .git/config read-only, and a trusted host-side
        # publisher must not depend on being able to rewrite it.
        run(
            [
                "git",
                "-c",
                f"user.name={bot_name}",
                "-c",
                f"user.email={bot_email}",
                "commit",
                "-m",
                plan.pr_title,
            ],
            name="git commit",
            timeout=60,
        )

    origin = executor.run(
        ["git", "remote", "get-url", "origin"], cwd=workspace, env=env, timeout=30
    ).stdout.strip()
    push_argv = [
        "git",
        "push",
        "--force-with-lease",
        _push_target(origin, plan.repo, env.get("GH_TOKEN", "")),
        branch,
    ]
    if plan.update_existing_branch:
        # Append to the PR branch: never force over human commits.
        push_argv = [
            "git",
            "push",
            _push_target(origin, plan.repo, env.get("GH_TOKEN", "")),
            branch,
        ]
    run(push_argv, name="git push", timeout=600)

    pr_url = plan.pr_url or _create_pr(plan, branch, base, body, env, executor, workspace)
    reply_url = None
    if wants_reply:
        reply = body or _reply_body(plan, workspace, files, pushed=True)
        reply_url = _comment_on_pr(plan, reply, env, executor, workspace)
    return PublishResult(
        status="succeeded",
        branch=branch,
        pr_url=pr_url,
        changed_files=files,
        reply_url=reply_url,
    )


def _rev_count(executor: Executor, workspace: str, env: Mapping[str, str], rev: str) -> int:
    res = executor.run(
        ["git", "rev-list", "--count", rev], cwd=workspace, env=env, timeout=60
    )
    try:
        return int(res.stdout.strip() or "0")
    except ValueError:
        return 0


def _diff_files(
    executor: Executor, workspace: str, env: Mapping[str, str], rev: str
) -> list[str]:
    res = executor.run(
        ["git", "diff", "--name-only", rev], cwd=workspace, env=env, timeout=60
    )
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


def _has_staged(executor: Executor, workspace: str, env: Mapping[str, str]) -> bool:
    # `git diff --cached --quiet` exits 1 when there are staged changes.
    res = executor.run(
        ["git", "diff", "--cached", "--quiet"], cwd=workspace, env=env, timeout=60
    )
    return res.exit_code != 0


def _reply_body(plan: RunPlan, workspace: str, files: list[str], *, pushed: bool) -> str:
    from .planner import render_comment_reply

    return render_comment_reply(plan, workspace, files, pushed=pushed)


def _comment_on_pr(
    plan: RunPlan,
    body: str,
    env: Mapping[str, str],
    executor: Executor,
    workspace: str,
) -> Optional[str]:
    """Post a comment on the PR conversation; returns its URL."""
    number = plan.pr_number or plan.issue.pr_number
    if not number:
        return None
    fd, path = tempfile.mkstemp(prefix="fleet-reply-", suffix=".md")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(body)
        res = executor.run(
            [
                "gh",
                "pr",
                "comment",
                str(number),
                "--repo",
                plan.repo,
                "--body-file",
                path,
            ],
            cwd=workspace,
            env=env,
            timeout=180,
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    if res.exit_code != 0:
        raise PublishError(
            f"gh pr comment failed (exit {res.exit_code}): "
            f"{res.stderr.strip() or res.stdout.strip()}"
        )
    return _first_url(res.stdout) or res.stdout.strip() or None


def _push_target(origin: str, repo: str, token: str) -> str:
    """Push URL for the trusted publisher.

    Uses the scoped publish token over HTTPS so the clone's (read) credentials
    in ``origin`` are never reused for a write. Falls back to ``origin`` for
    non-HTTP remotes (e.g. local ``file://`` dev repos).
    """
    match = re.match(r"https?://(?:[^@/]+@)?([^/]+)/", origin or "")
    if not match:
        return origin or "origin"
    host = match.group(1)
    if token:
        return f"https://x-access-token:{token}@{host}/{repo}.git"
    return origin


def _create_pr(
    plan: RunPlan,
    branch: str,
    base: str,
    body: str,
    env: Mapping[str, str],
    executor: Executor,
    workspace: str,
) -> str:
    argv = [
        "gh",
        "pr",
        "create",
        "--repo",
        plan.repo,
        "--base",
        base,
        "--head",
        branch,
        "--title",
        plan.pr_title,
        "--body",
        body,
    ]
    for label in plan.manifest.pr.labels:
        argv += ["--label", label]

    res = executor.run(argv, cwd=workspace, env=env, timeout=300)
    if res.exit_code == 0:
        return _first_url(res.stdout) or res.stdout.strip()

    if "already exists" in (res.stderr + res.stdout).lower():
        view = executor.run(
            ["gh", "pr", "view", branch, "--repo", plan.repo, "--json", "url", "-q", ".url"],
            cwd=workspace,
            env=env,
            timeout=120,
        )
        if view.exit_code == 0 and view.stdout.strip():
            return view.stdout.strip()

    raise PublishError(
        f"gh pr create failed (exit {res.exit_code}): {res.stderr.strip() or res.stdout.strip()}"
    )


def _first_url(text: str) -> Optional[str]:
    for token in text.split():
        if token.startswith("http"):
            return token.strip()
    return None


def _token_env() -> Mapping[str, str]:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise PublishError(
            "no GitHub token in GH_TOKEN/GITHUB_TOKEN; refusing to publish"
        )
    return {"GH_TOKEN": token, "GITHUB_TOKEN": token}
