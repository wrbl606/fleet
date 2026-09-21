"""Typed models for the fleet dispatcher.

These are the in-memory representations of:
  * a normalized :class:`Issue` (canonical PM-tool event),
  * a parsed :class:`FleetManifest` (``.fleet/fleet.toml``),
  * a loaded :class:`Registry` (``registry.yaml``),
  * a :class:`Resolution` (registry lookup result),
  * a fully materialized :class:`RunPlan` (everything a worker needs).

They all round-trip through ``to_dict()`` / ``from_dict()`` so a plan can be
computed on the Jenkins controller and replayed on a worker node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .errors import ValidationError

PLATFORM_OS = ("linux", "macos", "windows")
NETWORK_MODES = ("restricted", "allowlist", "open")
KNOWN_TOOLS = ("claude", "codex", "opencode", "pi", "custom")


def _require(data: dict, path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise ValidationError(f"missing required field '{path}'")
        cur = cur[part]
    return cur


def _as_str_list(value: Any, path: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValidationError(f"'{path}' must be a list of strings")
    return list(value)


@dataclass
class Issue:
    """Canonical issue produced by a PM-tool normalizer."""

    source: str
    key: str
    summary: str
    description: str = ""
    issue_type: str = ""
    labels: list[str] = field(default_factory=list)
    project: str = ""
    component: Optional[str] = None
    team: Optional[str] = None
    reporter: Optional[str] = None
    url: str = ""
    repo_hint: Optional[str] = None
    #: Default branch of the repo as reported by the source (GitHub webhook
    #: ``repository.default_branch``); used as the clone/PR-base fallback.
    default_branch: Optional[str] = None
    event: str = ""

    #: "issue" for a PM task, "pr_comment" for a PR-comment trigger.
    kind: str = "issue"
    pr_number: Optional[int] = None
    pr_head_branch: Optional[str] = None
    pr_base_branch: Optional[str] = None
    #: ``owner/name`` of the head repo, which differs from the base repo on forks.
    pr_head_repo: Optional[str] = None
    pr_state: Optional[str] = None
    comment_id: Optional[int] = None
    comment_url: Optional[str] = None
    comment_body: Optional[str] = None
    #: The instruction parsed from the comment (text after the prefix).
    command: Optional[str] = None
    author: Optional[str] = None
    author_association: Optional[str] = None

    @property
    def is_pr_comment(self) -> bool:
        return self.kind == "pr_comment"

    @property
    def is_fork(self) -> bool:
        if not self.pr_head_repo or not self.repo_hint:
            return False
        return self.pr_head_repo.lower() != self.repo_hint.lower()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "key": self.key,
            "summary": self.summary,
            "description": self.description,
            "type": self.issue_type,
            "labels": list(self.labels),
            "project": self.project,
            "component": self.component,
            "team": self.team,
            "reporter": self.reporter,
            "url": self.url,
            "repo_hint": self.repo_hint,
            "default_branch": self.default_branch,
            "event": self.event,
            "kind": self.kind,
            "pr_number": self.pr_number,
            "pr_head_branch": self.pr_head_branch,
            "pr_base_branch": self.pr_base_branch,
            "pr_head_repo": self.pr_head_repo,
            "pr_state": self.pr_state,
            "comment_id": self.comment_id,
            "comment_url": self.comment_url,
            "comment_body": self.comment_body,
            "command": self.command,
            "author": self.author,
            "author_association": self.author_association,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Issue":
        return cls(
            source=data["source"],
            key=data["key"],
            summary=data.get("summary", ""),
            description=data.get("description", ""),
            issue_type=data.get("type", ""),
            labels=list(data.get("labels", [])),
            project=data.get("project", ""),
            component=data.get("component"),
            team=data.get("team"),
            reporter=data.get("reporter"),
            url=data.get("url", ""),
            repo_hint=data.get("repo_hint"),
            default_branch=data.get("default_branch"),
            event=data.get("event", ""),
            kind=data.get("kind", "issue"),
            pr_number=data.get("pr_number"),
            pr_head_branch=data.get("pr_head_branch"),
            pr_base_branch=data.get("pr_base_branch"),
            pr_head_repo=data.get("pr_head_repo"),
            pr_state=data.get("pr_state"),
            comment_id=data.get("comment_id"),
            comment_url=data.get("comment_url"),
            comment_body=data.get("comment_body"),
            command=data.get("command"),
            author=data.get("author"),
            author_association=data.get("author_association"),
        )


@dataclass
class AgentSpec:
    tool: str = "claude"
    prompt_file: Optional[str] = None
    inline: Optional[str] = None
    command: Optional[list[str]] = None
    max_iterations: int = 3
    llm_env: Optional[str] = None
    llm_credential_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "prompt_file": self.prompt_file,
            "inline": self.inline,
            "command": list(self.command) if self.command else None,
            "max_iterations": self.max_iterations,
            "llm_env": self.llm_env,
            "llm_credential_id": self.llm_credential_id,
        }


@dataclass
class SetupSpec:
    script: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"script": self.script}


@dataclass
class VerifySpec:
    script: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {"script": self.script}


@dataclass
class PrSpec:
    branch_prefix: str = "fleet/"
    base: str = "main"
    title: str = "{{issue.key}}: {{issue.summary}}"
    labels: list[str] = field(default_factory=list)
    body_file: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_prefix": self.branch_prefix,
            "base": self.base,
            "title": self.title,
            "labels": list(self.labels),
            "body_file": self.body_file,
        }


@dataclass
class CommentSpec:
    """PR-comment trigger behavior (repo-controlled; policy lives in registry)."""

    enabled: bool = True
    #: auto | code | answer
    mode: str = "auto"
    reply: bool = True
    reply_file: str = "reply.md"

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "reply": self.reply,
            "reply_file": self.reply_file,
        }


@dataclass
class PlatformSpec:
    os: str = "linux"
    requires: list[str] = field(default_factory=list)
    arch: str = "amd64"

    def to_dict(self) -> dict[str, Any]:
        return {"os": self.os, "requires": list(self.requires), "arch": self.arch}


@dataclass
class CoiSpec:
    profile: str = ""
    network: str = "restricted"
    timeout: str = "30m"
    allowed_domains: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "network": self.network,
            "timeout": self.timeout,
            "allowed_domains": list(self.allowed_domains),
        }


@dataclass
class FleetManifest:
    """Parsed ``.fleet/fleet.toml``."""

    version: int = 1
    agent: AgentSpec = field(default_factory=AgentSpec)
    setup: SetupSpec = field(default_factory=SetupSpec)
    verify: VerifySpec = field(default_factory=VerifySpec)
    pr: PrSpec = field(default_factory=PrSpec)
    platform: PlatformSpec = field(default_factory=PlatformSpec)
    coi: CoiSpec = field(default_factory=CoiSpec)
    comment: CommentSpec = field(default_factory=CommentSpec)

    # -- validation ---------------------------------------------------------
    def validate(self) -> None:
        if self.version != 1:
            raise ValidationError(f"unsupported fleet.toml version: {self.version}")
        if self.agent.tool not in KNOWN_TOOLS:
            raise ValidationError(
                f"[agent].tool must be one of {', '.join(KNOWN_TOOLS)}; got {self.agent.tool!r}"
            )
        if bool(self.agent.prompt_file) == bool(self.agent.inline):
            raise ValidationError(
                "[agent] must set exactly one of prompt_file or inline"
            )
        if self.agent.tool == "custom" and not self.agent.command:
            raise ValidationError("[agent].command is required when tool = 'custom'")
        if not isinstance(self.agent.max_iterations, int) or self.agent.max_iterations < 1:
            raise ValidationError("[agent].max_iterations must be an integer >= 1")
        if self.agent.llm_env is not None and not _is_env_name(self.agent.llm_env):
            raise ValidationError("[agent].llm_env must be an environment variable NAME")
        if self.platform.os not in PLATFORM_OS:
            raise ValidationError(
                f"[platform].os must be one of {', '.join(PLATFORM_OS)}"
            )
        if self.coi.network not in NETWORK_MODES:
            raise ValidationError(
                f"[coi].network must be one of {', '.join(NETWORK_MODES)}"
            )
        for name, rel in (
            ("setup.script", self.setup.script),
            ("verify.script", self.verify.script),
            ("agent.prompt_file", self.agent.prompt_file),
            ("pr.body_file", self.pr.body_file),
        ):
            if rel is not None and not _is_safe_relpath(rel):
                raise ValidationError(f"[{name}] must be a repo-relative path: {rel!r}")
        if not self.pr.branch_prefix:
            raise ValidationError("[pr].branch_prefix must not be empty")
        if self.comment.mode not in ("auto", "code", "answer"):
            raise ValidationError(
                f"[comment].mode must be one of auto, code, answer; got {self.comment.mode!r}"
            )
        if not _is_safe_relpath(self.comment.reply_file):
            raise ValidationError(
                f"[comment].reply_file must be a repo-relative path: {self.comment.reply_file!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "agent": self.agent.to_dict(),
            "setup": self.setup.to_dict(),
            "verify": self.verify.to_dict(),
            "pr": self.pr.to_dict(),
            "platform": self.platform.to_dict(),
            "coi": self.coi.to_dict(),
            "comment": self.comment.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FleetManifest":
        agent = data.get("agent", {})
        setup = data.get("setup", {}) or {}
        verify = data.get("verify", {}) or {}
        pr = data.get("pr", {}) or {}
        platform = data.get("platform", {}) or {}
        coi = data.get("coi", {}) or {}
        comment = data.get("comment", {}) or {}
        manifest = cls(
            version=int(data.get("version", 1)),
            agent=AgentSpec(
                tool=agent.get("tool", "claude"),
                prompt_file=agent.get("prompt_file"),
                inline=agent.get("inline"),
                command=list(agent["command"]) if agent.get("command") else None,
                max_iterations=int(agent.get("max_iterations", 3)),
                llm_env=agent.get("llm_env"),
                llm_credential_id=agent.get("llm_credential_id"),
            ),
            setup=SetupSpec(script=setup.get("script")),
            verify=VerifySpec(script=verify.get("script")),
            pr=PrSpec(
                branch_prefix=pr.get("branch_prefix", "fleet/"),
                base=pr.get("base", "main"),
                title=pr.get("title", "{{issue.key}}: {{issue.summary}}"),
                labels=list(pr.get("labels", [])),
                body_file=pr.get("body_file"),
            ),
            platform=PlatformSpec(
                os=platform.get("os", "linux"),
                requires=list(platform.get("requires", [])),
                arch=platform.get("arch", "amd64"),
            ),
            coi=CoiSpec(
                profile=coi.get("profile", ""),
                network=coi.get("network", "restricted"),
                timeout=coi.get("timeout", "30m"),
                allowed_domains=list(coi.get("allowed_domains", [])),
            ),
            comment=CommentSpec(
                enabled=bool(comment.get("enabled", True)),
                mode=comment.get("mode", "auto"),
                reply=bool(comment.get("reply", True)),
                reply_file=comment.get("reply_file", "reply.md"),
            ),
        )
        manifest.validate()
        return manifest

    @classmethod
    def from_file(cls, path: str) -> "FleetManifest":
        import tomllib
        from pathlib import Path

        p = Path(path)
        if not p.is_file():
            raise ValidationError(f"fleet.toml not found: {path}")
        try:
            with p.open("rb") as fh:
                data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise ValidationError(f"invalid TOML in {path}: {exc}") from exc
        return cls.from_dict(data)


@dataclass
class Resolution:
    """Result of a registry lookup for an issue."""

    repo: str
    platform: str = "linux"
    requires: list[str] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    base_branch: str = "main"
    native: bool = False
    native_options: dict[str, Any] = field(default_factory=dict)

    @property
    def jenkins_label(self) -> str:
        if self.platform == "macos":
            base = "fleet-agent-macos"
        elif self.platform == "windows":
            base = "fleet-agent-windows"
        else:
            base = "fleet-agent"
        parts = [base, *self.requires]
        return " && ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "repo": self.repo,
            "platform": self.platform,
            "requires": list(self.requires),
            "labels": list(self.labels),
            "base_branch": self.base_branch,
            "native": self.native,
            "native_options": dict(self.native_options),
        }
        d["jenkins_label"] = self.jenkins_label
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Resolution":
        return cls(
            repo=data["repo"],
            platform=data.get("platform", "linux"),
            requires=list(data.get("requires", [])),
            labels=list(data.get("labels", [])),
            base_branch=data.get("base_branch", "main"),
            native=bool(data.get("native", False)),
            native_options=dict(data.get("native_options", {})),
        )


@dataclass
class RunPlan:
    """Everything a worker needs to execute one task."""

    issue: Issue
    resolution: Resolution
    manifest: FleetManifest
    prompt: str
    pr_title: str
    agent_command: list[str]
    coi_config: dict[str, Any]
    coi_config_toml: str
    repo: str = ""
    #: new_pr | auto | update_pr | answer
    mode: str = "new_pr"
    head_branch: Optional[str] = None
    pr_number: Optional[int] = None
    pr_url: Optional[str] = None
    comment_id: Optional[int] = None

    @property
    def update_existing_branch(self) -> bool:
        return self.mode in ("auto", "update_pr")

    def branch(self) -> str:
        """Branch the run targets: the PR head for comment triggers."""
        if self.update_existing_branch and self.head_branch:
            return self.head_branch
        from .publisher import branch_name

        return branch_name(self)

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue": self.issue.to_dict(),
            "resolution": self.resolution.to_dict(),
            "manifest": self.manifest.to_dict(),
            "prompt": self.prompt,
            "pr_title": self.pr_title,
            "agent_command": list(self.agent_command),
            "coi_config": self.coi_config,
            "coi_config_toml": self.coi_config_toml,
            "repo": self.repo or self.resolution.repo,
            "mode": self.mode,
            "head_branch": self.head_branch,
            "pr_number": self.pr_number,
            "pr_url": self.pr_url,
            "comment_id": self.comment_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunPlan":
        return cls(
            issue=Issue.from_dict(data["issue"]),
            resolution=Resolution.from_dict(data["resolution"]),
            manifest=FleetManifest.from_dict(data["manifest"]),
            prompt=data.get("prompt", ""),
            pr_title=data.get("pr_title", ""),
            agent_command=list(data.get("agent_command", [])),
            coi_config=data.get("coi_config", {}),
            coi_config_toml=data.get("coi_config_toml", ""),
            repo=data.get("repo", ""),
            mode=data.get("mode", "new_pr"),
            head_branch=data.get("head_branch"),
            pr_number=data.get("pr_number"),
            pr_url=data.get("pr_url"),
            comment_id=data.get("comment_id"),
        )


@dataclass
class StepResult:
    name: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "duration_s": round(self.duration_s, 3),
        }


@dataclass
class IterationRecord:
    n: int
    prompt: str
    agent: StepResult
    verify: Optional[StepResult] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "prompt": self.prompt,
            "agent": self.agent.to_dict(),
            "verify": self.verify.to_dict() if self.verify else None,
        }


@dataclass
class RunResult:
    status: str  # succeeded | verify_failed | failed | no_changes
    repo: str
    branch: str
    pr_url: Optional[str] = None
    reply_url: Optional[str] = None
    iterations: list[IterationRecord] = field(default_factory=list)
    error: Optional[str] = None
    error_code: Optional[str] = None
    #: Jenkins build that produced this run (from BUILD_URL / BUILD_NUMBER).
    build_url: Optional[str] = None
    build_number: Optional[int] = None
    artifacts: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in ("succeeded", "no_changes")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "repo": self.repo,
            "branch": self.branch,
            "pr_url": self.pr_url,
            "reply_url": self.reply_url,
            "iterations": [i.to_dict() for i in self.iterations],
            "error": self.error,
            "error_code": self.error_code,
            "build_url": self.build_url,
            "build_number": self.build_number,
            "artifacts": self.artifacts,
        }


def _is_env_name(value: str) -> bool:
    import re

    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value))


def _is_safe_relpath(value: str) -> bool:
    from pathlib import PurePosixPath

    if not value or value.startswith("/") or "\\" in value:
        return False
    parts = PurePosixPath(value).parts
    return not any(p == ".." for p in parts)
