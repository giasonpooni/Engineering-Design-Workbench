import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProjectContractTests(unittest.TestCase):
    def test_manifest_declares_implemented_bounded_profile(self):
        payload = json.loads((ROOT / "portfolio-project.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "portfolio-project-v1")
        self.assertEqual(payload["status"], "implemented-bounded-reference")
        self.assertEqual(payload["operation_id"], "tsde.square-tiled-flow.v1")
        self.assertEqual(payload["claim_scope"], "square-tiled-rational-translation-flow-prefix")
        self.assertGreaterEqual(len(payload["required_evidence"]), 5)

    def test_readme_names_delivered_scope_and_explicit_partial_statuses(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for text in ("implemented bounded reference", "stopped_at_vertex", "event_budget_exhausted", "does not establish"):
            self.assertIn(text, readme)


if __name__ == "__main__":
    unittest.main()
