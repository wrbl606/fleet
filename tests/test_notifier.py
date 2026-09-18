import os
import unittest
from unittest import mock

from fleetctl.models import FleetManifest, Issue, Resolution, RunPlan, RunResult
from fleetctl.notifier import external_id, post_run_finished


def make_plan() -> RunPlan:
    manifest = FleetManifest.from_dict(
        {"version": 1, "agent": {"tool": "claude", "inline": "x"}}
    )
    return RunPlan(
        issue=Issue(source="jira", key="ENG-1", summary="s"),
        resolution=Resolution(repo="acme/engine"),
        manifest=manifest,
        prompt="x",
        pr_title="t",
        agent_command=["claude", "x"],
        coi_config={},
        coi_config_toml="",
        repo="acme/engine",
    )


def make_pr_comment_plan(comment_id: int) -> RunPlan:
    manifest = FleetManifest.from_dict(
        {"version": 1, "agent": {"tool": "claude", "inline": "x"}}
    )
    return RunPlan(
        issue=Issue(
            source="github",
            key="o/r#14",
            summary="s",
            kind="pr_comment",
            pr_number=14,
            pr_head_branch="feature/x",
            comment_id=comment_id,
        ),
        resolution=Resolution(repo="o/r"),
        manifest=manifest,
        prompt="x",
        pr_title="t",
        agent_command=["claude", "x"],
        coi_config={},
        coi_config_toml="",
        repo="o/r",
        mode="auto",
        head_branch="feature/x",
        pr_number=14,
    )


class NotifierTest(unittest.TestCase):
    def test_run_finished_includes_build_reference(self):
        result = RunResult(
            status="succeeded",
            repo="acme/engine",
            branch="fleet/ENG-1",
            build_url="https://jenkins.example/job/fleet-dispatcher/5/",
            build_number=5,
        )
        captured = {}

        def fake_post(url, payload, headers=None):
            captured.update(payload)
            return True

        with mock.patch.dict(
            os.environ, {"FLEET_INGEST_URL": "https://panel/api/ingest"}
        ), mock.patch("fleetctl.notifier._post", side_effect=fake_post):
            self.assertTrue(post_run_finished(make_plan(), result))

        self.assertEqual(
            captured["build_url"], "https://jenkins.example/job/fleet-dispatcher/5/"
        )
        self.assertEqual(captured["build_number"], 5)
        self.assertEqual(captured["event"], "run.finished")

    def test_run_finished_omits_build_reference_when_absent(self):
        result = RunResult(status="succeeded", repo="acme/engine", branch="fleet/ENG-1")
        captured = {}

        with mock.patch.dict(
            os.environ, {"FLEET_INGEST_URL": "https://panel/api/ingest"}
        ), mock.patch(
            "fleetctl.notifier._post",
            side_effect=lambda url, payload, headers=None: captured.update(payload) or True,
        ):
            post_run_finished(make_plan(), result)

        self.assertIsNone(captured["build_url"])
        self.assertIsNone(captured["build_number"])

    def test_external_id_for_issue(self):
        self.assertEqual(external_id(make_plan()), "acme/engine#ENG-1@fleet/ENG-1")

    def test_external_id_separates_pr_comments(self):
        first = external_id(make_pr_comment_plan(1))
        second = external_id(make_pr_comment_plan(2))
        self.assertNotEqual(first, second)
        self.assertIn("#c1", first)
        self.assertIn("#c2", second)

    def test_run_finished_payload_carries_external_id(self):
        result = RunResult(status="succeeded", repo="o/r", branch="feature/x")
        captured = {}

        with mock.patch.dict(
            os.environ, {"FLEET_INGEST_URL": "https://panel/api/ingest"}
        ), mock.patch(
            "fleetctl.notifier._post",
            side_effect=lambda url, payload, headers=None: captured.update(payload) or True,
        ):
            post_run_finished(make_pr_comment_plan(9), result)

        self.assertIn("#c9", captured["external_id"])


if __name__ == "__main__":
    unittest.main()
