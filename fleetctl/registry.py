"""Central registry parsing + repo resolution (``registry.yaml``).

The registry is the trusted, versioned source of truth for *where* a PM event
goes and *how* it is allowed to run. It is the fail-closed gate for native
(non-COI) execution: a repo may only run outside the Linux/COI sandbox if it
is explicitly allowlisted here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .errors import AllowlistError, ResolutionError, ValidationError
from .models import Issue, PLATFORM_OS, Resolution

#: Optional, git-ignored overlay merged over the generic ``registry.yaml`` so a
#: deployment can add real org/repo/project mappings without editing tracked
#: files. Auto-discovered next to the base registry, or via FLEET_REGISTRY_LOCAL.
LOCAL_REGISTRY_NAME = "registry.local.yaml"


def _load_yaml(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise ValidationError(f"registry not found: {path}")
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment guard
        raise ValidationError("PyYAML is required to parse registry.yaml") from exc
    try:
        data = yaml.safe_load(p.read_text())
    except yaml.YAMLError as exc:
        raise ValidationError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("registry.yaml must be a mapping")
    return data


def discover_local_registry(path: str) -> Optional[str]:
    """Return the local overlay path for ``path``, if one exists."""
    env = os.environ.get("FLEET_REGISTRY_LOCAL")
    if env:
        return env
    sibling = Path(path).resolve().parent / LOCAL_REGISTRY_NAME
    return str(sibling) if sibling.is_file() else None


def merge_registry(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge ``overlay`` into ``base``.

    Mappings merge key-by-key; lists are unioned (base order preserved, new
    items appended); scalars are overridden by the overlay. This lets a local
    overlay append source entries, union allowlists/domains, and override
    defaults without restating the whole file.
    """
    if isinstance(base, dict) and isinstance(overlay, dict):
        merged = dict(base)
        for key, value in overlay.items():
            if key in merged:
                merged[key] = merge_registry(merged[key], value)
            else:
                merged[key] = value
        return merged
    if isinstance(base, list) and isinstance(overlay, list):
        merged = list(base)
        for item in overlay:
            if item not in merged:
                merged.append(item)
        return merged
    return overlay

DEFAULT_ALLOWED_DOMAINS = [
    "api.anthropic.com",
    "platform.claude.com",
    "api.openai.com",
    "chatgpt.com",
    "opencode.ai",
    "models.dev",
    "registry.npmjs.org",
    "npm.pkg.github.com",
    "pypi.org",
    "files.pythonhosted.org",
    "github.com",
    "api.github.com",
    "codeload.github.com",
    "objects.githubusercontent.com",
    "raw.githubusercontent.com",
]

DEFAULT_LIMITS: dict[str, Any] = {
    "cpu": {"count": "2"},
    "memory": {"limit": "4GiB", "enforce": "hard"},
    "disk": {"tmpfs_size": "2GiB"},
    "runtime": {"auto_stop": True, "stop_graceful": True},
}


@dataclass
class CoiDefaults:
    allowed_domains: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_DOMAINS))
    timeout_cap: str = "60m"
    limits: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_LIMITS))
    untrusted_profile: str = "hardened"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_domains": list(self.allowed_domains),
            "timeout_cap": self.timeout_cap,
            "limits": self.limits,
            "untrusted_profile": self.untrusted_profile,
        }


