"""GitHub Issues webhook normalizer (stub).

Reserved for a follow-up. The registry already supports
``sources.github.fallback_repo_from_issue: true`` so this adapter can resolve a
repo straight from ``repository.full_name``.
"""

from __future__ import annotations

from typing import Any, Optional

from ..models import Issue
from .base import Normalizer


class GithubIssuesNormalizer(Normalizer):
    source = "github"

    def normalize(
        self,
        payload: dict[str, Any],
        *,
        event: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> Optional[Issue]:
        raise NotImplementedError(
            "GitHub Issues adapter is not implemented yet (planned after the Jira MVP)"
        )
