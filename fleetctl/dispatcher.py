"""Bounded setup -> agent -> verify loop + publish/notify orchestration (P2)."""

from __future__ import annotations

import os

from .exec_ import Executor, tail
from .models import IterationRecord, RunPlan, RunResult, StepResult
from .notifier import notify_issue, post_run_finished
from .publisher import branch_name
from .runners import make_backend

RETRY_HEADER = (
    "\n\n---\n"
    "## Previous verification failure (iteration {n})\n"
    "A previous attempt to implement this task failed the repository's "
    "verification gate. Fix the failures below, then ensure `verify.sh` passes.\n\n"
)


def _build_number(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _retry_prompt(base: str, n: int, verify: StepResult) -> str:
    detail = (verify.stderr or "").strip() or (verify.stdout or "").strip()
    return base + RETRY_HEADER.format(n=n) + "```\n" + tail(detail) + "\n```\n"


def execute(
    plan: RunPlan,
    workspace: str,
    executor: Executor,
    *,
    coi_config_path: str,
    bot_name: str,
    bot_email: str,
    publish_enabled: bool = True,
    dry_run: bool = False,
    notify: bool = True,
) -> RunResult:
    from .planner import render_pr_body
    from .publisher import publish as do_publish

    result = RunResult(
        status="failed",
        repo=plan.repo,
        branch=plan.branch(),
        # Jenkins sets these in the build environment; absent for local runs.
        build_url=os.environ.get("BUILD_URL"),
        build_number=_build_number(os.environ.get("BUILD_NUMBER")),
        artifacts={"coi_config": plan.coi_config},
    )

    backend = make_backend(
        plan, workspace, executor, coi_config_path=coi_config_path
    )

    try:
        setup = backend.run_setup()
        result.artifacts["setup"] = setup.to_dict()
        if not setup.ok:
            return _fail(
                result, "setup", f"setup.sh failed (exit {setup.exit_code})", notify, plan
            )

        prompt = plan.prompt
        passed = False
        for n in range(1, plan.manifest.agent.max_iterations + 1):
            agent = backend.run_agent(prompt)
            record = IterationRecord(n=n, prompt=prompt, agent=agent)
            result.iterations.append(record)

            if not agent.ok:
                return _fail(
                    result,
                    "agent",
                    f"agent exited {agent.exit_code} on iteration {n}",
                    notify,
                    plan,
                )

            verify = backend.run_verify()
            record.verify = verify
            if verify.ok:
                passed = True
                break

            prompt = _retry_prompt(plan.prompt, n, verify)

        if not passed:
            result.status = "verify_failed"
            result.error = (
                f"verify.sh still failing after {plan.manifest.agent.max_iterations} "
                "iteration(s)"
            )
            result.error_code = "verify_failed"
            _finalize(result, plan, notify)
            return result

        if publish_enabled:
            # PR comments get their reply body generated inside the publisher,
            # from the final (post-exclude) changed-file set.
            body = "" if plan.issue.is_pr_comment else render_pr_body(plan, workspace)
            pub = do_publish(
                plan,
                workspace,
                executor,
                bot_name=bot_name,
                bot_email=bot_email,
                body=body,
                dry_run=dry_run,
            )
            result.status = pub.status
            result.pr_url = pub.pr_url
            result.branch = pub.branch
            result.reply_url = pub.reply_url
            result.artifacts["changed_files"] = pub.changed_files
        else:
            result.status = "succeeded"
            result.artifacts["changed_files"] = []

        _finalize(result, plan, notify)
        return result
    finally:
        backend.cleanup()


def _fail(
    result: RunResult,
    code: str,
    message: str,
    notify: bool,
    plan: RunPlan,
) -> RunResult:
    result.status = "failed"
    result.error = message
    result.error_code = code
    _finalize(result, plan, notify)
    return result


def _finalize(result: RunResult, plan: RunPlan, notify: bool) -> None:
    if not notify:
        return
    if result.pr_url:
        notify_issue(plan, f"Fleet agent opened a PR: {result.pr_url}")
    elif result.status in ("failed", "verify_failed"):
        notify_issue(
            plan,
            f"Fleet agent run did not produce a PR ({result.error or result.status}).",
        )
    post_run_finished(plan, result)
