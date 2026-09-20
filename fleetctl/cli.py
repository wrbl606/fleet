"""``fleetctl`` command line interface.

Subcommands:
  validate     validate registry + one or more .fleet contracts
  normalize    raw webhook payload -> canonical issue JSON
  resolve      issue JSON + registry -> repo resolution JSON
  plan         full RunPlan JSON (normalize + resolve + render + coi config)
  coi-config   emit/validate the trusted host-side COI config
  run          execute the bounded setup/agent/verify loop (on a worker)
  publish      trusted git commit/push + gh pr create
  env-check    verify required host tooling
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from . import __version__
from .coi_config import render_coi_toml, validate_coi_config, write_coi_config
from .dispatcher import execute
from .errors import FleetError, ValidationError
from .exec_ import SubprocessExecutor
from .github_api import enrich_issue_pr
from .models import FleetManifest, Issue, RunPlan
from .normalizers import get_normalizer
from .notifier import notify_issue, post_run_finished  # noqa: F401
from .planner import build_plan
from .publisher import publish
from .registry import Registry, discover_local_registry
from .reporter import payload_text, post_event

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _print_json(data: Any, out: Optional[str] = None) -> None:
    text = json.dumps(data, indent=2, sort_keys=False)
    if out:
        Path(out).write_text(text + "\n")
    else:
        print(text)


def _read_json(path: Optional[str]) -> Any:
    if path in (None, "-"):
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text())


def _load_issue(path: Optional[str]) -> Issue:
    data = _read_json(path)
    if isinstance(data, dict) and "issue" in data:
        data = data["issue"]
    return Issue.from_dict(data)


def _schemas_dir() -> Optional[Path]:
    env = os.environ.get("FLEET_SCHEMAS_DIR")
    if env:
        return Path(env)
    candidate = Path(__file__).resolve().parent.parent / "schemas"
    return candidate if candidate.is_dir() else None


def _validate_schema(kind: str, data: dict) -> list[str]:
    schemas = _schemas_dir()
    if schemas is None:
        return []
    schema_path = schemas / f"{kind}.schema.json"
    if not schema_path.is_file():
        return []
    try:
        import jsonschema
    except ImportError:
        return []
    schema = json.loads(schema_path.read_text())
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
        for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    ]


def _load_registry(path: str) -> Registry:
    registry = Registry.from_file(path, local_path=discover_local_registry(path))
    errors = _validate_schema("registry", registry.raw)
    if errors:
        raise ValidationError("registry schema errors: " + "; ".join(errors))
    return registry


def _load_contract(repo_dir: str) -> tuple[FleetManifest, dict]:
    import tomllib

    path = Path(repo_dir) / ".fleet" / "fleet.toml"
    if not path.is_file():
        raise ValidationError(f"no .fleet/fleet.toml under {repo_dir}")
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    manifest = FleetManifest.from_dict(raw)
    errors = _validate_schema("fleet", raw)
    if errors:
        raise ValidationError("fleet.toml schema errors: " + "; ".join(errors))
    return manifest, raw


def _bot(args: argparse.Namespace) -> tuple[str, str]:
    name = getattr(args, "bot_name", None)
    email = getattr(args, "bot_email", None)
    registry_path = getattr(args, "registry", None)
    if (not name or not email) and registry_path and Path(registry_path).is_file():
        reg = Registry.from_file(
            registry_path, local_path=discover_local_registry(registry_path)
        )
        name = name or reg.bot_name
        email = email or reg.bot_email
    return name or "fleet-agent[bot]", email or "fleet-agent@users.noreply.github.com"


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_validate(args: argparse.Namespace) -> int:
    report: dict[str, Any] = {"ok": True, "checks": []}

    if args.registry:
        try:
            reg = _load_registry(args.registry)
            report["checks"].append(
                {"name": "registry", "path": args.registry, "ok": True,
                 "sources": sorted(reg.raw.get("sources", {}).keys())}
            )
        except FleetError as exc:
            report["ok"] = False
            report["checks"].append(
                {"name": "registry", "path": args.registry, "ok": False,
                 "error": str(exc)}
            )

    for repo_dir in args.repo_dir:
        entry: dict[str, Any] = {"name": "fleet", "path": repo_dir, "ok": True}
        try:
            manifest, _ = _load_contract(repo_dir)
            entry["tool"] = manifest.agent.tool
            entry["platform"] = manifest.platform.os
        except FleetError as exc:
            entry["ok"] = False
            entry["error"] = str(exc)
            report["ok"] = False
        report["checks"].append(entry)

    if args.coi:
        try:
            manifest, _ = _load_contract(args.repo_dir[0])
            reg = _load_registry(args.registry)
            _, toml_text = render_coi_toml(
                manifest, reg, llm_env=manifest.agent.llm_env
            )
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "config.toml"
                write_coi_config(str(path), toml_text)
                ok, errors = validate_coi_config(str(path))
            report["checks"].append(
                {"name": "coi-config", "ok": ok, "errors": errors}
            )
            if not ok:
                report["ok"] = False
        except (FleetError, IndexError) as exc:
            report["ok"] = False
            report["checks"].append(
                {"name": "coi-config", "ok": False, "error": str(exc)}
            )

    _print_json(report, args.out)
    return EXIT_OK if report["ok"] else EXIT_ERROR


def cmd_normalize(args: argparse.Namespace) -> int:
    payload = _read_json(args.payload_file)
    if args.ingest:
        post_event(
            {
                "event": "webhook.received",
                "source": args.source,
                "webhook_event": args.event or "",
                "delivery": args.delivery or "",
                "payload": payload_text(payload),
            }
        )
    kwargs: dict[str, Any] = {}
    if args.registry:
        registry = _load_registry(args.registry)
        kwargs = {
            "comment_prefix": registry.github_comment_prefix,
            "comment_author_associations": registry.github_comment_associations,
            "comment_allow_users": registry.github_comment_allow_users,
            "comment_bot_logins": registry.github_comment_bot_logins,
        }
    normalizer = get_normalizer(
        args.source, trigger_label=args.trigger_label, **kwargs
    )
    try:
        issue = normalizer.normalize(payload, event=args.event, headers=args.headers or {})
    except FleetError as exc:
        _report_normalize(args, {"status": "error", "error": str(exc)})
        raise
    if issue is None:
        _report_normalize(
            args,
            {"actionable": False, "status": "filtered", "reason": "event filtered"},
        )
        _print_json({"actionable": False, "reason": "event filtered"}, args.out)
        return EXIT_OK
    if args.source == "github" and issue.is_pr_comment and args.enrich:
        # issue_comment carries no head/base refs; fetch them (best-effort).
        try:
            enrich_issue_pr(issue)
        except ValidationError:
            pass
    _report_normalize(
        args, {"actionable": True, "status": "ok", "issue": issue.to_dict()}
    )
    _print_json({"actionable": True, "issue": issue.to_dict()}, args.out)
    return EXIT_OK


def _report_normalize(args: argparse.Namespace, extra: dict[str, Any]) -> None:
    if not args.ingest:
        return
    post_event(
        {
            "event": "normalize.result",
            "source": args.source,
            "webhook_event": args.event or "",
            "delivery": args.delivery or "",
            **extra,
        }
    )


def cmd_resolve(args: argparse.Namespace) -> int:
    issue = _load_issue(args.issue_file)
    registry = _load_registry(args.registry)
    try:
        resolution = registry.resolve(issue)
    except FleetError as exc:
        if args.ingest:
            post_event(
                {
                    "event": "resolve.result",
                    "source": issue.source,
                    "status": "error",
                    "issue_key": issue.key,
                    "project": issue.project,
                    "error": str(exc),
                }
            )
        raise
    if args.ingest:
        post_event(
            {
                "event": "resolve.result",
                "source": issue.source,
                "issue_key": issue.key,
                "project": issue.project,
                **resolution.to_dict(),
            }
        )
    _print_json(resolution.to_dict(), args.out)
    return EXIT_OK


def cmd_plan(args: argparse.Namespace) -> int:
    registry = _load_registry(args.registry)
    if args.issue_file:
        issue = _load_issue(args.issue_file)
    else:
        kwargs = {
            "comment_prefix": registry.github_comment_prefix,
            "comment_author_associations": registry.github_comment_associations,
            "comment_allow_users": registry.github_comment_allow_users,
            "comment_bot_logins": registry.github_comment_bot_logins,
        }
        normalizer = get_normalizer(
            args.source, trigger_label=args.trigger_label, **kwargs
        )
        payload = _read_json(args.payload_file)
        issue = normalizer.normalize(payload, event=args.event)
        if issue is None:
            _print_json({"actionable": False}, args.out)
            return EXIT_OK

    if issue.is_pr_comment and not issue.pr_head_branch:
        try:
            enrich_issue_pr(issue)
        except ValidationError:
            pass

    plan = build_plan(issue, registry, args.repo_dir, llm_env=args.llm_env)
    if not args.skip_coi_validate:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            write_coi_config(str(path), plan.coi_config_toml)
            ok, errors = validate_coi_config(str(path))
        if not ok:
            raise ValidationError(f"generated COI config invalid: {errors}")
    _print_json(plan.to_dict(), args.out)
    return EXIT_OK


def cmd_coi_config(args: argparse.Namespace) -> int:
    registry = _load_registry(args.registry)
    if args.plan_file:
        plan = RunPlan.from_dict(_read_json(args.plan_file))
        toml_text = plan.coi_config_toml
    else:
        manifest, _ = _load_contract(args.repo_dir)
        _, toml_text = render_coi_toml(manifest, registry, llm_env=args.llm_env)
    if args.out:
        write_coi_config(args.out, toml_text)
    else:
        sys.stdout.write(toml_text)
    if args.validate:
        if not args.out:
            raise ValidationError("--validate requires --out")
        ok, errors = validate_coi_config(args.out)
        if not ok:
            raise ValidationError(f"COI config invalid: {errors}")
    return EXIT_OK


def cmd_run(args: argparse.Namespace) -> int:
    plan = RunPlan.from_dict(_read_json(args.plan_file))
    workspace = str(Path(args.workspace).resolve())
    if not (Path(workspace) / ".fleet").is_dir():
        raise ValidationError(f"workspace has no .fleet/: {workspace}")

    config_dir = Path(args.coi_config_dir or tempfile.mkdtemp(prefix="fleet-coi-"))
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.toml"
    write_coi_config(str(config_path), plan.coi_config_toml)

    bot_name, bot_email = _bot(args)
    executor = SubprocessExecutor()
    result = execute(
        plan,
        workspace,
        executor,
        coi_config_path=str(config_path),
        bot_name=bot_name,
        bot_email=bot_email,
        publish_enabled=not args.no_publish,
        dry_run=args.dry_run,
        notify=not args.no_notify,
    )
    _print_json(result.to_dict(), args.out)
    return EXIT_OK if result.ok or result.status == "verify_failed" else EXIT_ERROR


def cmd_publish(args: argparse.Namespace) -> int:
    plan = RunPlan.from_dict(_read_json(args.plan_file))
    workspace = str(Path(args.workspace).resolve())
    bot_name, bot_email = _bot(args)
    body = Path(args.body_file).read_text() if args.body_file else ""
    result = publish(
        plan,
        workspace,
        SubprocessExecutor(),
        bot_name=bot_name,
        bot_email=bot_email,
        body=body,
        dry_run=args.dry_run,
    )
    _print_json(result.to_dict(), args.out)
    return EXIT_OK


def cmd_env_check(args: argparse.Namespace) -> int:
    import shutil

    required = ["git", "gh"]
    if args.platform == "linux":
        required += ["coi", "incus"]
    checks = {tool: bool(shutil.which(tool)) for tool in required}
    checks["GH_TOKEN"] = bool(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    ok = all(checks[t] for t in required)
    _print_json({"ok": ok, "checks": checks}, args.out)
    return EXIT_OK if ok else EXIT_ERROR


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fleetctl", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="validate registry + .fleet contracts")
    p.add_argument("--registry")
    p.add_argument("--repo-dir", action="append", default=[])
    p.add_argument("--coi", action="store_true", help="also validate generated COI config")
    p.add_argument("--out")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("normalize", help="payload -> canonical issue")
    p.add_argument("--source", required=True, choices=["jira", "linear", "github"])
    p.add_argument("--registry", help="trusted registry (github comment policy)")
    p.add_argument("--payload-file", default="-")
    p.add_argument("--event")
    p.add_argument("--trigger-label", default="agent")
    p.add_argument("--headers", type=json.loads, default={})
    p.add_argument(
        "--ingest",
        action="store_true",
        help="report webhook/normalize events to the admin ingest log",
    )
    p.add_argument("--delivery", help="webhook delivery id (e.g. X-GitHub-Delivery)")
    p.add_argument(
        "--no-enrich",
        dest="enrich",
        action="store_false",
        help="skip GitHub PR metadata fetch for issue_comment",
    )
    p.set_defaults(enrich=True)
    p.add_argument("--out")
    p.set_defaults(func=cmd_normalize)

    p = sub.add_parser("resolve", help="issue + registry -> resolution")
    p.add_argument("--registry", required=True)
    p.add_argument("--issue-file", required=True)
    p.add_argument(
        "--ingest",
        action="store_true",
        help="report the routing decision to the admin ingest log",
    )
    p.add_argument("--out")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("plan", help="build a full RunPlan")
    p.add_argument("--registry", required=True)
    p.add_argument("--repo-dir", required=True)
    p.add_argument("--issue-file")
    p.add_argument("--source", choices=["jira", "linear", "github"])
    p.add_argument("--payload-file", default="-")
    p.add_argument("--event")
    p.add_argument("--trigger-label", default="agent")
    p.add_argument("--llm-env")
    p.add_argument("--skip-coi-validate", action="store_true")
    p.add_argument("--out")
    p.set_defaults(func=cmd_plan)

    p = sub.add_parser("coi-config", help="emit/validate trusted COI config")
    p.add_argument("--registry", required=True)
    p.add_argument("--repo-dir")
    p.add_argument("--plan-file")
    p.add_argument("--llm-env")
    p.add_argument("--out")
    p.add_argument("--validate", action="store_true")
    p.set_defaults(func=cmd_coi_config)

    p = sub.add_parser("run", help="execute the bounded agent loop")
    p.add_argument("--plan-file", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--coi-config-dir")
    p.add_argument("--registry")
    p.add_argument("--bot-name")
    p.add_argument("--bot-email")
    p.add_argument("--no-publish", action="store_true")
    p.add_argument("--no-notify", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--out")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("publish", help="trusted push + PR")
    p.add_argument("--plan-file", required=True)
    p.add_argument("--workspace", required=True)
    p.add_argument("--body-file")
    p.add_argument("--registry")
    p.add_argument("--bot-name")
    p.add_argument("--bot-email")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--out")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("env-check", help="verify host tooling")
    p.add_argument("--platform", default="linux", choices=["linux", "macos", "windows"])
    p.add_argument("--out")
    p.set_defaults(func=cmd_env_check)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FleetError as exc:
        print(
            json.dumps({"ok": False, "error": str(exc), "code": exc.code}),
            file=sys.stderr,
        )
        return EXIT_ERROR
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "code": "file_not_found"}),
              file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
