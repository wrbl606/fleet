"""Normalizer factory."""

from __future__ import annotations

from ..errors import ValidationError
from .base import Normalizer
from .github import GithubIssuesNormalizer
from .jira import JiraNormalizer
from .linear import LinearNormalizer

_REGISTRY: dict[str, type[Normalizer]] = {
    "jira": JiraNormalizer,
    "linear": LinearNormalizer,
    "github": GithubIssuesNormalizer,
}


def get_normalizer(source: str, **kwargs) -> Normalizer:
    try:
        cls = _REGISTRY[source]
    except KeyError:
        raise ValidationError(
            f"unknown webhook source {source!r}; known: {', '.join(sorted(_REGISTRY))}"
        ) from None
    if source == "jira":
        return JiraNormalizer(**kwargs)
    return cls()


__all__ = [
    "Normalizer",
    "JiraNormalizer",
    "LinearNormalizer",
    "GithubIssuesNormalizer",
    "get_normalizer",
]
