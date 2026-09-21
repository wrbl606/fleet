"""GitHub webhook normalizer.

Actionable events:

* ``issues`` — issue ``opened`` (existing new-PR flow).
* ``issue_comment`` — ``created`` comment whose body starts with the trusted
  ``/agent`` prefix. On a **pull request** it updates that PR ("action" mode)
  and/or answers ("answer" mode); on a **plain issue** it starts the normal
  new-PR issue flow for that issue.
* ``pull_request_review_comment`` — inline review comment, same prefix rules.

The prefix and who-may-trigger policy are **trusted** (registry
``sources.github``), never supplied by the repo. Bot/self comments are ignored
to prevent loops.

Note: ``issue_comment`` payloads do not carry the PR head/base refs, so those
are filled by an enrichment step (``fleetctl.github_api``) before planning.
``pull_request_review_comment`` payloads include ``pull_request`` and need no
fetch.
"""

from __future__ import annotations

from typing import Any, Optional

from ..models import Issue
from .base import Normalizer, _need

ISSUES = "issues"
ISSUE_COMMENT = "issue_comment"
REVIEW_COMMENT = "pull_request_review_comment"

DEFAULT_PREFIX = "/agent"
DEFAULT_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")


class GithubNormalizer(Normalizer):
    source = "github"

    def __init__(
        self,
        *,
        comment_prefix: str = DEFAULT_PREFIX,
        author_associations: Optional[list[str]] = None,
        allow_users: Optional[list[str]] = None,
        bot_logins: Optional[list[str]] = None,
    ) -> None:
        self.comment_prefix = comment_prefix or DEFAULT_PREFIX
        self.author_associations = {
            a.upper() for a in (author_associations or DEFAULT_ASSOCIATIONS)
        }
        self.allow_users = {u.lower() for u in (allow_users or [])}
        self.bot_logins = {b.lower() for b in (bot_logins or [])}

    def normalize(
        self,
        payload: dict[str, Any],
        *,
        event: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> Optional[Issue]:
        name = self._event_name(payload, event, headers)
        if name == ISSUES:
            return self._issue(payload)
        if name == ISSUE_COMMENT:
            return self._comment(payload, inline=False)
        if name == REVIEW_COMMENT:
            return self._comment(payload, inline=True)
        return None

    # -- events -------------------------------------------------------------

    @staticmethod
    def _event_name(
        payload: dict[str, Any],
        event: Optional[str],
        headers: Optional[dict[str, str]],
    ) -> str:
        if event:
            return event.strip()
        for key, value in (headers or {}).items():
            if key.lower().replace("_", "-") == "x-github-event":
                return str(value).strip()
        # Best-effort inference for panel-triggered payloads without a header.
        if "comment" in payload and "issue" in payload:
            return ISSUE_COMMENT
        if payload.get("action") in ("created", "opened", "reopened"):
            return ISSUES
        return ""

    def _issue(self, payload: dict[str, Any]) -> Optional[Issue]:
        if payload.get("action") not in ("opened", "reopened"):
            return None
        issue = payload.get("issue")
        if not isinstance(issue, dict):
            raise _bad("issue")
        repo = _need(payload, "repository.full_name")
        number = _need(issue, "number")
        repository = payload.get("repository") or {}
        default_branch = repository.get("default_branch")
        return Issue(
            source=self.source,
            key=f"{repo}#{number}",
            summary=str(issue.get("title", "")),
            description=str(issue.get("body") or ""),
            labels=self._labels(issue),
            project=repo,
            reporter=self._login(issue.get("user")),
            url=str(issue.get("html_url", "")),
            repo_hint=str(repo),
            default_branch=str(default_branch) if default_branch else None,
            event=ISSUES,
        )

    def _comment(self, payload: dict[str, Any], *, inline: bool) -> Optional[Issue]:
        if payload.get("action") != "created":
            return None
        comment = payload.get("comment")
        if not isinstance(comment, dict):
            raise _bad("comment")
        body = str(comment.get("body") or "")
        command = self._match_command(body)
        if command is None:
            return None

        user = comment.get("user") or {}
        login = str(user.get("login") or "")
        association = str(comment.get("author_association") or "").upper()
        if not self._authorized(login, association, user):
            return None

        repo = str(_need(payload, "repository.full_name"))
        pr = payload.get("pull_request") or {}
        if inline:
            if not isinstance(pr, dict) or not pr:
                raise _bad("pull_request")
            number = int(_need(pr, "number"))
            head = pr.get("head") or {}
            base = pr.get("base") or {}
            head_repo = (head.get("repo") or {}).get("full_name")
            head_branch = head.get("ref")
            base_branch = base.get("ref")
            state = pr.get("state")
        else:
            issue = payload.get("issue")
            if not isinstance(issue, dict):
                raise _bad("issue")
            number = int(_need(issue, "number"))
            if not issue.get("pull_request"):
                # Plain issue: the comment kicks off the normal new-PR flow, so
                # an operator can start work with `/agent` on the issue itself
                # instead of needing a PR to exist first.
                return self._issue_from_comment(
                    payload, issue, repo, number, body, command, login, association
                )
            head_repo = head_branch = base_branch = state = None

        summary = command.splitlines()[0].strip() if command.strip() else f"PR #{number} comment"
        return Issue(
            source=self.source,
            key=f"{repo}#{number}",
            summary=summary or f"PR #{number} comment",
            description=command,
            labels=self._labels(payload.get("issue") or {}),
            project=repo,
            reporter=login,
            url=str(comment.get("html_url", "")),
            repo_hint=repo,
            event=REVIEW_COMMENT if inline else ISSUE_COMMENT,
            kind="pr_comment",
            pr_number=number,
            pr_head_branch=str(head_branch) if head_branch else None,
            pr_base_branch=str(base_branch) if base_branch else None,
            pr_head_repo=str(head_repo) if head_repo else None,
            pr_state=str(state) if state else None,
            comment_id=int(comment["id"]) if comment.get("id") is not None else None,
            comment_url=str(comment.get("html_url") or ""),
            comment_body=body,
            command=command.strip(),
            author=login or None,
            author_association=association or None,
        )

    # -- helpers ------------------------------------------------------------

    def _issue_from_comment(
        self,
        payload: dict[str, Any],
        issue: dict[str, Any],
        repo: str,
        number: int,
        body: str,
        command: str,
        login: str,
        association: str,
    ) -> Issue:
        """A plain-issue comment trigger: run the issue's new-PR flow."""
        comment = payload.get("comment") or {}
        repository = payload.get("repository") or {}
        default_branch = repository.get("default_branch")
        return Issue(
            source=self.source,
            key=f"{repo}#{number}",
            summary=str(issue.get("title", "")),
            description=str(issue.get("body") or ""),
            labels=self._labels(issue),
            project=repo,
            reporter=self._login(issue.get("user")),
            url=str(issue.get("html_url", "")),
            repo_hint=repo,
            default_branch=str(default_branch) if default_branch else None,
            event=ISSUE_COMMENT,
            kind="issue",
            comment_id=int(comment["id"]) if comment.get("id") is not None else None,
            comment_url=str(comment.get("html_url") or ""),
            comment_body=body,
            command=command.strip(),
            author=login or None,
            author_association=association or None,
        )

    def _match_command(self, body: str) -> Optional[str]:
        text = (body or "").strip()
        prefix = self.comment_prefix
        if not text.startswith(prefix):
            return None
        rest = text[len(prefix):]
        if rest and not rest[0].isspace():
            return None
        return rest.strip()

    def _authorized(
        self, login: str, association: str, user: dict[str, Any]
    ) -> bool:
        if not login:
            return False
        if str(user.get("type") or "").lower() == "bot":
            return False
        if login.lower().endswith("[bot]"):
            return False
        if login.lower() in self.bot_logins:
            return False
        if login.lower() in self.allow_users:
            return True
        return association in self.author_associations

    @staticmethod
    def _labels(issue: dict[str, Any]) -> list[str]:
        labels = issue.get("labels") or []
        result = []
        for label in labels:
            if isinstance(label, dict):
                result.append(str(label.get("name", "")))
            else:
                result.append(str(label))
        return [x for x in result if x]

    @staticmethod
    def _login(user: Any) -> Optional[str]:
        if isinstance(user, dict) and user.get("login"):
            return str(user["login"])
        return None


def _bad(path: str):
    from ..errors import ValidationError

    return ValidationError(f"github payload missing '{path}'")
