"""Trusted publisher step (P2).

Runs **outside** the sandbox, on the Jenkins host, after the agent loop. The
agent never receives a GitHub credential: it only edits files. Here we commit
with a pinned bot identity, push the ``fleet/<issue-key>`` branch, and open a
PR with the scoped token supplied via ``GH_TOKEN`` / ``GITHUB_TOKEN``.
"""

from __future__ import annotations

import os
import re
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

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "branch": self.branch,
            "pr_url": self.pr_url,
            "changed_files": self.changed_files,
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
    branch = branch_name(plan)
    base = base_branch or plan.manifest.pr.base

    # Keep agent/COI runtime artifacts out of the commit (host-side, untracked).
    _write_runtime_excludes(workspace)

    files = changed_files(executor, workspace)
    if not files:
        return PublishResult(status="no_changes", branch=branch)

    if dry_run:
        return PublishResult(
            status="succeeded", branch=branch, pr_url="(dry-run)", changed_files=files
        )

    env = _token_env()

    def run(argv: list[str], *, name: str, timeout: float = 300) -> None:
        res = executor.run(argv, cwd=workspace, env=env, timeout=timeout)
        if res.exit_code != 0:
            raise PublishError(
                f"{name} failed (exit {res.exit_code}): {res.stderr.strip() or res.stdout.strip()}"
            )

    run(
        ["git", "config", "user.name", bot_name],
        name="git config user.name",
        timeout=30,
    )
    run(
        ["git", "config", "user.email", bot_email],
        name="git config user.email",
        timeout=30,
    )
    run(["git", "checkout", "-B", branch], name="git checkout")
    run(["git", "add", "-A"], name="git add")
    run(["git", "commit", "-m", plan.pr_title], name="git commit", timeout=60)
    run(
        ["git", "push", "--force-with-lease", "-u", "origin", branch],
        name="git push",
        timeout=600,
    )

    pr_url = _create_pr(plan, branch, base, body, env, executor, workspace)
    return PublishResult(
        status="succeeded", branch=branch, pr_url=pr_url, changed_files=files
    )


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
