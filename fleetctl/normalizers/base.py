"""PM-tool normalizers: raw webhook payload -> canonical :class:`Issue`."""

from __future__ import annotations

from typing import Any, Optional

from ..errors import ValidationError
from ..models import Issue


class Normalizer:
    """Base class for source adapters.

    A normalizer is pure: it receives a decoded payload plus optional event
    name/headers and returns a canonical :class:`Issue`, or ``None`` when the
    event is not one this source considers actionable.
    """

    source: str = ""

    def normalize(
        self,
        payload: dict[str, Any],
        *,
        event: Optional[str] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> Optional[Issue]:  # pragma: no cover - interface
        raise NotImplementedError


def _need(payload: dict[str, Any], path: str) -> Any:
    cur: Any = payload
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            raise ValidationError(f"webhook payload missing '{path}'")
    return cur
