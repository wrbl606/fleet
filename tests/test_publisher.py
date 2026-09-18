import tempfile
import unittest
from pathlib import Path

from fleetctl.errors import PublishError
from fleetctl.models import FleetManifest, Issue, Resolution, RunPlan, StepResult
from fleetctl.publisher import branch_name, changed_files, publish

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


if __name__ == "__main__":
    unittest.main()
