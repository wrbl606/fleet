"""Normalizer factory."""

from __future__ import annotations

from ..errors import ValidationError
from .base import Normalizer
from .github import GithubNormalizer
from .jira import JiraNormalizer
from .linear import LinearNormalizer

_REGISTRY: dict[str, type[Normalizer]] = {
    "jira": JiraNormalizer,
    "linear": LinearNormalizer,
    "github": GithubNormalizer,
}


def get_normalizer(source: str, **kwargs) -> Normalizer:
    try:
        cls = _REGISTRY[source]
    except KeyError:
        raise ValidationError(
            f"unknown webhook source {source!r}; known: {', '.join(sorted(_REGISTRY))}"
        ) from None
    if source == "jira":
        return JiraNormalizer(trigger_label=kwargs.get("trigger_label", "agent"))
    if source == "github":
        return GithubNormalizer(
            comment_prefix=kwargs.get("comment_prefix", "/agent"),
            author_associations=kwargs.get("comment_author_associations"),
            allow_users=kwargs.get("comment_allow_users"),
            bot_logins=kwargs.get("comment_bot_logins"),
        )
    return cls()


__all__ = [
    "Normalizer",
    "JiraNormalizer",
    "LinearNormalizer",
    "GithubNormalizer",
    "get_normalizer",
]
