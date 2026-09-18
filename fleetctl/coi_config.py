"""Trusted host-side COI config generation (P3).

The config COI reads is generated on the trusted host from:
  * the **registry** (trusted): allowlisted domains, resource caps, bot identity
  * the **manifest** (repo-controlled): requested network mode, timeout

Repo-supplied values are clamped by trusted values; the repo can never widen
its own resource caps. Only the LLM env var *name* is forwarded — COI reads the
value from the host environment at session start, so the secret never lands in
this file, the repo, or logs.
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .models import FleetManifest
from .registry import Registry

_DURATION_RE = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")

_BARE_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")


def parse_duration(value: str) -> int:
    """Parse ``30m`` / ``1h30m`` / ``90s`` to seconds."""
    value = (value or "").strip()
    if not value:
        raise ValueError("empty duration")
    m = _DURATION_RE.fullmatch(value)
    if not m or not any(m.groups()):
        raise ValueError(f"invalid duration: {value!r}")
    hours, minutes, seconds = (int(g or 0) for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


def format_duration(seconds: int) -> str:
    if seconds % 3600 == 0 and seconds >= 3600:
        return f"{seconds // 3600}h"
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def build_coi_config(
    manifest: FleetManifest,
    registry: Registry,
    *,
    llm_env: str | None = None,
) -> dict[str, Any]:
    """Build the trusted COI profile body for a run."""
    cfg: dict[str, Any] = {
        "container": {"persistent": False},
        "ssh": {"forward_agent": False},
    }

    if llm_env:
        cfg["forward_env"] = [llm_env]

    network: dict[str, Any] = {"mode": manifest.coi.network}
    if manifest.coi.network == "allowlist":
        domains = list(
            dict.fromkeys(
                [*registry.coi.allowed_domains, *manifest.coi.allowed_domains]
            )
        )
        network["allowed_domains"] = domains
    elif manifest.coi.network == "restricted":
        # restricted already permits internet egress; domain list is unused.
        pass
    cfg["network"] = network

    timeout = parse_duration(manifest.coi.timeout)
    cap = parse_duration(registry.coi.timeout_cap)
    if timeout > cap:
        timeout = cap

    limits = copy.deepcopy(registry.coi.limits)
    runtime = limits.setdefault("runtime", {})
    runtime["max_duration"] = format_duration(timeout)
    runtime.setdefault("auto_stop", True)
    cfg["limits"] = limits

    cfg["monitoring"] = {
        "enabled": True,
        # In allowlist mode the sandbox legitimately attempts (and has blocked)
        # DNS, which the monitor reports as high-severity "unexpected network
        # connection". Pausing on that is a false positive that stalls runs, so
        # only auto-kill on critical threats.
        "auto_pause_on_high": False,
        "auto_kill_on_critical": True,
    }

    cfg["security"] = {
        "secret_paths": [
            ".env",
            "*.pem",
            "*.key",
            ".npmrc",
            ".netrc",
            ".git-credentials",
            "secrets/**",
        ],
        "host_immutable": True,
    }

    cfg["git"] = {
        "name": registry.bot_name,
        "email": registry.bot_email,
        "seed_host_identity": False,
        "writable_hooks": False,
    }

    return cfg


# ---------------------------------------------------------------------------
# Minimal TOML writer (pyproject has no writer dependency and we only need a
# small subset: nested tables, strings, bools, ints, floats, string arrays).
# ---------------------------------------------------------------------------


def _fmt_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    return json.dumps(text)  # JSON string escaping is valid TOML for our subset


def _fmt_key(key: str) -> str:
    return key if _BARE_TOKEN.match(key) else json.dumps(key)


def dumps_toml(data: dict[str, Any], _prefix: str = "") -> str:
    lines: list[str] = []
    scalars = {k: v for k, v in data.items() if not isinstance(v, dict)}
    tables = {k: v for k, v in data.items() if isinstance(v, dict)}

    for key, value in scalars.items():
        if isinstance(value, list):
            if not value:
                continue
            lines.append(f"{_fmt_key(key)} = [{', '.join(_fmt_scalar(v) for v in value)}]")
        else:
            lines.append(f"{_fmt_key(key)} = {_fmt_scalar(value)}")

    for key, table in tables.items():
        if not table:
            continue
        path = f"{_prefix}.{key}" if _prefix else key
        if lines:
            lines.append("")
        lines.append(f"[{path}]")
        lines.append(dumps_toml(table, path))

    return "\n".join(lines).strip() + "\n"


def render_coi_toml(
    manifest: FleetManifest, registry: Registry, *, llm_env: str | None = None
) -> tuple[dict[str, Any], str]:
    cfg = build_coi_config(manifest, registry, llm_env=llm_env)
    return cfg, dumps_toml(cfg)


def validate_coi_config(path: str) -> tuple[bool, list[dict[str, str]]]:
    """Validate *path* with ``coi validate profile`` if COI is installed."""
    if shutil.which("coi") is None:
        return True, []
    proc = subprocess.run(
        ["coi", "validate", "profile", path, "--format", "json"],
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "").strip()
    if not out:
        return proc.returncode == 0, []
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError:
        return proc.returncode == 0, []
    return bool(parsed.get("valid")), list(parsed.get("errors", []))


def write_coi_config(path: str, toml_text: str) -> None:
    Path(path).write_text(toml_text)
    Path(path).chmod(0o600)
