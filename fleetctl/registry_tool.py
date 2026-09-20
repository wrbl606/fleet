"""Helper to configure the trusted fleet registry.

Edits a registry file — by default the git-ignored ``registry.local.yaml``
overlay that ``fleetctl`` merges over the generic ``registry.yaml`` — without
touching the tracked, reusable defaults.

Exposed through ``scripts/configure-registry.sh`` and usable directly:

    python3 -m fleetctl.registry_tool jira --project ENG --repo acme/engine
    python3 -m fleetctl.registry_tool trusted acme/engine
    python3 -m fleetctl.registry_tool github --comment-prefix /agent
    python3 -m fleetctl.registry_tool show
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Optional

from .registry import merge_registry

PLATFORMS = ("linux", "macos", "windows")
DEFAULT_FILE = os.environ.get("FLEET_REGISTRY_LOCAL_DEFAULT", "registry.local.yaml")


# --------------------------------------------------------------------------- #
# yaml io
# --------------------------------------------------------------------------- #
def _yaml():
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment guard
        raise SystemExit(
            "PyYAML is required; run: python3 -m pip install -r requirements.txt"
        ) from exc
    return yaml


def load_registry(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        return {}
    yaml = _yaml()
    data = yaml.safe_load(p.read_text()) or {}
    if not isinstance(data, dict):
        raise SystemExit(f"{path}: not a mapping")
    return data


def save_registry(path: str, data: dict[str, Any]) -> None:
    yaml = _yaml()
    text = yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)
    Path(path).write_text(text)


# --------------------------------------------------------------------------- #
# mutators (pure-ish: operate on the overlay dict)
# --------------------------------------------------------------------------- #
def add_jira(
    overlay: dict[str, Any],
    *,
    project: str,
    repo: str,
    components: Optional[dict[str, str]] = None,
    platform: Optional[str] = None,
    labels: Optional[list[str]] = None,
    base_branch: Optional[str] = None,
) -> dict[str, Any]:
    entries = _source_list(overlay, "jira")
    entry = _find(entries, "project", project)
    if entry is None:
        entry = {}
        entries.append(entry)
    entry["project"] = project
    entry["repo"] = repo
    if components:
        entry["components"] = dict(components)
    _opt(entry, "platform", platform)
    _opt(entry, "labels", labels)
    _opt(entry, "base_branch", base_branch)
    return entry


def add_linear(
    overlay: dict[str, Any],
    *,
    team: str,
    repo: str,
    platform: Optional[str] = None,
    labels: Optional[list[str]] = None,
    base_branch: Optional[str] = None,
) -> dict[str, Any]:
    entries = _source_list(overlay, "linear")
    entry = _find(entries, "team", team)
    if entry is None:
        entry = {}
        entries.append(entry)
    entry["team"] = team
    entry["repo"] = repo
    _opt(entry, "platform", platform)
    _opt(entry, "labels", labels)
    _opt(entry, "base_branch", base_branch)
    return entry


def configure_github(
    overlay: dict[str, Any],
    *,
    repo: Optional[str] = None,
    prefix: Optional[str] = None,
    author_associations: Optional[list[str]] = None,
    allow_users: Optional[list[str]] = None,
    bot_logins: Optional[list[str]] = None,
    fallback_repo_from_issue: bool = True,
) -> dict[str, Any]:
    sources = overlay.setdefault("sources", {})
    current = sources.get("github")
    entry: dict[str, Any] = {}
    if isinstance(current, dict):
        entry = dict(current)
    elif isinstance(current, list) and current and isinstance(current[0], dict):
        entry = dict(current[0])
    entry["fallback_repo_from_issue"] = fallback_repo_from_issue
    _opt(entry, "repo", repo)
    _opt(entry, "comment_prefix", prefix)
    _opt(entry, "comment_author_associations", author_associations)
    _opt(entry, "comment_allow_users", allow_users)
    _opt(entry, "comment_bot_logins", bot_logins)
    sources["github"] = [entry]
    return entry


def add_trusted(overlay: dict[str, Any], repos: list[str]) -> list[str]:
    return _union(overlay.setdefault("allowlist", {}), "trusted_repos", repos)


def add_native(
    overlay: dict[str, Any],
    *,
    repos: Optional[list[str]] = None,
    labels: Optional[list[str]] = None,
) -> dict[str, list[str]]:
    allow = overlay.setdefault("allowlist", {})
    return {
        "native_repos": _union(allow, "native_repos", repos or []),
        "native_labels": _union(allow, "native_labels", labels or []),
    }


def set_bot(
    overlay: dict[str, Any], *, name: Optional[str] = None, email: Optional[str] = None
) -> dict[str, Any]:
    bot = overlay.setdefault("bot", {})
    _opt(bot, "name", name)
    _opt(bot, "email", email)
    return bot


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _source_list(overlay: dict[str, Any], source: str) -> list[dict[str, Any]]:
    sources = overlay.setdefault("sources", {})
    entries = sources.setdefault(source, [])
    if not isinstance(entries, list):
        raise SystemExit(f"sources.{source} in the overlay must be a list")
    return entries


def _find(entries: list[dict[str, Any]], key: str, value: str) -> Optional[dict[str, Any]]:
    for entry in entries:
        if isinstance(entry, dict) and str(entry.get(key, "")).lower() == value.lower():
            return entry
    return None


def _opt(target: dict[str, Any], key: str, value: Any) -> None:
    if value is not None and value != []:
        target[key] = value


def _union(target: dict[str, Any], key: str, values: list[str]) -> list[str]:
    current = target.setdefault(key, [])
    for value in values:
        if value not in current:
            current.append(value)
    return current


def _pairs(items: Optional[list[str]]) -> Optional[dict[str, str]]:
    if not items:
        return None
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--component expects name=repo, got {item!r}")
        name, _, repo = item.partition("=")
        out[name.strip()] = repo.strip()
    return out


def _csv(value: Optional[str]) -> Optional[list[str]]:
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="configure-registry",
        description="Configure the trusted fleet registry overlay.",
    )
    parser.add_argument(
        "--file",
        default=DEFAULT_FILE,
        help=f"registry file to edit (default: {DEFAULT_FILE})",
    )
    parser.add_argument("--dry-run", action="store_true", help="print, do not write")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("jira", help="add/update a Jira project mapping")
    p.add_argument("--project", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--component", action="append", metavar="NAME=REPO")
    p.add_argument("--platform", choices=PLATFORMS)
    p.add_argument("--labels", help="comma-separated")
    p.add_argument("--base-branch")

    p = sub.add_parser("linear", help="add/update a Linear team mapping")
    p.add_argument("--team", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--platform", choices=PLATFORMS)
    p.add_argument("--labels", help="comma-separated")
    p.add_argument("--base-branch")

    p = sub.add_parser("github", help="configure the GitHub source / comment trigger")
    p.add_argument("--repo")
    p.add_argument("--comment-prefix")
    p.add_argument("--author-associations", help="comma-separated, e.g. OWNER,MEMBER")
    p.add_argument("--allow-users", help="comma-separated logins")
    p.add_argument("--bot-logins", help="comma-separated logins to ignore")

    p = sub.add_parser("trusted", help="add repos to allowlist.trusted_repos")
    p.add_argument("repos", nargs="+")

    p = sub.add_parser("native", help="add repos/labels to the native allowlist")
    p.add_argument("--repo", action="append", default=[])
    p.add_argument("--label", action="append", default=[])

    p = sub.add_parser("bot", help="set the bot identity")
    p.add_argument("--name")
    p.add_argument("--email")

    p = sub.add_parser("show", help="print the overlay")
    p.add_argument("--effective", action="store_true", help="merge over --base first")
    p.add_argument("--base", default="registry.yaml")

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    overlay = load_registry(args.file)

    if args.command == "jira":
        add_jira(
            overlay,
            project=args.project,
            repo=args.repo,
            components=_pairs(args.component),
            platform=args.platform,
            labels=_csv(args.labels),
            base_branch=args.base_branch,
        )
    elif args.command == "linear":
        add_linear(
            overlay,
            team=args.team,
            repo=args.repo,
            platform=args.platform,
            labels=_csv(args.labels),
            base_branch=args.base_branch,
        )
    elif args.command == "github":
        configure_github(
            overlay,
            repo=args.repo,
            prefix=args.comment_prefix,
            author_associations=_csv(args.author_associations),
            allow_users=_csv(args.allow_users),
            bot_logins=_csv(args.bot_logins),
        )
    elif args.command == "trusted":
        add_trusted(overlay, args.repos)
    elif args.command == "native":
        add_native(overlay, repos=args.repo, labels=args.label)
    elif args.command == "bot":
        set_bot(overlay, name=args.name, email=args.email)
    elif args.command == "show":
        data = overlay
        if args.effective:
            data = merge_registry(load_registry(args.base), overlay)
        print(
            _yaml()
            .safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)
            .rstrip()
        )
        return 0

    if args.dry_run:
        print(_yaml().safe_dump(
            overlay, sort_keys=False, default_flow_style=False, allow_unicode=True
        ).rstrip())
        return 0

    save_registry(args.file, overlay)
    print(f"updated {args.file}")
    print(
        "validate with: python3 -m fleetctl validate "
        "--registry registry.yaml --repo-dir <repo> --coi"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
