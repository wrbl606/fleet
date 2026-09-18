"""``{{var}}`` prompt/PR templating over a canonical issue context.

Supported expressions (dotted lookups into the context mapping)::

    {{issue.key}} {{issue.summary}} {{issue.description}} {{issue.type}}
    {{issue.labels}} {{issue.project}} {{issue.component}} {{issue.url}}
    {{source}} {{repo}} {{platform}} {{pr.title}}

Unknown expressions raise :class:`RenderError` in strict mode (the default), so
a typo in a prompt template fails the run instead of silently shipping a blank
instruction to the agent.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from .errors import RenderError
from .models import Issue

_VAR_RE = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")


def build_context(
    issue: Issue,
    *,
    repo: str = "",
    platform: str = "linux",
    pr_title: str = "",
) -> dict[str, Any]:
    """Build the canonical template context from a normalized issue."""
    return {
        "source": issue.source,
        "repo": repo,
        "platform": platform,
        "pr": {"title": pr_title},
        "issue": {
            "key": issue.key,
            "summary": issue.summary,
            "description": issue.description,
            "type": issue.issue_type,
            "labels": ", ".join(issue.labels),
            "project": issue.project,
            "component": issue.component or "",
            "team": issue.team or "",
            "reporter": issue.reporter or "",
            "url": issue.url,
        },
    }


def _lookup(context: dict[str, Any], expr: str) -> Any:
    cur: Any = context
    for part in expr.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise RenderError(f"unknown template variable '{expr}'")
        cur = cur[part]
    return cur


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(_stringify(v) for v in value)
    return str(value)


def render(template: str, context: dict[str, Any], *, strict: bool = True) -> str:
    """Substitute every ``{{...}}`` expression in *template*."""
    if template is None:
        return ""

    def _sub(match: re.Match[str]) -> str:
        expr = match.group(1)
        try:
            return _stringify(_lookup(context, expr))
        except RenderError:
            if strict:
                raise
            return match.group(0)

    return _VAR_RE.sub(_sub, template)


def render_file(path: str, context: dict[str, Any], *, strict: bool = True) -> str:
    p = Path(path)
    if not p.is_file():
        raise RenderError(f"template file not found: {path}")
    return render(p.read_text(), context, strict=strict)


def referenced_vars(template: str) -> set[str]:
    """Return the set of expressions referenced by a template."""
    return set(_VAR_RE.findall(template or ""))
