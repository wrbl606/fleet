import json
import unittest
from pathlib import Path

from fleetctl.normalizers.jira import JiraNormalizer, adf_to_text

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


class AdfTest(unittest.TestCase):
    def test_flattens_paragraphs_and_code(self):
        text = adf_to_text(
            {
                "type": "doc",
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": "hello"}]},
                    {"type": "codeBlock", "content": [{"type": "text", "text": "x=1"}]},
                ],
            }
        )
        self.assertIn("hello", text)
        self.assertIn("x=1", text)
        self.assertIn("\n", text)

    def test_plain_string(self):
        self.assertEqual(adf_to_text("plain"), "plain")


class JiraNormalizerTest(unittest.TestCase):
    def setUp(self):
        self.n = JiraNormalizer(trigger_label="agent")

    def test_created_is_actionable(self):
        issue = self.n.normalize(load("issue-created.json"))
        self.assertIsNotNone(issue)
        assert issue is not None
        self.assertEqual(issue.key, "ENG-123")
        self.assertEqual(issue.issue_type, "Bug")
        self.assertEqual(issue.project, "ENG")
        self.assertEqual(issue.component, "backend")
        self.assertEqual(issue.reporter, "Ada Lovelace")
        self.assertEqual(issue.url, "https://acme.atlassian.net/browse/ENG-123")
        self.assertIn("plus sign", issue.description)
        self.assertEqual(issue.event, "jira:issue_created")

    def test_updated_with_label_change_is_actionable(self):
        issue = self.n.normalize(load("issue-updated.json"))
        self.assertIsNotNone(issue)
        assert issue is not None
        self.assertEqual(issue.key, "ENG-124")
        self.assertEqual(issue.component, "web")

    def test_irrelevant_update_filtered(self):
        self.assertIsNone(self.n.normalize(load("issue-updated-irrelevant.json")))

    def test_unknown_event_filtered(self):
        payload = load("issue-created.json")
        payload["webhookEvent"] = "jira:issue_deleted"
        self.assertIsNone(self.n.normalize(payload))

    def test_custom_trigger_label(self):
        n = JiraNormalizer(trigger_label="fleet")
        self.assertIsNone(n.normalize(load("issue-updated.json")))


if __name__ == "__main__":
    unittest.main()
