"""Shared test helpers."""

from __future__ import annotations

from typing import Mapping, Optional, Sequence

from fleetctl.exec_ import Executor
from fleetctl.models import StepResult


class FakeExecutor(Executor):
    """Executor whose responses are scripted, keyed by a substring of argv.

    ``responses`` maps a match string to either a single StepResult or a list of
    StepResults consumed in order (the last one repeats).
    """

    def __init__(self, responses: Optional[dict[str, object]] = None) -> None:
        self.responses = responses or {}
        self.calls: list[list[str]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Optional[str] = None,
        env: Optional[Mapping[str, str]] = None,
        timeout: Optional[float] = None,
    ) -> StepResult:
        argv = list(argv)
        self.calls.append(argv)
        joined = " ".join(argv)
        for match, value in self.responses.items():
            if match in joined:
                if isinstance(value, list):
                    result = value.pop(0) if len(value) > 1 else value[0]
                else:
                    result = value
                assert isinstance(result, StepResult)
                return result
        return StepResult(name=joined[:40], exit_code=0, stdout="(fake default)")
