import tomllib
import unittest
from pathlib import Path

from fleetctl.coi_config import (
    build_coi_config,
    dumps_toml,
    format_duration,
    parse_duration,
    validate_coi_config,
    write_coi_config,
)
from fleetctl.models import FleetManifest
from fleetctl.registry import Registry

REPO = Path(__file__).resolve().parent.parent
SAMPLE = REPO / "examples" / "sample-repo"


class DurationTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_duration("30m"), 1800)
        self.assertEqual(parse_duration("1h30m"), 5400)
        self.assertEqual(parse_duration("90s"), 90)
        self.assertEqual(parse_duration("2h"), 7200)

    def test_format(self):
        self.assertEqual(format_duration(1800), "30m")
        self.assertEqual(format_duration(3600), "1h")
        self.assertEqual(format_duration(90), "90s")

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_duration("soon")


class CoiConfigTest(unittest.TestCase):
    def setUp(self):
        self.reg = Registry.from_file(str(REPO / "registry.yaml"))
        self.manifest = FleetManifest.from_file(str(SAMPLE / ".fleet" / "fleet.toml"))

    def test_forward_env_only_when_declared(self):
        cfg = build_coi_config(self.manifest, self.reg, llm_env="ANTHROPIC_API_KEY")
        self.assertEqual(cfg["forward_env"], ["ANTHROPIC_API_KEY"])
        cfg2 = build_coi_config(self.manifest, self.reg, llm_env=None)
        self.assertNotIn("forward_env", cfg2)

    def test_untrusted_limits_are_registry_owned(self):
        cfg = build_coi_config(self.manifest, self.reg, llm_env=None)
        self.assertEqual(cfg["limits"]["memory"]["limit"], "4GiB")
        self.assertTrue(cfg["limits"]["runtime"]["auto_stop"])

    def test_host_immutable_disabled_for_trusted_publisher(self):
        # chattr +i on the host breaks the unprivileged publisher and workspace
        # reuse; container-side read-only mounts still protect .git.
        cfg = build_coi_config(self.manifest, self.reg, llm_env=None)
        self.assertFalse(cfg["security"]["host_immutable"])

    def test_timeout_is_capped(self):
        m = FleetManifest.from_dict(
            {
                "version": 1,
                "agent": {"tool": "claude", "inline": "x"},
                "coi": {"timeout": "5h"},
            }
        )
        cfg = build_coi_config(m, self.reg, llm_env=None)
        self.assertEqual(cfg["limits"]["runtime"]["max_duration"], "1h")

    def test_allowlist_mode_carries_domains(self):
        m = FleetManifest.from_dict(
            {
                "version": 1,
                "agent": {"tool": "claude", "inline": "x"},
                "coi": {"network": "allowlist", "allowed_domains": ["example.com"]},
            }
        )
        cfg = build_coi_config(m, self.reg, llm_env=None)
        self.assertEqual(cfg["network"]["mode"], "allowlist")
        self.assertIn("api.anthropic.com", cfg["network"]["allowed_domains"])
        self.assertIn("example.com", cfg["network"]["allowed_domains"])

    def test_toml_round_trips_and_coi_validates(self):
        cfg = build_coi_config(self.manifest, self.reg, llm_env="ANTHROPIC_API_KEY")
        text = dumps_toml(cfg)
        parsed = tomllib.loads(text)
        self.assertEqual(parsed["forward_env"], ["ANTHROPIC_API_KEY"])
        self.assertEqual(parsed["network"]["mode"], "restricted")

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            write_coi_config(str(path), text)
            ok, errors = validate_coi_config(str(path))
        self.assertTrue(ok, errors)


if __name__ == "__main__":
    unittest.main()
