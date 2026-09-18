import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fleetctl.errors import PublishError
from fleetctl.models import FleetManifest, Issue, Resolution, RunPlan, StepResult
from fleetctl.publisher import (
    _push_target,
    branch_name,
    changed_files,
    publish,
)

from helpers import FakeExecutor


def make_plan() -> RunPlan:
    manifest = FleetManifest.from_dict(
        {
            "version": 1,
            "agent": {"tool": "claude", "inline": "x"},
            "pr": {"branch_prefix": "fleet/", "title": "ENG-1: fix"},
        }
    )
    return RunPlan(
        issue=Issue(source="jira", key="ENG 1/2", summary="fix", project="ENG"),
        resolution=Resolution(repo="acme/engine"),
        manifest=manifest,
        prompt="x",
        pr_title="ENG-1: fix",
        agent_command=["claude", "x"],
        coi_config={},
        coi_config_toml="",
        repo="acme/engine",
    )


class PublisherTest(unittest.TestCase):
    def test_branch_name_sanitized(self):
        self.assertEqual(branch_name(make_plan()), "fleet/ENG-1-2")

    def test_no_changes_returns_early(self):
        executor = FakeExecutor({"git status --porcelain": StepResult("git", 0, stdout="")})
        result = publish(
            make_plan(),
            "/tmp",
            executor,
            bot_name="bot",
            bot_email="b@e",
            body="body",
        )
        self.assertEqual(result.status, "no_changes")

    def test_dry_run_succeeds_without_token(self):
        executor = FakeExecutor(
            {"git status --porcelain": StepResult("git", 0, stdout=" M src/app.js\n")}
        )
        result = publish(
            make_plan(),
            "/tmp",
            executor,
            bot_name="bot",
            bot_email="b@e",
            body="body",
            dry_run=True,
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.pr_url, "(dry-run)")

    def test_agent_runtime_artifacts_are_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            info = Path(tmp) / ".git" / "info"
            info.mkdir(parents=True)
            (info / "exclude").write_text("# default excludes\n")

            executor = FakeExecutor(
                {"git status --porcelain": StepResult("git", 0, stdout="")}
            )
            result = publish(
                make_plan(),
                tmp,
                executor,
                bot_name="bot",
                bot_email="b@e",
                body="body",
            )

            self.assertEqual(result.status, "no_changes")
            content = (info / "exclude").read_text()
            self.assertIn(".claude/", content)
            self.assertIn(".opencode/", content)

    def test_push_target_uses_publish_token(self):
        url = _push_target(
            "https://x-access-token:READ@github.com/acme/engine.git",
            "acme/engine",
            "PUB",
        )
        self.assertEqual(
            url, "https://x-access-token:PUB@github.com/acme/engine.git"
        )

    def test_push_target_keeps_local_remotes(self):
        self.assertEqual(
            _push_target("/tmp/local.git", "acme/engine", "PUB"), "/tmp/local.git"
        )

    def test_changed_files_parsed(self):
        executor = FakeExecutor(
            {
                "git status --porcelain": StepResult(
                    "git", 0, stdout=" M src/app.js\n?? new.txt\n"
                )
            }
        )
        self.assertEqual(changed_files(executor, "/tmp"), ["src/app.js", "new.txt"])

    def test_missing_token_raises(self):
        import os

        old = os.environ.pop("GH_TOKEN", None)
        old2 = os.environ.pop("GITHUB_TOKEN", None)
        try:
            executor = FakeExecutor(
                {"git status --porcelain": StepResult("git", 0, stdout=" M a\n")}
            )
            with self.assertRaises(PublishError):
                publish(
                    make_plan(),
                    "/tmp",
                    executor,
                    bot_name="bot",
                    bot_email="b@e",
                    body="body",
                )
        finally:
            if old:
                os.environ["GH_TOKEN"] = old
            if old2:
                os.environ["GITHUB_TOKEN"] = old2


def make_pr_comment_plan(mode="auto", reply=True) -> RunPlan:
    manifest = FleetManifest.from_dict(
        {
            "version": 1,
            "agent": {"tool": "claude", "inline": "x"},
            "pr": {"branch_prefix": "fleet/", "title": "PR update"},
            "comment": {"mode": "auto", "reply": reply},
        }
    )
    issue = Issue(
        source="github",
        key="o/r#14",
        summary="do it",
        kind="pr_comment",
        pr_number=14,
        pr_head_branch="feature/x",
        pr_base_branch="main",
        repo_hint="o/r",
        comment_id=5,
        comment_url="https://github.com/o/r/pull/14#issuecomment-5",
    )
    return RunPlan(
        issue=issue,
        resolution=Resolution(repo="o/r", base_branch="main"),
        manifest=manifest,
        prompt="x",
        pr_title="PR #14",
        agent_command=["claude", "x"],
        coi_config={},
        coi_config_toml="",
        repo="o/r",
        mode=mode,
        head_branch="feature/x",
        pr_number=14,
        pr_url="https://github.com/o/r/pull/14",
        comment_id=5,
    )


