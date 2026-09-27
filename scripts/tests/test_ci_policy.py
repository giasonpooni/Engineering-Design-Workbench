"""Regressions for lost release coverage, stacked PRs and overbroad CI skipping."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("ci_policy", Path(__file__).resolve().parents[1] / "check_ci_policy.py")
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


def workflow(qualification=True):
    push = {"branches": ["main"], "tags": ["**"]}
    pull = {}
    if qualification:
        push["paths-ignore"] = list(policy.DOCS_ONLY)
        pull["paths-ignore"] = list(policy.DOCS_ONLY)
    return {"on": {"push": push, "pull_request": pull, "workflow_dispatch": ""},
            "concurrency": {"group": policy.GROUP, "cancel-in-progress": "true"}}


class PolicyTests(unittest.TestCase):
    def check(self, value, qualification=True):
        return policy.check_workflow("example.yml", value, qualification=qualification)

    def test_core_and_qualification_policies_are_accepted(self):
        for qualification in (False, True):
            with self.subTest(qualification=qualification):
                self.assertEqual(self.check(workflow(qualification), qualification), [])

    def test_core_cannot_skip_documentation_changes(self):
        self.assertTrue(self.check(workflow(), False))

    def test_tag_push_coverage_is_required(self):
        value = workflow()
        del value["on"]["push"]["tags"]
        self.assertTrue(self.check(value))

    def test_feature_push_duplication_is_rejected(self):
        value = workflow()
        del value["on"]["push"]["branches"]
        self.assertTrue(self.check(value))

    def test_stacked_pr_targets_cannot_be_filtered(self):
        value = workflow()
        value["on"]["pull_request"]["branches"] = ["main"]
        self.assertTrue(self.check(value))

    def test_code_and_future_documentation_fixtures_cannot_be_ignored(self):
        for pattern in ("src/**", "tests/**", "docs/**", "**/*.md"):
            value = workflow()
            value["on"]["pull_request"]["paths-ignore"].append(pattern)
            with self.subTest(pattern=pattern):
                self.assertTrue(self.check(value))

    def test_both_push_and_pr_filters_are_checked(self):
        value = workflow()
        value["on"]["push"]["paths-ignore"] = ["docs/**"]
        self.assertTrue(self.check(value))

    def test_manual_qualification_remains_available(self):
        value = workflow()
        del value["on"]["workflow_dispatch"]
        self.assertTrue(self.check(value))

    def test_manual_dispatch_does_not_require_inputs(self):
        value = workflow()
        value["on"]["workflow_dispatch"] = {"inputs": {"pin": {"required": "true"}}}
        self.assertTrue(self.check(value))

    def test_non_pr_runs_cannot_cancel_each_other(self):
        value = workflow()
        value["concurrency"]["group"] = "${{ github.workflow }}-${{ github.ref }}"
        self.assertTrue(self.check(value))

    def test_check_does_not_mutate_input(self):
        value = workflow()
        before = deepcopy(value)
        self.check(value)
        self.assertEqual(value, before)


if __name__ == "__main__":
    unittest.main()
