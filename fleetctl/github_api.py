"""GitHub REST helpers for PR-comment enrichment.

An ``issue_comment`` webhook payload does not include the pull request's head or
base refs (only ``issue.pull_request`` URLs), so the PR has to be fetched before
we can clone/update the right branch. ``pull_request_review_comment`` payloads
include ``pull_request`` and do not need this.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from .errors import ValidationError
from .models import Issue

_API = "https://api.github.com"
_TIMEOUT = 30


def _token() -> Optional[str]:
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def fetch_pull_request(
    repo: str, number: int, *, token: Optional[str] = None
) -> dict[str, Any]:
    token = token or _token()
    if not token:
        raise ValidationError("no GH_TOKEN/GITHUB_TOKEN for PR enrichment")
    req = urllib.request.Request(f"{_API}/repos/{repo}/pulls/{number}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "fleet-dispatcher")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise ValidationError(
            f"github PR enrichment failed ({exc.code}) for {repo}#{number}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise ValidationError(f"github PR enrichment error: {exc}") from exc


def enrich_issue_pr(issue: Issue, *, token: Optional[str] = None) -> Issue:
    """Fill PR head/base/state on an ``issue_comment`` issue (idempotent)."""
    if not issue.is_pr_comment or issue.pr_head_branch:
        return issue
    if not issue.repo_hint or not issue.pr_number:
        return issue
    data = fetch_pull_request(issue.repo_hint, issue.pr_number, token=token)
    head = data.get("head") or {}
    base = data.get("base") or {}
    if head.get("ref"):
        issue.pr_head_branch = str(head["ref"])
    if base.get("ref"):
        issue.pr_base_branch = str(base["ref"])
    head_repo = (head.get("repo") or {}).get("full_name")
    if head_repo:
        issue.pr_head_repo = str(head_repo)
    if data.get("state"):
        issue.pr_state = str(data["state"])
    return issue
