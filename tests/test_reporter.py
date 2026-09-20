import os
import unittest
from pathlib import Path
from unittest import mock

from fleetctl import cli, reporter

REPO = Path(__file__).resolve().parent.parent


class ReporterTest(unittest.TestCase):
    def test_disabled_without_url(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(reporter.enabled())
            self.assertFalse(reporter.post_event({"event": "x"}))

    def test_post_event_sends_bearer_token(self):
        captured = {}

        def fake_post(url, payload, headers=None):
            captured.update(url=url, headers=headers, payload=payload)
            return True

        with mock.patch.dict(
            os.environ,
            {
                "FLEET_INGEST_URL": "https://panel/api/ingest",
                "FLEET_INGEST_TOKEN": "tok",
            },
        ), mock.patch("fleetctl.reporter._post", side_effect=fake_post):
            self.assertTrue(reporter.post_event({"event": "webhook.received"}))

        self.assertEqual(captured["url"], "https://panel/api/ingest")
        self.assertEqual(captured["headers"], {"Authorization": "Bearer tok"})

    def test_payload_text_truncates(self):
        text = reporter.payload_text({"blob": "a" * reporter.MAX_PAYLOAD})
        self.assertTrue(text.endswith("…(truncated)"))


class NormalizeIngestTest(unittest.TestCase):
    def test_normalize_reports_received_and_result(self):
        events = []
        with mock.patch(
            "fleetctl.cli.post_event",
            side_effect=lambda payload: events.append(payload) or True,
        ):
            rc = cli.main(
                [
                    "normalize",
                    "--source",
                    "jira",
                    "--payload-file",
                    str(REPO / "tests" / "fixtures" / "issue-created.json"),
                    "--registry",
                    str(REPO / "registry.yaml"),
                    "--ingest",
                ]
            )

        self.assertEqual(rc, 0)
        self.assertEqual(
            [e["event"] for e in events], ["webhook.received", "normalize.result"]
        )
        self.assertTrue(events[1]["actionable"])
        self.assertIn("issue", events[1])

    def test_resolve_reports_routing(self):
        issue = REPO / "tests" / "fixtures" / "issue-created.json"
        # Normalize first so we have a canonical issue file.
        import tempfile

        events = []
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            issue_path = fh.name
        try:
            from fleetctl.cli import main as cli_main

            cli_main(
                [
                    "normalize",
                    "--source",
                    "jira",
                    "--payload-file",
                    str(issue),
                    "--registry",
                    str(REPO / "registry.yaml"),
                    "--out",
                    issue_path,
                ]
            )
            with mock.patch(
                "fleetctl.cli.post_event",
                side_effect=lambda payload: events.append(payload) or True,
            ):
                rc = cli_main(
                    [
                        "resolve",
                        "--registry",
                        str(REPO / "registry.yaml"),
                        "--issue-file",
                        issue_path,
                        "--ingest",
                    ]
                )
        finally:
            os.unlink(issue_path)

        self.assertEqual(rc, 0)
        self.assertEqual(events[0]["event"], "resolve.result")
        self.assertEqual(events[0]["repo"], "acme/engine-api")


if __name__ == "__main__":
    unittest.main()
