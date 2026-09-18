import unittest
from pathlib import Path

from fleetctl.models import Issue
from fleetctl.planner import build_plan, render_pr_body
from fleetctl.registry import Registry

REPO = Path(__file__).resolve().parent.parent
STUB = REPO / "tests" / "fixtures" / "stub-repo"


class PlannerTest(unittest.TestCase):
    def setUp(self):
        self.reg = Registry.from_file(str(REPO / "registry.yaml"))
        self.issue = Issue(
            source="jira",
            key="ENG-1",
            summary="Fix the login bug",
            description="plus sign breaks login",
            issue_type="Bug",
            labels=["agent"],
            project="ENG",
            component="backend",
            url="https://acme.atlassian.net/browse/ENG-1",
        )

    def test_builds_full_plan(self):
        plan = build_plan(self.issue, self.reg, str(STUB))
        self.assertEqual(plan.repo, "acme/engine-api")
        self.assertEqual(plan.pr_title, "ENG-1: Fix the login bug")
        self.assertEqual(plan.agent_command[0], "bash")
        self.assertIn("Task ENG-1: Fix the login bug", plan.agent_command[-1])
        self.assertEqual(plan.manifest.agent.tool, "custom")
        self.assertEqual(plan.coi_config["network"]["mode"], "restricted")
        self.assertIn("container", plan.coi_config)

    def test_plan_round_trips(self):
        from fleetctl.models import RunPlan

        plan = build_plan(self.issue, self.reg, str(STUB))
        again = RunPlan.from_dict(plan.to_dict())
        self.assertEqual(plan.to_dict(), again.to_dict())

    def test_pr_body_default(self):
        plan = build_plan(self.issue, self.reg, str(STUB))
        body = render_pr_body(plan, str(STUB))
        self.assertIn("ENG-1", body)

    def test_pr_body_template(self):
        plan = build_plan(self.issue, self.reg, str(STUB))
        body = render_pr_body(plan, str(STUB))
        self.assertIn("Automated change for ENG-1", body)

    def test_untrusted_repo_gets_hardened_profile(self):
        data = self.reg.raw
        data["allowlist"]["trusted_repos"] = []
        reg = Registry.from_dict(data)
        plan = build_plan(self.issue, reg, str(STUB))
        self.assertEqual(plan.manifest.coi.profile, "hardened")

    def test_trusted_repo_keeps_repo_profile(self):
        plan = build_plan(self.issue, self.reg, str(STUB))
        # acme/engine-api is trusted and the stub manifest pins no profile
        self.assertEqual(plan.manifest.coi.profile, "")

    def _pr_issue(self, **over):
        base = dict(
            source="github",
            key="o/r#14",
            summary="change it",
            kind="pr_comment",
            repo_hint="o/r",
            pr_number=14,
            pr_head_branch="feature/x",
            pr_base_branch="main",
            comment_body="/agent change it",
            command="change it",
            comment_id=1,
            comment_url="https://github.com/o/r/pull/14#issuecomment-1",
        )
        base.update(over)
        return Issue(**base)

    def test_pr_comment_auto_mode(self):
        plan = build_plan(self._pr_issue(), self.reg, str(STUB))
        self.assertEqual(plan.mode, "auto")
        self.assertEqual(plan.head_branch, "feature/x")
        self.assertEqual(plan.pr_number, 14)
        self.assertEqual(plan.pr_url, "https://github.com/o/r/pull/14")
        self.assertIn("change it", plan.prompt)

    def test_pr_comment_fork_is_answer_only(self):
        plan = build_plan(self._pr_issue(pr_head_repo="someone/r"), self.reg, str(STUB))
        self.assertEqual(plan.mode, "answer")

    def test_resolve_mode_from_manifest(self):
        from fleetctl.models import FleetManifest
        from fleetctl.planner import _resolve_mode

        def manifest(**comment):
            return FleetManifest.from_dict(
                {
                    "version": 1,
                    "agent": {"tool": "claude", "inline": "x"},
                    "comment": comment,
                }
            )

        issue = self._pr_issue()
        self.assertEqual(_resolve_mode(issue, manifest(mode="answer")), "answer")
        self.assertEqual(_resolve_mode(issue, manifest(mode="code")), "update_pr")
        self.assertEqual(_resolve_mode(issue, manifest(mode="auto")), "auto")
        self.assertEqual(_resolve_mode(issue, manifest(enabled=False)), "answer")


if __name__ == "__main__":
    unittest.main()
