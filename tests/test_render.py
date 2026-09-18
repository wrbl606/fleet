import unittest

from fleetctl.errors import RenderError
from fleetctl.models import Issue
from fleetctl.render import build_context, referenced_vars, render


def issue():
    return Issue(
        source="jira",
        key="ENG-1",
        summary="Fix the thing",
        description="details",
        issue_type="Bug",
        labels=["agent", "backend"],
        project="ENG",
        component="web",
        reporter="Ada",
        url="https://x/browse/ENG-1",
    )


class RenderTest(unittest.TestCase):
    def setUp(self):
        self.ctx = build_context(issue(), repo="acme/engine", platform="linux")

    def test_substitutes_dotted_paths(self):
        out = render("{{issue.key}}: {{issue.summary}} ({{source}})", self.ctx)
        self.assertEqual(out, "ENG-1: Fix the thing (jira)")

    def test_labels_joined(self):
        self.assertEqual(render("{{issue.labels}}", self.ctx), "agent, backend")

    def test_unknown_variable_raises_strict(self):
        with self.assertRaises(RenderError):
            render("{{issue.nope}}", self.ctx)

    def test_unknown_variable_left_in_non_strict(self):
        self.assertEqual(render("{{issue.nope}}", self.ctx, strict=False), "{{issue.nope}}")

    def test_referenced_vars(self):
        self.assertEqual(referenced_vars("a {{x.y}} b {{z}}"), {"x.y", "z"})

    def test_missing_component_becomes_empty(self):
        i = issue()
        i.component = None
        ctx = build_context(i)
        self.assertEqual(render("{{issue.component}}", ctx), "")


if __name__ == "__main__":
    unittest.main()
