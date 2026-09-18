"""Notifications + run ledger ingest (P2).

Both integrations are opt-in and degrade to a no-op when their credentials /
endpoints are absent, so the pipeline still succeeds without the admin panel or
Jira API access. Failures never mask the run result.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from .models import RunPlan, RunResult

_TIMEOUT = 30


def notify_issue(plan: RunPlan, message: str) -> bool:
    """Comment *message* on the originating Jira issue, if configured."""
    if plan.issue.source != "jira":
        return False
    base = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN")
    if not (base and email and token and plan.issue.key):
        return False

    url = f"{base}/rest/api/3/issue/{plan.issue.key}/comment"
    payload = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": message}],
                }
            ],
        }
    }
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    return _post(url, payload, headers={"Authorization": f"Basic {auth}"})


def external_id(plan: RunPlan) -> str:
    """Stable run identity.

    Includes the triggering comment id for ``pr_comment`` runs so successive
    ``/agent`` comments on the same PR are recorded as separate runs.
    """
    repo = plan.repo or plan.resolution.repo
    branch = plan.branch()
    key = plan.issue.key
    if plan.issue.is_pr_comment and plan.issue.comment_id:
        return f"{repo}#{key}@{branch}#c{plan.issue.comment_id}"
    return f"{repo}#{key}@{branch}"


def post_run_finished(plan: RunPlan, result: RunResult) -> bool:
    """POST a run-finished event to the admin panel ingest API, if configured."""
    url = os.environ.get("FLEET_INGEST_URL")
    if not url:
        return False
    payload: dict[str, Any] = {
        "event": "run.finished",
        "external_id": external_id(plan),
        "issue": plan.issue.to_dict(),
        "repo": result.repo,
        "branch": result.branch,
        "status": result.status,
        "pr_url": result.pr_url,
        "reply_url": result.reply_url,
        "mode": plan.mode,
        "comment_url": plan.issue.comment_url,
        "comment_command": plan.issue.command or plan.issue.comment_body,
        "tool": plan.manifest.agent.tool,
        "iterations": [i.to_dict() for i in result.iterations],
        "error": result.error,
        "build_url": result.build_url,
        "build_number": result.build_number,
    }
    headers: dict[str, str] = {}
    token = os.environ.get("FLEET_INGEST_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return _post(url, payload, headers=headers)


def _post(url: str, payload: dict[str, Any], *, headers: Optional[dict[str, str]] = None) -> bool:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return False
