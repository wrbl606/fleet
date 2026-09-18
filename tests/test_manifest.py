import unittest
from pathlib import Path

from fleetctl.errors import ValidationError
from fleetctl.models import FleetManifest

REPO = Path(__file__).resolve().parent.parent
SAMPLE = REPO / "examples" / "sample-repo"
STUB = REPO / "tests" / "fixtures" / "stub-repo"


class ManifestTest(unittest.TestCase):
    def test_sample_repo_parses(self):
        m = FleetManifest.from_file(str(SAMPLE / ".fleet" / "fleet.toml"))
        self.assertEqual(m.agent.tool, "claude")
        self.assertEqual(m.agent.prompt_file, "prompts/task.md")
        self.assertEqual(m.agent.max_iterations, 3)
        self.assertEqual(m.agent.llm_env, "ANTHROPIC_API_KEY")
        self.assertEqual(m.pr.branch_prefix, "fleet/")
        self.assertEqual(m.platform.os, "linux")
        self.assertEqual(m.coi.network, "restricted")

    def test_stub_repo_custom_command(self):
        m = FleetManifest.from_file(str(STUB / ".fleet" / "fleet.toml"))
        self.assertEqual(m.agent.tool, "custom")
        self.assertIn("{{prompt}}", m.agent.command)

    def test_requires_prompt_xor_inline(self):
        data = {"version": 1, "agent": {"tool": "claude"}}
        with self.assertRaises(ValidationError):
            FleetManifest.from_dict(data)

    def test_rejects_unsafe_prompt_path(self):
        data = {
            "version": 1,
            "agent": {"tool": "claude", "prompt_file": "../../etc/passwd"},
        }
        with self.assertRaises(ValidationError):
            FleetManifest.from_dict(data)

    def test_rejects_bad_network(self):
        data = {
            "version": 1,
            "agent": {"tool": "claude", "inline": "x"},
            "coi": {"network": "wide-open"},
        }
        with self.assertRaises(ValidationError):
            FleetManifest.from_dict(data)

    def test_rejects_custom_without_command(self):
        data = {"version": 1, "agent": {"tool": "custom", "inline": "x"}}
        with self.assertRaises(ValidationError):
            FleetManifest.from_dict(data)

    def test_rejects_unknown_version(self):
        data = {"version": 2, "agent": {"tool": "claude", "inline": "x"}}
        with self.assertRaises(ValidationError):
            FleetManifest.from_dict(data)

    def test_round_trip(self):
        m = FleetManifest.from_file(str(SAMPLE / ".fleet" / "fleet.toml"))
        again = FleetManifest.from_dict(m.to_dict())
        self.assertEqual(m.to_dict(), again.to_dict())


if __name__ == "__main__":
    unittest.main()