class PrCommentPublishTest(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"GH_TOKEN": "tok"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_update_branch_appends_without_force(self):
        executor = FakeExecutor(
            {
                "git status --porcelain": StepResult("git", 0, stdout=" M a.py\n"),
                "git diff --cached": StepResult("git", 1, stdout=""),
                "git remote get-url origin": StepResult(
                    "git", 0, stdout="https://x-access-token:READ@github.com/o/r.git"
                ),
            }
        )
        result = publish(
            make_pr_comment_plan(mode="update_pr", reply=False),
            "/tmp",
            executor,
            bot_name="bot",
            bot_email="b@e",
            body="reply",
        )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(result.branch, "feature/x")
        joined = [" ".join(c) for c in executor.calls]
        self.assertTrue(any("fetch" in c and "feature/x" in c for c in joined))
        pushes = [c for c in joined if " push " in f" {c} "]
        self.assertTrue(pushes)
        self.assertFalse(any("--force-with-lease" in c for c in pushes))
        self.assertTrue(any(" commit " in f" {c} " for c in joined))
        self.assertFalse(any(c.startswith("gh pr comment") for c in joined))

    def test_existing_agent_commit_is_pushed_without_new_commit(self):
        executor = FakeExecutor(
            {
                "git status --porcelain": StepResult("git", 0, stdout=""),
                "git rev-list --count": StepResult("git", 0, stdout="1"),
                "git diff --name-only": StepResult("git", 0, stdout="CHANGELOG.md\n"),
                "git remote get-url origin": StepResult(
                    "git", 0, stdout="https://x-access-token:READ@github.com/o/r.git"
                ),
                "gh pr comment": StepResult(
                    "gh", 0, stdout="https://github.com/o/r/pull/14#issuecomment-2"
                ),
            }
        )
        result = publish(
            make_pr_comment_plan(mode="auto", reply=True),
            "/tmp",
            executor,
            bot_name="bot",
            bot_email="b@e",
            body="",
        )
        self.assertEqual(result.status, "succeeded")
        joined = [" ".join(c) for c in executor.calls]
        self.assertTrue(any(" push " in f" {c} " for c in joined))
        self.assertFalse(any(" commit " in f" {c} " for c in joined))
        self.assertTrue(result.reply_url.endswith("2"))

    def test_answer_mode_only_replies(self):
        executor = FakeExecutor(
            {
                "git status --porcelain": StepResult("git", 0, stdout=""),
                "gh pr comment": StepResult(
                    "gh", 0, stdout="https://github.com/o/r/pull/14#issuecomment-999"
                ),
            }
        )
        result = publish(
            make_pr_comment_plan(mode="answer", reply=True),
            "/tmp",
            executor,
            bot_name="bot",
            bot_email="b@e",
            body="the answer",
        )
        self.assertEqual(result.status, "succeeded")
        self.assertTrue(result.reply_url.endswith("999"))
        joined = [" ".join(c) for c in executor.calls]
        self.assertFalse(any(" push " in f" {c} " for c in joined))
        self.assertFalse(any(" commit " in f" {c} " for c in joined))

    def test_auto_without_changes_replies_only(self):
        executor = FakeExecutor(
            {
                "git status --porcelain": StepResult("git", 0, stdout=""),
                "gh pr comment": StepResult(
                    "gh", 0, stdout="https://github.com/o/r/pull/14#issuecomment-1"
                ),
            }
        )
        result = publish(
            make_pr_comment_plan(mode="auto", reply=True),
            "/tmp",
            executor,
            bot_name="bot",
            bot_email="b@e",
            body="no change",
        )
        self.assertEqual(result.reply_url.endswith("1"), True)
        joined = [" ".join(c) for c in executor.calls]
        self.assertFalse(any(" push " in f" {c} " for c in joined))

    def test_auto_with_changes_pushes(self):
        executor = FakeExecutor(
            {
                "git status --porcelain": StepResult("git", 0, stdout=" M a.py\n"),
                "git remote get-url origin": StepResult(
                    "git", 0, stdout="https://x-access-token:READ@github.com/o/r.git"
                ),
            }
        )
        result = publish(
            make_pr_comment_plan(mode="auto", reply=False),
            "/tmp",
            executor,
            bot_name="bot",
            bot_email="b@e",
            body="x",
        )
        self.assertEqual(result.status, "succeeded")
        joined = [" ".join(c) for c in executor.calls]
        self.assertTrue(any(" push " in f" {c} " for c in joined))


if __name__ == "__main__":
    unittest.main()
