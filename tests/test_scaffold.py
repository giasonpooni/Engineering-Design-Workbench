import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ScaffoldContractTests(unittest.TestCase):
    def test_manifest_declares_a_planned_bounded_project(self) -> None:
        payload = json.loads((ROOT / "portfolio-project.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["schema"], "portfolio-project-v1")
        self.assertEqual(payload["project"], "Translation-Surface-Dynamics-Explorer")
        self.assertEqual(payload["status"], "planned")
        self.assertGreaterEqual(len(payload["required_evidence"]), 5)
        self.assertTrue(set(payload["required_evidence"]).isdisjoint(payload["does_not_own"]))

    def test_readme_does_not_present_scaffold_as_implemented(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
        self.assertIn("status: planned", readme)
        self.assertIn("does not yet claim", readme)


if __name__ == "__main__":
    unittest.main()
