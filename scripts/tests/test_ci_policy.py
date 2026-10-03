"""Regressions for lost release coverage, stacked PRs and overbroad CI skipping."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

import yaml

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

    def test_cantera_direct_worker_uses_shared_event_policy_with_its_existing_paths(self):
        path = Path(__file__).resolve().parents[2] / ".github/workflows/cantera-worker.yml"
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        events = value["on"]
        # This standalone direct-worker gate retains its positive path scope.
        # Strip only those paths before applying the shared event/concurrency
        # rules, so feature pushes and main-only PR targets remain regressions.
        push_paths = events["push"].pop("paths")
        pull_paths = events["pull_request"].pop("paths")
        self.assertEqual(push_paths, pull_paths)
        self.assertIn("runtimes/cantera-reaction/**", push_paths)
        self.assertIn("scripts/provision_cantera_python.ps1", push_paths)
        self.assertIn("tests/test_reaction_cantera_worker.py", push_paths)
        self.assertIn("src/ciw/reaction_contract.py", push_paths)
        self.assertIn("src/ciw/native_interop_contract.py", push_paths)
        self.assertIn("src/ciw/native-interop-runtimes.json", push_paths)
        self.assertIn("pyproject.toml", push_paths)
        self.assertIn(".github/workflows/cantera-worker.yml", push_paths)
        self.assertEqual(policy.check_workflow(path.name, value, qualification=False), [])


    def test_candidate_workflows_match_the_release_evidence_policy(self):
        import json
        root = Path(__file__).resolve().parents[2]
        release = json.loads((root / "release/qualification-policy.json").read_text(encoding="utf-8"))
        self.assertEqual(set(policy.CANDIDATE_WORKFLOWS),
                         {Path(item["path"]).name for item in release["required_workflows"]})
        self.assertEqual(policy.CANDIDATE_AUXILIARY, ("release-evidence.yml",))

    def test_selected_shared_workflows_require_the_exact_candidate_branch(self):
        for name in policy.CANDIDATE_WORKFLOWS:
            if name not in (*policy.ALWAYS, *policy.QUALIFICATION):
                continue
            qualification = name in policy.QUALIFICATION
            value = workflow(qualification)
            with self.subTest(name=name):
                self.assertTrue(policy.check_workflow(name, value, qualification=qualification))
                value["on"]["push"]["branches"].append(policy.CANDIDATE_BRANCH)
                self.assertEqual(policy.check_workflow(name, value, qualification=qualification), [])

    def test_unselected_workflows_reject_candidate_pushes(self):
        value = workflow()
        value["on"]["push"]["branches"].append(policy.CANDIDATE_BRANCH)
        self.assertTrue(self.check(value))

    def test_candidate_route_rejects_missing_main_and_extra_or_wildcard_branches(self):
        branches = [
            ["main"], [policy.CANDIDATE_BRANCH],
            ["main", policy.CANDIDATE_BRANCH, "feature/unreviewed"],
            ["main", "*"], ["main", "**"], ["main", "codex/**"],
            ["main", policy.CANDIDATE_BRANCH + "*"],
        ]
        for name in (*policy.CANDIDATE_WORKFLOWS, *policy.CANDIDATE_AUXILIARY):
            for selected in branches:
                value = workflow(name in policy.QUALIFICATION)
                value["on"]["push"]["branches"] = selected
                with self.subTest(name=name, branches=selected):
                    self.assertTrue(policy.check_candidate_push(name, value))
                    if name in (*policy.ALWAYS, *policy.QUALIFICATION):
                        self.assertTrue(policy.check_workflow(
                            name, value, qualification=name in policy.QUALIFICATION))

    def test_checked_in_candidate_workflows_use_exact_push_scope(self):
        root = Path(__file__).resolve().parents[2]
        for name in (*policy.CANDIDATE_WORKFLOWS, *policy.CANDIDATE_AUXILIARY):
            value = yaml.load((root / ".github/workflows" / name).read_text(encoding="utf-8"),
                              Loader=yaml.BaseLoader)
            with self.subTest(name=name):
                self.assertEqual(policy.check_candidate_push(name, value), [])

    def test_pyyaml_pin_lives_only_in_the_dev_extra(self):
        import tomllib
        root = Path(__file__).resolve().parents[2]
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        pins = [item for item in project["project"]["optional-dependencies"]["dev"]
                if item.startswith("PyYAML==")]
        self.assertEqual(pins, ["PyYAML==6.0.3"])
        workflow = (root / ".github/workflows/workflow-contracts.yml").read_text(encoding="utf-8")
        self.assertIn('python -m pip install -e ".[dev]"', workflow)
        self.assertNotIn("PyYAML==", workflow)


if __name__ == "__main__":
    unittest.main()
