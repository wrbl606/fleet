"""Linear webhook normalizer (stub).

Reserved for a follow-up. Implements the same :class:`Normalizer` interface as
:class:`~fleetctl.normalizers.jira.JiraNormalizer` so wiring it in is a
one-line registry/factory change.
"""

from __future__ import annotations

from typing import Any, Optional

from ..models import Issue
from .base import Normalizer


class LinearNormalizer(Normalizer):
    source = "linear"

    def normalize(
        self,
        payload: dict[str, Any],
        *,
        event: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> Optional[Issue]:
        raise NotImplementedError(
            "Linear adapter is not implemented yet (planned after the Jira MVP)"
        )