@dataclass
class Registry:
    github_org: str
    default_branch: str = "main"
    platform: str = "linux"
    labels: list[str] = field(default_factory=list)
    native_repos: list[str] = field(default_factory=list)
    native_labels: list[str] = field(default_factory=list)
    trusted_repos: list[str] = field(default_factory=list)
    #: Host-side, trusted OS sandbox for native (bare-metal) runs.
    native_macos_seatbelt_profile: Optional[str] = "resources/native/seatbelt.sb"
    native_windows_wrapper: list[str] = field(default_factory=list)
    jira: list[dict[str, Any]] = field(default_factory=list)
    linear: list[dict[str, Any]] = field(default_factory=list)
    github: dict[str, Any] = field(default_factory=dict)
    #: Trusted PR-comment trigger policy (never repo-controlled).
    github_comment_prefix: str = "/agent"
    github_comment_associations: list[str] = field(
        default_factory=lambda: ["OWNER", "MEMBER", "COLLABORATOR"]
    )
    github_comment_allow_users: list[str] = field(default_factory=list)
    github_comment_bot_logins: list[str] = field(default_factory=list)
    coi: CoiDefaults = field(default_factory=CoiDefaults)
    bot_name: str = "fleet-agent[bot]"
    bot_email: str = "fleet-agent@users.noreply.github.com"
    raw: dict[str, Any] = field(default_factory=dict)

    # -- loading ------------------------------------------------------------
    @classmethod
    def from_file(cls, path: str, local_path: Optional[str] = None) -> "Registry":
        data = _load_yaml(path)
        if local_path:
            data = merge_registry(data, _load_yaml(local_path))
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Registry":
        defaults = data.get("defaults") or {}
        if not isinstance(defaults, dict):
            raise ValidationError("registry.defaults must be a mapping")
        org = defaults.get("github_org")
        if not org:
            raise ValidationError("registry.defaults.github_org is required")

        allow = data.get("allowlist") or {}
        sources = data.get("sources") or {}
        if not isinstance(sources, dict):
            raise ValidationError("registry.sources must be a mapping")

        github_raw = sources.get("github", {})
        if isinstance(github_raw, list):
            merged: dict[str, Any] = {}
            for item in github_raw:
                if isinstance(item, dict):
                    merged.update(item)
            github_raw = merged
        if not isinstance(github_raw, dict):
            raise ValidationError("registry.sources.github must be a mapping or list")

        coi_raw = data.get("coi") or {}
        coi = CoiDefaults(
            allowed_domains=list(coi_raw.get("allowed_domains", DEFAULT_ALLOWED_DOMAINS)),
            timeout_cap=coi_raw.get("timeout_cap", "60m"),
            limits=coi_raw.get("limits", DEFAULT_LIMITS),
            untrusted_profile=coi_raw.get("untrusted_profile", "hardened"),
        )
        bot = data.get("bot") or {}
        native = data.get("native") or {}
        native_macos = native.get("macos") or {}
        native_windows = native.get("windows") or {}

        platform = defaults.get("platform", "linux")
        if platform not in PLATFORM_OS:
            raise ValidationError(
                f"registry.defaults.platform must be one of {', '.join(PLATFORM_OS)}"
            )

        return cls(
            github_org=org,
            default_branch=defaults.get("default_branch", "main"),
            platform=platform,
            labels=list(defaults.get("labels", [])),
            native_repos=list(allow.get("native_repos", [])),
            native_labels=list(allow.get("native_labels", [])),
            trusted_repos=list(allow.get("trusted_repos", [])),
            native_macos_seatbelt_profile=native_macos.get(
                "seatbelt_profile", "resources/native/seatbelt.sb"
            ),
            native_windows_wrapper=list(native_windows.get("wrapper", [])),
            jira=list(sources.get("jira", [])),
            linear=list(sources.get("linear", [])),
            github=dict(github_raw),
            github_comment_prefix=github_raw.get("comment_prefix", "/agent"),
            github_comment_associations=[
                str(x).upper()
                for x in github_raw.get(
                    "comment_author_associations",
                    ["OWNER", "MEMBER", "COLLABORATOR"],
                )
            ],
            github_comment_allow_users=[
                str(x) for x in github_raw.get("comment_allow_users", [])
            ],
            github_comment_bot_logins=[
                str(x) for x in github_raw.get("comment_bot_logins", [])
            ],
            coi=coi,
            bot_name=bot.get("name", "fleet-agent[bot]"),
            bot_email=bot.get("email", "fleet-agent@users.noreply.github.com"),
            raw=data,
        )

    # -- resolution ---------------------------------------------------------
    def resolve(self, issue: Issue) -> Resolution:
        """Map a normalized issue to a repo + platform, fail-closed."""
        entry = self._match_source(issue)
        if entry is None:
            raise ResolutionError(
                f"no registry source matches {issue.source} issue "
                f"{issue.key!r} (project={issue.project!r}, "
                f"component={issue.component!r}, team={issue.team!r})"
            )

        repo = self._repo_for(issue, entry)
        if not repo:
            raise ResolutionError(
                f"source entry for {issue.key!r} matched but produced no repo"
            )

        platform = entry.get("platform", self.platform)
        requires = list(entry.get("requires", []))
        labels = list(dict.fromkeys([*self.labels, *entry.get("labels", [])]))
        base_branch = entry.get("base_branch", self.default_branch)
        native = platform != "linux"

        native_options: dict[str, Any] = {}
        if platform == "macos":
            native_options["seatbelt_profile"] = self.native_macos_seatbelt_profile
        elif platform == "windows":
            native_options["windows_wrapper"] = list(self.native_windows_wrapper)

        resolution = Resolution(
            repo=repo,
            platform=platform,
            requires=requires,
            labels=labels,
            base_branch=base_branch,
            native=native,
            native_options=native_options,
        )
        if native:
            self._assert_native_allowed(resolution)
        return resolution

    def _match_source(self, issue: Issue) -> Optional[dict[str, Any]]:
        if issue.source == "jira":
            for entry in self.jira:
                if str(entry.get("project", "")).lower() == issue.project.lower() and issue.project:
                    return entry
            return None
        if issue.source == "linear":
            for entry in self.linear:
                if str(entry.get("team", "")).lower() == (issue.team or "").lower() and issue.team:
                    return entry
            return None
        if issue.source == "github":
            return {"github": True}
        return None

    def _repo_for(self, issue: Issue, entry: dict[str, Any]) -> Optional[str]:
        if issue.source == "jira":
            components = entry.get("components") or {}
            if issue.component and issue.component in components:
                return components[issue.component]
            # case-insensitive component match
            for name, repo in components.items():
                if name.lower() == (issue.component or "").lower():
                    return repo
            return entry.get("repo")
        if issue.source == "linear":
            return entry.get("repo")
        if issue.source == "github":
            if self.github.get("fallback_repo_from_issue") and issue.repo_hint:
                return issue.repo_hint
            return entry.get("repo")
        return None

    def _assert_native_allowed(self, resolution: Resolution) -> None:
        if resolution.repo in self.native_repos:
            return
        if set(resolution.labels) & set(self.native_labels):
            return
        raise AllowlistError(
            f"{resolution.repo} requested native ({resolution.platform}) execution "
            "but is not in allowlist.native_repos and carries none of "
            f"allowlist.native_labels {self.native_labels!r}; refusing to run unisolated"
        )
