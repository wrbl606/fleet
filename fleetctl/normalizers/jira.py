"""Jira webhook normalizer (P1 MVP).

Actionable events:
  * ``jira:issue_created``
  * ``jira:issue_updated`` where the changelog touches labels AND the issue
    currently carries the configured trigger label (default ``agent``).

Jira Cloud sends Atlassian Document Format (ADF) for rich-text fields; the
description is flattened to plain text.
"""

from __future__ import annotations

from typing import Any, Optional

from ..models import Issue
from .base import Normalizer, _need

CREATED = "jira:issue_created"
UPDATED = "jira:issue_updated"


def adf_to_text(node: Any) -> str:
    """Flatten an ADF document (or plain string) into readable text."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_text(n) for n in node)
    if not isinstance(node, dict):
        return str(node)

    ntype = node.get("type")
    if ntype == "text":
        return node.get("text", "")
    if ntype == "hardBreak":
        return "\n"
    if ntype == "mention":
        return "@" + str(node.get("attrs", {}).get("text", "")).lstrip("@")
    if ntype == "emoji":
        return node.get("attrs", {}).get("text", "")

    inner = adf_to_text(node.get("content", []))
    block = {
        "paragraph",
        "heading",
        "blockquote",
        "listItem",
        "bulletList",
        "orderedList",
        "codeBlock",
        "rule",
        "tableRow",
    }
    if ntype in block:
        sep = "\n" if ntype != "listItem" else "\n"
        return inner + sep
    return inner


class JiraNormalizer(Normalizer):
    source = "jira"

    def __init__(self, trigger_label: str = "agent") -> None:
        self.trigger_label = trigger_label

    def normalize(
        self,
        payload: dict[str, Any],
        *,
        event: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> Optional[Issue]:
        event = payload.get("webhookEvent") or event or ""
        if event == UPDATED and not self._label_added(payload):
            return None
        if event not in (CREATED, UPDATED):
            return None

        issue = payload.get("issue")
        if not isinstance(issue, dict):
            raise _bad("payload.issue")
        fields = issue.get("fields") or {}

        components = fields.get("components") or []
        component = components[0].get("name") if components else None

        reporter = (fields.get("reporter") or {}).get("displayName")

        return Issue(
            source=self.source,
            key=str(_need(payload, "issue.key")),
            summary=str(fields.get("summary", "")),
            description=adf_to_text(fields.get("description")),
            issue_type=str((fields.get("issuetype") or {}).get("name", "")),
            labels=[str(x) for x in (fields.get("labels") or [])],
            project=str((fields.get("project") or {}).get("key", "")),
            component=component,
            reporter=reporter,
            url=self._browse_url(payload, issue),
            event=event,
        )

    @staticmethod
    def _browse_url(payload: dict[str, Any], issue: dict[str, Any]) -> str:
        browse = issue.get("browseUrl")
        if browse:
            return str(browse)
        self_url = str(issue.get("self", ""))
        marker = "/rest/api/"
        if marker in self_url:
            base, _, _ = self_url.partition(marker)
            return f"{base}/browse/{issue.get('key', '')}"
        site = payload.get("site") or {}
        if site.get("url"):
            return f"{site['url'].rstrip('/')}/browse/{issue.get('key', '')}"
        return ""

    def _label_added(self, payload: dict[str, Any]) -> bool:
        issue = payload.get("issue") or {}
        fields = issue.get("fields") or {}
        labels = [str(x) for x in (fields.get("labels") or [])]
        if self.trigger_label not in labels:
            return False
        for item in (payload.get("changelog") or {}).get("items", []):
            if item.get("field") == "labels":
                return True
        return False


def _bad(path: str):
    from ..errors import ValidationError

    return ValidationError(f"jira payload missing '{path}'")
