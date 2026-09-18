"""Exception hierarchy for fleetctl.

Every failure that should abort a run in a well-understood way derives from
:class:`FleetError`. The dispatcher maps these to a structured run result so
the Jenkins job can fail closed with an actionable message.
"""

from __future__ import annotations


class FleetError(Exception):
    """Base class for all expected fleetctl failures."""

    #: Stable machine-readable code emitted in run results / CLI errors.
    code = "fleet_error"


class ValidationError(FleetError):
    """A contract (fleet.toml / registry.yaml / payload) is malformed."""

    code = "validation_error"


class ResolutionError(FleetError):
    """No repo could be resolved for a normalized issue."""

    code = "resolution_error"


class RenderError(FleetError):
    """A prompt/PR template referenced an unknown variable."""

    code = "render_error"


class AllowlistError(FleetError):
    """Native (non-COI) execution was requested for a non-allowlisted repo."""

    code = "allowlist_error"


class RunnerError(FleetError):
    """A sandbox/host command failed to execute."""

    code = "runner_error"


class PublishError(FleetError):
    """The trusted git/gh publish step failed."""

    code = "publish_error"


class ToolError(FleetError):
    """The declared agent tool is unknown / misconfigured."""

    code = "tool_error"
