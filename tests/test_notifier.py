import os
import unittest
from unittest import mock

from fleetctl.models import FleetManifest, Issue, Resolution, RunPlan, RunResult
from fleetctl.notifier import post_run_finished


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


if __name__ == "__main__":
    unittest.main()
