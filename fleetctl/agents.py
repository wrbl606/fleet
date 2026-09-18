"""Agent CLI invocation map (P3).

CLI non-interactive flags drift between tool versions. Known tools use the
mapping below; a repo can pin exact argv via ``[agent].command`` (with a
``{{prompt}}`` placeholder) when a tool's flags change or for an unsupported
tool (``tool = "custom"``).
"""

from __future__ import annotations

from .errors import ToolError
from .models import FleetManifest

#: tool name -> callable(prompt) -> argv
TOOL_COMMANDS = {
    "claude": lambda prompt: [
        "claude",
        "-p",
        prompt,
        "--dangerously-skip-permissions",
    ],
    "codex": lambda prompt: ["codex", "exec", "--full-auto", prompt],
    "opencode": lambda prompt: ["opencode", "run", prompt],
    "pi": lambda prompt: ["pi", "run", prompt],
}


def build_agent_command(manifest: FleetManifest, prompt: str) -> list[str]:
    """Return the argv used to run the agent inside the sandbox."""
    explicit = manifest.agent.command
    if explicit:
        if not any("{{prompt}}" in arg for arg in explicit):
            raise ToolError(
                "[agent].command must contain a '{{prompt}}' placeholder "
                "so the rendered task prompt is passed to the agent"
            )
        return [arg.replace("{{prompt}}", prompt) for arg in explicit]

    builder = TOOL_COMMANDS.get(manifest.agent.tool)
    if builder is None:
        raise ToolError(
            f"unsupported tool {manifest.agent.tool!r}; set [agent].command "
            f"for a custom invocation (known: {', '.join(sorted(TOOL_COMMANDS))})"
        )
    return builder(prompt)
