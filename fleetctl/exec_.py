"""Command execution abstraction.

Everything that shells out goes through an :class:`Executor` so the dispatcher
can be unit-tested with a fake executor and so streaming/timeouts are handled
in one place.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Mapping, Optional, Sequence

from .models import StepResult


class Executor:
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> StepResult:  # pragma: no cover - interface
        raise NotImplementedError


class SubprocessExecutor(Executor):
    """Run argv locally, capturing stdout/stderr and the exit code."""

    def __init__(self, *, stream: bool = False) -> None:
        self.stream = stream

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> StepResult:
        name = " ".join(argv[:2]) if argv else ""
        merged = dict(os.environ)
        if env:
            merged.update({k: str(v) for k, v in env.items()})
        start = time.monotonic()
        try:
            proc = subprocess.run(
                list(argv),
                cwd=cwd,
                env=merged,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return StepResult(
                name=name,
                exit_code=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
                duration_s=time.monotonic() - start,
            )
        except subprocess.TimeoutExpired as exc:
            return StepResult(
                name=name,
                exit_code=124,
                stdout=_decode(exc.stdout),
                stderr=_decode(exc.stderr) + f"\n[timeout after {timeout}s]",
                duration_s=time.monotonic() - start,
            )
        except FileNotFoundError as exc:
            return StepResult(
                name=name,
                exit_code=127,
                stderr=f"command not found: {exc}",
                duration_s=time.monotonic() - start,
            )


def _decode(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def tail(text: str, limit: int = 4000) -> str:
    """Keep the last *limit* characters, useful for feeding errors back."""
    if len(text) <= limit:
        return text
    return "...\n" + text[-limit:]
