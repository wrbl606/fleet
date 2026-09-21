import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fleetctl.errors import AllowlistError, ResolutionError
from fleetctl.models import Issue
from fleetctl.registry import Registry, discover_local_registry

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "registry.yaml"

BASE_YAML = """\
defaults:
  github_org: acme
  default_branch: main
allowlist:
  trusted_repos: ["acme/engine"]
sources:
  jira:
    - project: ENG
      repo: acme/engine
"""

LOCAL_YAML = """\
defaults:
  default_branch: trunk
allowlist:
  trusted_repos: ["acme/overlay-repo"]
bot:
  name: local-bot
  email: local@example.com
sources:
  jira:
    - project: LOCAL
      repo: acme/overlay-repo
"""


def mk_issue(**kw):
    base = dict(source="jira", key="ENG-1", summary="s", project="ENG")
    base.update(kw)
    return Issue(**base)


class RegistryTest(unittest.TestCase):
    def setUp(self):
        self.reg = Registry.from_file(str(REGISTRY))

    def test_loads_defaults(self):
        self.assertEqual(self.reg.github_org, "acme")
        self.assertEqual(self.reg.default_branch, "main")
        self.assertIn("fleet-agent", self.reg.labels)

    def test_component_mapping(self):
        r = self.reg.resolve(mk_issue(component="backend"))
        self.assertEqual(r.repo, "acme/engine-api")
        self.assertFalse(r.native)
        self.assertEqual(r.jenkins_label, "fleet-agent")

    def test_component_case_insensitive(self):
        r = self.reg.resolve(mk_issue(component="WEB"))
        self.assertEqual(r.repo, "acme/engine-web")

    def test_project_fallback_repo(self):
        r = self.reg.resolve(mk_issue(component=None))
        self.assertEqual(r.repo, "acme/engine")

    def test_unknown_project_fails(self):
        with self.assertRaises(ResolutionError):
            self.reg.resolve(mk_issue(project="NOPE"))

    def test_native_fails_closed_when_not_allowlisted(self):
        data = self.reg.raw
        data["sources"]["jira"].append(
            {"project": "IOS", "repo": "acme/not-allowed", "platform": "macos"}
        )
        reg = Registry.from_dict(data)
        with self.assertRaises(AllowlistError):
            reg.resolve(mk_issue(project="IOS"))

    def test_native_allowlisted_repo_ok(self):
        data = self.reg.raw
        data["sources"]["jira"].append(
            {"project": "IOS", "repo": "acme/ios-app", "platform": "macos", "requires": ["xcode-15"]}
        )
        reg = Registry.from_dict(data)
        r = reg.resolve(mk_issue(project="IOS"))
        self.assertTrue(r.native)
        self.assertEqual(r.jenkins_label, "fleet-agent-macos && xcode-15")
        self.assertEqual(
            r.native_options["seatbelt_profile"], "resources/native/seatbelt.sb"
        )

    def test_native_windows_wrapper_option(self):
        data = self.reg.raw
        data["native"]["windows"]["wrapper"] = ["powershell", "-File", "w.ps1", "--"]
        data["sources"]["jira"].append(
            {"project": "WIN", "repo": "acme/win-tool", "platform": "windows"}
        )
        reg = Registry.from_dict(data)
        r = reg.resolve(mk_issue(project="WIN"))
        self.assertTrue(r.native)
        self.assertEqual(
            r.native_options["windows_wrapper"], ["powershell", "-File", "w.ps1", "--"]
        )

    def test_native_allowlisted_label_ok(self):
        data = self.reg.raw
        data["sources"]["jira"].append(
            {
                "project": "WIN",
                "repo": "acme/anything",
                "platform": "windows",
                "labels": ["fleet-agent-windows"],
            }
        )
        reg = Registry.from_dict(data)
        r = reg.resolve(mk_issue(project="WIN"))
        self.assertTrue(r.native)

    def test_github_issue_uses_webhook_default_branch(self):
        issue = mk_issue(
            source="github",
            key="o/r#4",
            project="",
            repo_hint="o/r",
            default_branch="development",
        )
        r = self.reg.resolve(issue)
        self.assertEqual(r.repo, "o/r")
        self.assertEqual(r.base_branch, "development")

    def test_github_issue_falls_back_to_registry_default_branch(self):
        issue = mk_issue(source="github", key="o/r#4", project="", repo_hint="o/r")
        r = self.reg.resolve(issue)
        self.assertEqual(r.base_branch, "main")

    def test_source_base_branch_overrides_webhook_default(self):
        data = self.reg.raw
        data["sources"]["jira"].append(
            {"project": "REL", "repo": "acme/engine", "base_branch": "release"}
        )
        reg = Registry.from_dict(data)
        r = reg.resolve(mk_issue(project="REL", default_branch="development"))
        self.assertEqual(r.base_branch, "release")

    def test_missing_github_org_rejected(self):
        from fleetctl.errors import ValidationError

        with self.assertRaises(ValidationError):
            Registry.from_dict({"defaults": {}, "sources": {}})


class RegistryOverlayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.base = self.dir / "registry.yaml"
        self.local = self.dir / "registry.local.yaml"
        self.base.write_text(BASE_YAML)
        self.local.write_text(LOCAL_YAML)

    def _merged(self) -> Registry:
        return Registry.from_file(str(self.base), local_path=str(self.local))

    def test_overlay_unions_lists_and_appends_sources(self):
        reg = self._merged()
        self.assertIn("acme/engine", reg.trusted_repos)
        self.assertIn("acme/overlay-repo", reg.trusted_repos)
        projects = [e["project"] for e in reg.jira]
        self.assertIn("ENG", projects)
        self.assertIn("LOCAL", projects)
        self.assertEqual(
            reg.resolve(
                Issue(source="jira", key="LOCAL-1", summary="s", project="LOCAL")
            ).repo,
            "acme/overlay-repo",
        )

    def test_overlay_scalars_override(self):
        reg = self._merged()
        self.assertEqual(reg.default_branch, "trunk")
        self.assertEqual(reg.bot_name, "local-bot")
        self.assertEqual(reg.bot_email, "local@example.com")

    def test_base_without_overlay_stays_generic(self):
        reg = Registry.from_file(str(self.base))
        self.assertNotIn("acme/overlay-repo", reg.trusted_repos)
        self.assertEqual(reg.default_branch, "main")

    def test_discover_local_registry_sibling(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FLEET_REGISTRY_LOCAL", None)
            self.assertEqual(
                discover_local_registry(str(self.base)), str(self.local)
            )
            self.local.unlink()
            self.assertIsNone(discover_local_registry(str(self.base)))

    def test_discover_local_registry_env_override(self):
        with mock.patch.dict(
            os.environ, {"FLEET_REGISTRY_LOCAL": "/tmp/elsewhere.yaml"}
        ):
            self.assertEqual(
                discover_local_registry(str(self.base)), "/tmp/elsewhere.yaml"
            )


if __name__ == "__main__":
    unittest.main()
