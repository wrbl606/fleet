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
    wants_reply = (
        plan.issue.is_pr_comment and plan.manifest.comment.reply and bool(body)
    )

    # Keep agent/COI runtime artifacts out of the commit (host-side, untracked).
    _write_runtime_excludes(workspace)

    files = changed_files(executor, workspace)

    if plan.mode == "new_pr" and not files:
        return PublishResult(status="no_changes", branch=branch)

    # Reply-only path: forced ``answer`` mode, or ``auto`` with nothing to push.
    if plan.mode == "answer" or (plan.mode == "auto" and not files):
        reply_url = None
        if wants_reply and not dry_run:
            reply_url = _comment_on_pr(plan, body, _token_env(), executor, workspace)
        status = "succeeded" if (wants_reply or files) else "no_changes"
        return PublishResult(
            status=status,
            branch=branch,
            pr_url=plan.pr_url,
            changed_files=files,
            reply_url=reply_url,
        )

    if dry_run:
        return PublishResult(
            status="succeeded",
            branch=branch,
            pr_url=plan.pr_url or "(dry-run)",
            changed_files=files,
        )

    env = _token_env()

    def run(argv: list[str], *, name: str, timeout: float = 300) -> None:
        res = executor.run(argv, cwd=workspace, env=env, timeout=timeout)
        if res.exit_code != 0:
            raise PublishError(
                f"{name} failed (exit {res.exit_code}): {res.stderr.strip() or res.stdout.strip()}"
            )

    if plan.update_existing_branch and plan.head_branch:
        # Act on an existing PR: fetch the head branch and append (no force).
        run(
            ["git", "fetch", "--depth", "50", "origin", plan.head_branch],
            name="git fetch",
            timeout=600,
        )
        run(
            ["git", "checkout", "-B", branch, f"origin/{branch}"],
            name="git checkout",
        )
    else:
        run(["git", "checkout", "-B", branch], name="git checkout")

    run(["git", "add", "-A"], name="git add")
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
        push_argv = ["git", "push", _push_target(origin, plan.repo, env.get("GH_TOKEN", "")), branch]
    run(push_argv, name="git push", timeout=600)

    pr_url = plan.pr_url or _create_pr(plan, branch, base, body, env, executor, workspace)
    reply_url = None
    if wants_reply:
        reply_url = _comment_on_pr(plan, body, env, executor, workspace)
    return PublishResult(
        status="succeeded",
        branch=branch,
        pr_url=pr_url,
        changed_files=files,
        reply_url=reply_url,
    )


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
