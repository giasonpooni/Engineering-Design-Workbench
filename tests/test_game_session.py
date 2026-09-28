"""Actual CIW Session integration with clearly labelled native-execution doubles."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ciw import game_trace as c
from ciw import game_workflow as g
from ciw.control_contracts import load
from ciw.operations.runner import seal
from test_game_trace import fixture


class FixtureBinding:
    """Only the separate native qualification executes Godot."""
    def __init__(self, fail=False):
        self.calls = 0
        self.fail = fail
        self.identity = {"provider": "ciw.game.godot-courier", "execution_mode": "unit_test_double"}

    def runtime_identity(self):
        return deepcopy(self.identity)

    def invoke(self, scenario, parameters):
        from ciw.adapters.protocol import AdapterRefusal
        self.calls += 1
        if self.fail:
            raise AdapterRefusal("fixture_failure", "deliberate test double failure")
        return fixture(parameters["diagnostic_fault"], parameters["nonce"], scenario)


class GameSessionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.binding = FixtureBinding()

    def tearDown(self):
        self.tmp.cleanup()

    def baseline(self):
        return g.run_case(g.courier_scenario(), self.binding, self.root / "baseline")

    def test_existing_session_and_record_envelopes(self):
        from ciw.session import Session
        session, source = self.baseline()
        self.assertIsInstance(session, Session)
        self.assertEqual(len(session.executions), 2)
        self.assertEqual(len(session.results), 2)
        self.assertEqual(self.binding.calls, 1)
        self.assertEqual(source["runtime"]["execution_mode"], "unit_test_double")
        self.assertTrue(all(r["verification_id"] is None for r in session.results.values()))
        self.assertTrue(all(r["verification_status"] == "not_verified" for r in session.results.values()))

    def test_provider_free_reopening(self):
        session, _ = self.baseline()
        with patch("subprocess.Popen", side_effect=AssertionError("Unexpected execution")), patch.object(FixtureBinding, "invoke", side_effect=AssertionError("Unexpected provider")):
            reopened = g.open_saved(self.root / "baseline/workspace.json", self.root / "reopened")
            report = g.inspect(self.root / "baseline/workspace.json")
        self.assertEqual(reopened.results, session.results)
        self.assertEqual(reopened.executions, session.executions)
        self.assertEqual(len(report["executions"]), 2)

    def test_reproduction_preserves_original_history(self):
        baseline, source = self.baseline()
        original = (self.root / "baseline/workspace.json").read_bytes()
        repeated, candidate = g.extend_case(self.root / "baseline/workspace.json", self.binding, self.root / "repeat",
            source_execution_id=source["execution_id"], reproduce=True)
        self.assertEqual((self.root / "baseline/workspace.json").read_bytes(), original)
        self.assertEqual(len(repeated.executions), 5)
        for key in baseline.results:
            self.assertEqual(repeated.results[key], baseline.results[key])
        self.assertNotEqual(candidate["execution_id"], source["execution_id"])
        self.assertNotEqual(candidate["data"]["request"]["nonce"], source["data"]["request"]["nonce"])
        self.assertEqual(list(repeated.results.values())[-1]["data"]["status"], "PASS")

    def test_fault_candidate_is_successful_capture_with_failed_check(self):
        _, source = self.baseline()
        session, _ = g.extend_case(self.root / "baseline/workspace.json", self.binding, self.root / "bad",
            source_execution_id=source["execution_id"], reproduce=False, fault="early-knowledge")
        self.assertTrue(all(e["status"] == "completed" for e in session.executions.values()))
        self.assertEqual(list(session.results.values())[-1]["data"]["first_divergence_tick"], 1)
        self.assertEqual(list(session.results.values())[-2]["data"]["status"], "FAIL")

    def test_incomplete_capture_is_not_pass(self):
        _, source = self.baseline()
        session, _ = g.extend_case(self.root / "baseline/workspace.json", self.binding, self.root / "drop",
            source_execution_id=source["execution_id"], reproduce=False, fault="drop-sample")
        self.assertEqual(list(session.results.values())[-1]["data"]["status"], "INDETERMINATE")

    def test_failed_runtime_retains_refusal_without_result(self):
        with self.assertRaises(ValueError):
            g.run_case(g.courier_scenario(), FixtureBinding(fail=True), self.root / "refused")
        session = g.open_saved(self.root / "refused/workspace.json", self.root / "refused-open")
        self.assertEqual(len(session.executions), 1)
        self.assertEqual(len(session.results), 0)
        self.assertIsNone(next(iter(session.executions.values()))["result_id"])

    def test_existing_output_is_not_overwritten(self):
        self.baseline()
        before = (self.root / "baseline/workspace.json").read_bytes()
        with self.assertRaises(FileExistsError): self.baseline()
        self.assertEqual((self.root / "baseline/workspace.json").read_bytes(), before)
        self.assertEqual(self.binding.calls, 1)

    def test_wrong_reproduction_binding_does_not_execute(self):
        _, source = self.baseline()
        different = FixtureBinding(); different.identity["changed"] = True
        with self.assertRaises(ValueError):
            g.extend_case(self.root / "baseline/workspace.json", different, self.root / "wrong",
                source_execution_id=source["execution_id"], reproduce=True)
        self.assertEqual(different.calls, 0)

    def test_reproduce_original_fault_not_silently_corrected(self):
        session, source = g.run_case(g.courier_scenario(), self.binding, self.root / "fault", fault="duplicate-reward")
        repeated, result = g.extend_case(self.root / "fault/workspace.json", self.binding, self.root / "reproduced-fault",
            source_execution_id=source["execution_id"], reproduce=True)
        self.assertEqual(result["parameters"]["diagnostic_fault"], "duplicate-reward")
        self.assertEqual(list(repeated.results.values())[-2]["data"]["status"], "FAIL")
        self.assertEqual(list(repeated.results.values())[-1]["data"]["status"], "PASS")

    def test_resealed_false_check_is_refused(self):
        session, _ = self.baseline()
        result = next(r for r in session.results.values() if r["operation_id"] == g.AUDIT_OP)
        altered = deepcopy(result)
        altered["data"]["status"] = "FAIL"
        altered.pop("record_digest")
        session.results[result["result_id"]] = seal(altered)
        with self.assertRaises(ValueError): g.validate_session(session)

    def test_missing_dependency_refused(self):
        session, source = self.baseline()
        session.results.pop(source["result_id"])
        with self.assertRaises(ValueError): g.validate_session(session)

    def test_observations_export_uses_capture_not_audit_execution(self):
        session, source = self.baseline()
        path = self.root / "observations.json"
        self.assertEqual(g.main(["observations", str(self.root / "baseline/workspace.json"), "--execution-id", source["execution_id"], "--output", str(path)]), 0)
        stream = load(path)
        self.assertTrue(all(v["identity"]["execution_id"] == source["execution_id"] for v in stream["observations"]))
        self.assertEqual(len(session.executions), 2)

    def test_catalog_never_binds_runtime(self):
        with patch.object(g, "GodotCourierBinding", side_effect=AssertionError("Binding is forbidden")):
            self.assertEqual(g.main(["catalog"]), 0)

    def test_example_command_is_create_only(self):
        path = self.root / "scenario.json"
        self.assertEqual(g.main(["example", "--output", str(path)]), 0)
        self.assertEqual(load(path), g.courier_scenario())
        self.assertEqual(g.main(["example", "--output", str(path)]), 1)

    def test_scenario_copy_not_mutated(self):
        scenario = g.courier_scenario(); before = deepcopy(scenario)
        g.run_case(scenario, self.binding, self.root / "copy")
        self.assertEqual(scenario, before)

    def test_native_binding_requires_expected_digest_before_launch(self):
        fake = self.root / "not-godot"
        fake.write_bytes(b"not an executable")
        with patch("subprocess.Popen", side_effect=AssertionError("Unexpected process")), self.assertRaises(ValueError):
            g.GodotCourierBinding(fake, self.root, expected_sha256="sha256:" + "0" * 64)

    def test_native_binding_snapshots_scripts_and_detects_binary_drift(self):
        exe = self.root / "binary"; exe.write_bytes(b"operator-selected-fixture")
        for name in ("courier.gd", "recorder.gd"):
            (self.root / name).write_text("extends RefCounted\n", encoding="utf-8")
        binding = g.GodotCourierBinding(exe, self.root, expected_sha256=g.file_sha(exe))
        original = binding.scripts["courier.gd"]
        (self.root / "courier.gd").write_text("changed source", encoding="utf-8")
        self.assertEqual(binding.scripts["courier.gd"], original)
        exe.write_bytes(b"changed executable")
        with self.assertRaises(ValueError): binding.runtime_identity()

    def test_original_scientific_session_still_works(self):
        from ciw.instruments import make_demo_run
        from ciw.session import Session
        original = Session(make_demo_run(), self.root / "scientific")
        before = deepcopy(original.run)
        self.baseline()
        reply = original.handle({"protocol_version": 1, "request_id": "scientific-regression", "type": "operation.execute",
            "payload": {"operation_id": "statistics.v1", "parameters": {"channel": "q"}}})
        self.assertNotEqual(reply["type"], "error")
        self.assertEqual(original.run, before)
        self.assertEqual(len(original.results), 1)


if __name__ == "__main__":
    unittest.main()
