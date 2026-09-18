import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fleetctl.dispatcher import execute
from fleetctl.models import (
    FleetManifest,
    Issue,
    Resolution,
    RunPlan,
    StepResult,
)

from helpers import FakeExecutor


def make_workspace(tmp: str) -> str:
    ws = Path(tmp) / "ws"
    (ws / ".fleet").mkdir(parents=True)
    (ws / ".fleet" / "setup.sh").write_text("#!/usr/bin/env bash\ntrue\n")
    (ws / ".fleet" / "verify.sh").write_text("#!/usr/bin/env bash\nfalse\n")
    return str(ws)


def make_plan(max_iterations: int = 3) -> RunPlan:
    manifest = FleetManifest.from_dict(
        {
            "version": 1,
            "agent": {
                "tool": "custom",
                "command": ["bash", "agent-stub.sh", "{{prompt}}"],
                "inline": "do {{issue.key}}",
                "max_iterations": max_iterations,
            },
            "setup": {"script": "setup.sh"},
            "verify": {"script": "verify.sh"},
        }
    )
    issue = Issue(source="jira", key="ENG-1", summary="s", project="ENG")
    return RunPlan(
        issue=issue,
        resolution=Resolution(repo="acme/engine"),
        manifest=manifest,
        prompt="do ENG-1",
        pr_title="ENG-1: s",
        agent_command=["bash", "agent-stub.sh", "do ENG-1"],
        coi_config={},
        coi_config_toml="",
        repo="acme/engine",
    )


class DispatcherTest(unittest.TestCase):
    def test_verify_passes_after_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(tmp)
            executor = FakeExecutor(
                {
                    "setup.sh": StepResult("setup", 0),
                    "agent-stub.sh": StepResult("agent", 0),
                    "verify.sh": [
                        StepResult("verify", 1, stderr="boom-1"),
                        StepResult("verify", 1, stderr="boom-2"),
                        StepResult("verify", 0),
                    ],
                }
            )
            result = execute(
                make_plan(3),
                ws,
                executor,
                coi_config_path=str(Path(tmp) / "coi.toml"),
                bot_name="bot",
                bot_email="bot@example.com",
                publish_enabled=False,
                notify=False,
            )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(len(result.iterations), 3)
        self.assertIn("Previous verification failure", result.iterations[1].prompt)
        self.assertIn("boom-1", result.iterations[1].prompt)

    def test_verify_failed_after_max_iterations(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(tmp)
            executor = FakeExecutor(
                {
                    "setup.sh": StepResult("setup", 0),
                    "agent-stub.sh": StepResult("agent", 0),
                    "verify.sh": StepResult("verify", 1, stderr="nope"),
                }
            )
            result = execute(
                make_plan(2),
                ws,
                executor,
                coi_config_path=str(Path(tmp) / "coi.toml"),
                bot_name="bot",
                bot_email="bot@example.com",
                publish_enabled=False,
                notify=False,
            )
        self.assertEqual(result.status, "verify_failed")
        self.assertEqual(len(result.iterations), 2)
        self.assertEqual(result.error_code, "verify_failed")

    def test_setup_failure_aborts(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(tmp)
            executor = FakeExecutor(
                {
                    "setup.sh": StepResult("setup", 2, stderr="bad"),
                    "agent-stub.sh": StepResult("agent", 0),
                    "verify.sh": StepResult("verify", 0),
                }
            )
            result = execute(
                make_plan(2),
                ws,
                executor,
                coi_config_path=str(Path(tmp) / "coi.toml"),
                bot_name="bot",
                bot_email="bot@example.com",
                publish_enabled=False,
                notify=False,
            )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "setup")
        self.assertEqual(result.iterations, [])

    def test_agent_failure_aborts(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(tmp)
            executor = FakeExecutor(
                {
                    "setup.sh": StepResult("setup", 0),
                    "agent-stub.sh": StepResult("agent", 1, stderr="crash"),
                    "verify.sh": StepResult("verify", 0),
                }
            )
            result = execute(
                make_plan(2),
                ws,
                executor,
                coi_config_path=str(Path(tmp) / "coi.toml"),
                bot_name="bot",
                bot_email="bot@example.com",
                publish_enabled=False,
                notify=False,
            )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.error_code, "agent")

    def test_captures_jenkins_build_reference_from_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(tmp)
            executor = FakeExecutor(
                {
                    "setup.sh": StepResult("setup", 0),
                    "agent-stub.sh": StepResult("agent", 0),
                    "verify.sh": StepResult("verify", 0),
                }
            )
            env = {
                "BUILD_URL": "https://jenkins.example/job/fleet-dispatcher/7/",
                "BUILD_NUMBER": "7",
            }
            with mock.patch.dict(os.environ, env):
                result = execute(
                    make_plan(2),
                    ws,
                    executor,
                    coi_config_path=str(Path(tmp) / "coi.toml"),
                    bot_name="bot",
                    bot_email="bot@example.com",
                    publish_enabled=False,
                    notify=False,
                )
        self.assertEqual(result.status, "succeeded")
        self.assertEqual(
            result.build_url, "https://jenkins.example/job/fleet-dispatcher/7/"
        )
        self.assertEqual(result.build_number, 7)

    def test_build_number_non_numeric_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = make_workspace(tmp)
            executor = FakeExecutor(
                {
                    "setup.sh": StepResult("setup", 0),
                    "agent-stub.sh": StepResult("agent", 0),
                    "verify.sh": StepResult("verify", 0),
                }
            )
            with mock.patch.dict(os.environ, {"BUILD_URL": "x", "BUILD_NUMBER": "n/a"}):
                result = execute(
                    make_plan(2),
                    ws,
                    executor,
                    coi_config_path=str(Path(tmp) / "coi.toml"),
                    bot_name="bot",
                    bot_email="bot@example.com",
                    publish_enabled=False,
                    notify=False,
                )
        self.assertIsNone(result.build_number)


if __name__ == "__main__":
    unittest.main()
