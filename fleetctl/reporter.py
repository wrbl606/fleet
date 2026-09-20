"""Best-effort ingest/debug reporting to the admin panel.

Used by the dispatcher to record incoming webhooks and their normalization /
routing outcomes (`webhook.received`, `normalize.result`, `resolve.result`) so
the panel's Ingest log can explain what happened. A no-op when
``FLEET_INGEST_URL`` is unset, and never raises: debug reporting must not break
a run.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .notifier import _post

MAX_PAYLOAD = 100_000


def enabled() -> bool:
    return bool(os.environ.get("FLEET_INGEST_URL"))


def post_event(payload: dict[str, Any]) -> bool:
    url = os.environ.get("FLEET_INGEST_URL")
    if not url:
        return False
    headers: dict[str, str] = {}
    token = os.environ.get("FLEET_INGEST_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        return _post(url, payload, headers=headers)
    except Exception:  # noqa: BLE001 - debug reporting must never break a run
        return False


def payload_text(payload: Any) -> str:
    """Compact, size-bounded rendering of a raw webhook payload."""
    try:
        text = json.dumps(payload, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        text = str(payload)
    if len(text) > MAX_PAYLOAD:
        return text[:MAX_PAYLOAD] + "…(truncated)"
    return text
