import tempfile
import unittest
from pathlib import Path

from fleetctl.errors import RunnerError
from fleetctl.models import FleetManifest, Issue, Resolution, RunPlan
from fleetctl.runners import NativeRunnerBackend

from helpers import FakeExecutor


def make_plan(platform="macos", native_options=None):
    manifest = FleetManifest.from_dict(
        {
            "version": 1,
            "agent": {"tool": "claude", "inline": "x"},
            "platform": {"os": platform},
        }
    )
    return RunPlan(
        issue=Issue(source="jira", key="IOS-1", summary="s", project="IOS"),
        resolution=Resolution(
            repo="acme/ios-app",
            platform=platform,
            native=True,
            native_options=native_options or {},
        ),
        manifest=manifest,
        prompt="x",
        pr_title="IOS-1: s",
        agent_command=["claude", "x"],
        coi_config={},
        coi_config_toml="",
        repo="acme/ios-app",
    )


class NativeRunnerTest(unittest.TestCase):
    def test_macos_wraps_with_seatbelt(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = Path(tmp) / "seatbelt.sb"
            profile.write_text("(version 1)\n(allow default)\n")
            plan = make_plan("macos", {"seatbelt_profile": str(profile)})
            backend = NativeRunnerBackend(plan, tmp, FakeExecutor())

            argv = backend._wrap(["bash", ".fleet/setup.sh"])
            self.assertEqual(argv[0], "sandbox-exec")
            self.assertIn("-f", argv)
            self.assertIn(str(profile), argv)
            self.assertIn(f"WORKSPACE={Path(tmp).resolve()}", argv)
            self.assertEqual(argv[-2:], ["bash", ".fleet/setup.sh"])

    def test_macos_missing_profile_fails_closed(self):
        plan = make_plan("macos", {"seatbelt_profile": "/nope/seatbelt.sb"})
        backend = NativeRunnerBackend(plan, "/tmp", FakeExecutor())
        with self.assertRaises(RunnerError):
            backend._wrap(["bash", "x"])

    def test_windows_uses_wrapper_prefix(self):
        plan = make_plan("macos", {})
        backend = NativeRunnerBackend(plan, "/tmp", FakeExecutor())
        backend.plan.resolution.platform = "windows"
        backend.plan.resolution.native_options = {
            "windows_wrapper": ["powershell", "-File", "w.ps1", "--"]
        }
        self.assertEqual(
            backend._wrap(["cmd"]), ["powershell", "-File", "w.ps1", "--", "cmd"]
        )

    def test_no_sandbox_configured_runs_raw(self):
        plan = make_plan("macos", {})
        backend = NativeRunnerBackend(plan, "/tmp", FakeExecutor())
        backend.plan.resolution.platform = "freebsd"
        self.assertEqual(backend._wrap(["cmd"]), ["cmd"])

    def test_refuses_linux_task(self):
        plan = make_plan("macos", {})
        plan.resolution.native = False
        plan.resolution.platform = "linux"
        with self.assertRaises(RunnerError):
            NativeRunnerBackend(plan, "/tmp", FakeExecutor())

    def test_refuses_windows_on_non_windows_host(self):
        plan = make_plan("windows", {})
        with self.assertRaises(RunnerError):
            NativeRunnerBackend(plan, "/tmp", FakeExecutor())


if __name__ == "__main__":
    unittest.main()
