import tempfile
import unittest
from pathlib import Path

from fleetctl import registry_tool as rt


class RegistryToolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "registry.local.yaml"

    def _load(self):
        return rt.load_registry(str(self.path))

    def test_add_jira_round_trips(self):
        overlay = {}
        rt.add_jira(
            overlay,
            project="ENG",
            repo="acme/engine",
            components={"web": "acme/engine-web"},
            labels=["agent"],
            base_branch="main",
        )
        rt.save_registry(str(self.path), overlay)

        data = self._load()
        entry = data["sources"]["jira"][0]
        self.assertEqual(entry["project"], "ENG")
        self.assertEqual(entry["repo"], "acme/engine")
        self.assertEqual(entry["components"], {"web": "acme/engine-web"})
        self.assertEqual(entry["labels"], ["agent"])

    def test_jira_updates_existing_entry(self):
        overlay = {"sources": {"jira": [{"project": "ENG", "repo": "old/repo"}]}}
        rt.add_jira(overlay, project="eng", repo="new/repo")
        self.assertEqual(len(overlay["sources"]["jira"]), 1)
        self.assertEqual(overlay["sources"]["jira"][0]["repo"], "new/repo")

    def test_trusted_dedupes(self):
        overlay = {}
        rt.add_trusted(overlay, ["a/b"])
        rt.add_trusted(overlay, ["a/b", "c/d"])
        self.assertEqual(overlay["allowlist"]["trusted_repos"], ["a/b", "c/d"])

    def test_native_repos_and_labels(self):
        overlay = {}
        rt.add_native(overlay, repos=["acme/ios"], labels=["fleet-agent-macos"])
        self.assertEqual(overlay["allowlist"]["native_repos"], ["acme/ios"])
        self.assertEqual(overlay["allowlist"]["native_labels"], ["fleet-agent-macos"])

    def test_github_written_as_list_and_keeps_fallback(self):
        overlay = {}
        rt.configure_github(
            overlay, prefix="/bot", author_associations=["OWNER"], allow_users=["ada"]
        )
        gh = overlay["sources"]["github"]
        self.assertIsInstance(gh, list)
        self.assertEqual(gh[0]["comment_prefix"], "/bot")
        self.assertEqual(gh[0]["comment_author_associations"], ["OWNER"])
        self.assertTrue(gh[0]["fallback_repo_from_issue"])

    def test_merge_effective_unions_lists(self):
        base = {
            "defaults": {"github_org": "acme"},
            "allowlist": {"trusted_repos": ["a/b"]},
            "sources": {"jira": [{"project": "ENG", "repo": "acme/engine"}]},
        }
        overlay = {
            "allowlist": {"trusted_repos": ["c/d"]},
            "sources": {"jira": [{"project": "ENG", "repo": "c/d"}]},
        }
        merged = rt.merge_registry(base, overlay)
        self.assertEqual(merged["allowlist"]["trusted_repos"], ["a/b", "c/d"])
        self.assertEqual(
            [e["project"] for e in merged["sources"]["jira"]], ["ENG", "ENG"]
        )

    def test_main_writes_file(self):
        rc = rt.main(
            [
                "--file",
                str(self.path),
                "jira",
                "--project",
                "ENG",
                "--repo",
                "acme/engine",
                "--labels",
                "agent,backend",
            ]
        )
        self.assertEqual(rc, 0)
        data = self._load()
        self.assertEqual(
            data["sources"]["jira"][0]["labels"], ["agent", "backend"]
        )

    def test_main_dry_run_does_not_write(self):
        rc = rt.main(
            [
                "--file",
                str(self.path),
                "--dry-run",
                "trusted",
                "acme/engine",
            ]
        )
        self.assertEqual(rc, 0)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
