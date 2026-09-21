import unittest

from fleetctl.normalizers.github import GithubNormalizer


def issue_comment(body="/agent add tests", **over):
    payload = {
        "action": "created",
        "issue": {
            "number": 14,
            "title": "Add widget",
            "body": "pr body",
            "pull_request": {"url": "https://api.github.com/repos/o/r/pulls/14"},
            "labels": [{"name": "agent"}],
            "user": {"login": "bob"},
            "html_url": "https://github.com/o/r/pull/14",
        },
        "comment": {
            "id": 555,
            "body": body,
            "html_url": "https://github.com/o/r/pull/14#issuecomment-555",
            "user": {"login": "alice", "type": "User"},
            "author_association": "MEMBER",
        },
        "repository": {"full_name": "o/r"},
    }
    payload.update(over)
    return payload


def issue_event(**over):
    payload = {
        "action": "opened",
        "issue": {
            "number": 4,
            "title": "chore: use mise",
            "body": "Create mise.toml",
            "labels": [],
            "user": {"login": "bob"},
            "html_url": "https://github.com/o/r/issues/4",
        },
        "repository": {"full_name": "o/r", "default_branch": "development"},
    }
    payload.update(over)
    return payload


def review_comment(body="/agent explain this"):
    return {
        "action": "created",
        "comment": {
            "id": 777,
            "body": body,
            "html_url": "https://github.com/o/r/pull/14#discussion_r777",
            "user": {"login": "alice", "type": "User"},
            "author_association": "OWNER",
        },
        "pull_request": {
            "number": 14,
            "state": "open",
            "head": {"ref": "fleet/CUT-1", "repo": {"full_name": "o/r"}},
            "base": {"ref": "main"},
        },
        "repository": {"full_name": "o/r"},
    }


class GithubNormalizerTest(unittest.TestCase):
    def setUp(self):
        self.n = GithubNormalizer()

    def test_issue_comment_command(self):
        issue = self.n.normalize(issue_comment(), event="issue_comment")
        self.assertIsNotNone(issue)
        self.assertEqual(issue.kind, "pr_comment")
        self.assertEqual(issue.repo_hint, "o/r")
        self.assertEqual(issue.pr_number, 14)
        self.assertEqual(issue.command, "add tests")
        self.assertEqual(issue.comment_id, 555)
        self.assertEqual(issue.author, "alice")
        self.assertIsNone(issue.pr_head_branch)  # enriched later

    def test_bare_prefix_is_actionable(self):
        issue = self.n.normalize(issue_comment("/agent"), event="issue_comment")
        self.assertIsNotNone(issue)
        self.assertEqual(issue.command, "")

    def test_prefix_must_be_a_word_boundary(self):
        self.assertIsNone(
            self.n.normalize(issue_comment("/agents please"), event="issue_comment")
        )

    def test_non_command_ignored(self):
        self.assertIsNone(
            self.n.normalize(issue_comment("looks good to me"), event="issue_comment")
        )

    def test_bot_author_ignored(self):
        p = issue_comment()
        p["comment"]["user"] = {"login": "fleet-agent[bot]", "type": "Bot"}
        self.assertIsNone(self.n.normalize(p, event="issue_comment"))

    def test_unauthorized_association_ignored(self):
        p = issue_comment()
        p["comment"]["author_association"] = "NONE"
        self.assertIsNone(self.n.normalize(p, event="issue_comment"))

    def test_allowlisted_user_overrides_association(self):
        n = GithubNormalizer(allow_users=["stranger"])
        p = issue_comment()
        p["comment"]["user"] = {"login": "stranger", "type": "User"}
        p["comment"]["author_association"] = "NONE"
        self.assertIsNotNone(n.normalize(p, event="issue_comment"))

    def test_comment_on_plain_issue_ignored(self):
        p = issue_comment()
        p["issue"].pop("pull_request")
        self.assertIsNone(self.n.normalize(p, event="issue_comment"))

    def test_edited_action_ignored(self):
        self.assertIsNone(
            self.n.normalize(issue_comment(action="edited"), event="issue_comment")
        )

    def test_custom_prefix(self):
        n = GithubNormalizer(comment_prefix="/bot")
        self.assertIsNotNone(n.normalize(issue_comment("/bot go"), event="issue_comment"))
        self.assertIsNone(n.normalize(issue_comment("/agent go"), event="issue_comment"))

    def test_review_comment_carries_branch(self):
        issue = self.n.normalize(
            review_comment(), event="pull_request_review_comment"
        )
        self.assertIsNotNone(issue)
        self.assertEqual(issue.pr_head_branch, "fleet/CUT-1")
        self.assertEqual(issue.pr_base_branch, "main")
        self.assertEqual(issue.pr_head_repo, "o/r")
        self.assertEqual(issue.pr_state, "open")

    def test_issue_carries_repo_default_branch(self):
        issue = self.n.normalize(issue_event(), event="issues")
        self.assertIsNotNone(issue)
        self.assertEqual(issue.kind, "issue")
        self.assertEqual(issue.repo_hint, "o/r")
        self.assertEqual(issue.default_branch, "development")

    def test_issue_without_default_branch_is_none(self):
        p = issue_event()
        p["repository"].pop("default_branch")
        issue = self.n.normalize(p, event="issues")
        self.assertIsNotNone(issue)
        self.assertIsNone(issue.default_branch)

    def test_event_inferred_from_headers(self):
        issue = self.n.normalize(
            issue_comment(), headers={"X-GitHub-Event": "issue_comment"}
        )
        self.assertIsNotNone(issue)

    def test_unknown_event_ignored(self):
        self.assertIsNone(self.n.normalize(issue_comment(), event="push"))


if __name__ == "__main__":
    unittest.main()
