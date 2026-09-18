"""Build a :class:`RunPlan` from a normalized issue + registry + repo checkout."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .agents import build_agent_command
from .coi_config import build_coi_config, dumps_toml
from .errors import ValidationError
from .models import FleetManifest, Issue, RunPlan
from .registry import Registry
from .render import build_context, render


def load_manifest(repo_dir: str) -> FleetManifest:
    return FleetManifest.from_file(str(Path(repo_dir) / ".fleet" / "fleet.toml"))


def build_prompt(manifest: FleetManifest, context: dict, repo_dir: str) -> str:
    if manifest.agent.inline:
        template = manifest.agent.inline
    else:
        path = Path(repo_dir) / ".fleet" / str(manifest.agent.prompt_file)
        if not path.is_file():
            raise ValidationError(f"prompt_file not found: {manifest.agent.prompt_file}")
        template = path.read_text()
    return render(template, context)


def build_plan(
    issue: Issue,
    registry: Registry,
    repo_dir: str,
    *,
    llm_env: Optional[str] = None,
) -> RunPlan:
    manifest = load_manifest(repo_dir)
    resolution = registry.resolve(issue)

    # Untrusted repos get the hardened COI profile unless they pinned one.
    if not manifest.coi.profile and resolution.repo not in registry.trusted_repos:
        if registry.coi.untrusted_profile:
            manifest.coi.profile = registry.coi.untrusted_profile

    mode = _resolve_mode(issue, manifest)
    head_branch = issue.pr_head_branch if issue.is_pr_comment else None
    base_branch = (
        issue.pr_base_branch if issue.is_pr_comment else None
    ) or resolution.base_branch
    pr_url = _pr_url(issue, resolution.repo)

    context = build_context(
        issue,
        repo=resolution.repo,
        platform=resolution.platform,
        mode=mode,
        head_branch=head_branch or "",
        base_branch=base_branch or "",
        pr_number=issue.pr_number,
        pr_url=pr_url or "",
    )
    pr_title = render(manifest.pr.title, context)
    context["pr"]["title"] = pr_title

    prompt = build_prompt(manifest, context, repo_dir)
    agent_command = build_agent_command(manifest, prompt)

    env_name = llm_env or manifest.agent.llm_env
    coi_config = build_coi_config(manifest, registry, llm_env=env_name)

    return RunPlan(
        issue=issue,
        resolution=resolution,
        manifest=manifest,
        prompt=prompt,
        pr_title=pr_title,
        agent_command=agent_command,
        coi_config=coi_config,
        coi_config_toml=dumps_toml(coi_config),
        repo=resolution.repo,
        mode=mode,
        head_branch=head_branch,
        pr_number=issue.pr_number,
        pr_url=pr_url,
        comment_id=issue.comment_id,
    )


def _resolve_mode(issue: Issue, manifest: FleetManifest) -> str:
    if not issue.is_pr_comment:
        return "new_pr"
    # A repo cannot force a push it isn't allowed to make; forks are reply-only.
    if not manifest.comment.enabled or issue.is_fork:
        return "answer"
    # Without the PR head ref (enrichment unavailable) we can only reply.
    if not issue.pr_head_branch:
        return "answer"
    return {
        "auto": "auto",
        "code": "update_pr",
        "answer": "answer",
    }.get(manifest.comment.mode, "auto")


def _pr_url(issue: Issue, repo: str) -> Optional[str]:
    if not issue.is_pr_comment or not issue.pr_number:
        return None
    if issue.comment_url and "/pull/" in issue.comment_url:
        return issue.comment_url.split("#", 1)[0]
    return f"https://github.com/{repo}/pull/{issue.pr_number}"


def render_comment_reply(plan: RunPlan, repo_dir: str, changed_files: list[str]) -> str:
    """Human-facing PR reply: the agent's ``reply_file`` if present, else a summary."""
    reply_file = plan.manifest.comment.reply_file
    if reply_file:
        path = Path(repo_dir) / ".fleet" / reply_file
        if path.is_file():
            text = path.read_text().strip()
            if text:
                return text + "\n"

    lines = ["**fleet agent** processed this comment."]
    if changed_files:
        branch = plan.head_branch or plan.branch()
        lines.append("")
        lines.append(f"Pushed changes to `{branch}`:")
        lines += [f"- `{f}`" for f in changed_files]
    else:
        lines.append("")
        lines.append("No file changes were required.")
    if plan.manifest.agent.tool:
        lines.append("")
        lines.append(f"_Agent: `{plan.manifest.agent.tool}`._")
    return "\n".join(lines).strip() + "\n"


def render_pr_body(plan: RunPlan, repo_dir: str, summary: str = "") -> str:
    """Render the PR body template (or a sensible default)."""
    body_file = plan.manifest.pr.body_file
    context = build_context(
        plan.issue, repo=plan.repo, platform=plan.resolution.platform,
        pr_title=plan.pr_title,
    )
    context["pr"]["summary"] = summary
    if body_file:
        path = Path(repo_dir) / ".fleet" / body_file
        if not path.is_file():
            raise ValidationError(f"pr.body_file not found: {body_file}")
        return render(path.read_text(), context, strict=False)
    lines = [
        f"Automated change for **{plan.issue.key}**: {plan.issue.summary}",
        "",
        f"- Source: {plan.issue.source}",
    ]
    if plan.issue.url:
        lines.append(f"- Issue: {plan.issue.url}")
    lines += [
        f"- Agent: `{plan.manifest.agent.tool}`",
        f"- Verify iterations: see run log",
        "",
        summary,
    ]
    return "\n".join(lines).strip() + "\n"
