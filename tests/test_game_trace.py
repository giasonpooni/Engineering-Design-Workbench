"""Contract tests use explicit synthetic tables, not native-engine evidence."""
from copy import deepcopy
import json
import unittest

from ciw import game_trace as c
from ciw.game_workflow import courier_scenario
from ciw.control_contracts import bytes_ref
from ciw.core.identities import content_identity


def fixture(fault="none", nonce="unit-capture", scenario=None):
    scenario = deepcopy(scenario or courier_scenario())
    # Hand-written reference table: knowledge, mission, reward, cargo.
    rows = [[0, 0, 0, 0], [0, 1, 0, 1], [0, 1, 0, 1], [1, 2, 0, 0], [1, 2, 0, 0],
            [1, 2, 0, 0], [1, 3, 1, 0], [1, 3, 1, 0], [1, 3, 1, 0]]
    if fault == "early-knowledge":
        rows[1][0] = rows[2][0] = 1
    if fault == "duplicate-reward":
        rows[7][2] = rows[8][2] = 2
    samples = [{"tick": tick, "channel": name, "value": values[i]} for tick, values in enumerate(rows)
               for i, name in enumerate(("knowledge", "mission", "reward", "cargo"))]
    if fault == "drop-sample":
        samples = [s for s in samples if (s["tick"], s["channel"]) != (3, "knowledge")]
    kinds = ["order.issued", "order.received", "order.acknowledged", "mission.completed", "report.received"]
    actors = ["commander", "recipient", "recipient", "courier", "commander"]
    ticks = [1, 3, 3, 6, 6]
    events = [{"id": f"e{i}", "tick": ticks[i], "kind": kind, "actor_id": actors[i], "target_ids": [],
               "causes": [] if i == 0 else [f"e{i-1}"], "payload": {}} for i, kind in enumerate(kinds)]
    trace = {"schema": c.TRACE, "request_nonce": nonce, "scenario_digest": content_identity(scenario),
             "engine": "godot", "engine_version": "unit-test-double-not-native", "samples": samples, "events": events,
             "dropped_samples": int(fault == "drop-sample"), "dropped_events": 0, "complete": fault != "drop-sample"}
    raw = json.dumps(trace)
    return {"schema": c.CAPTURE, "request": {"scenario": scenario, "scenario_digest": content_identity(scenario),
            "nonce": nonce, "diagnostic_fault": fault}, "trace_utf8": raw, "trace_sha256": bytes_ref(raw.encode())}


def edit_trace(capture, edit):
    value = deepcopy(capture)
    trace = json.loads(value["trace_utf8"])
    edit(trace)
    value["trace_utf8"] = json.dumps(trace)
    value["trace_sha256"] = bytes_ref(value["trace_utf8"].encode())
    return value


class GameTraceTests(unittest.TestCase):
    def setUp(self):
        self.capture = fixture()

    def reject(self, edit):
        with self.assertRaises((ValueError, TypeError, KeyError)):
            c.validate_capture(edit_trace(self.capture, edit))

    def test_fixture_valid(self):
        c.validate_capture(self.capture)

    def test_unknown_scenario_schema(self):
        s = courier_scenario(); s["schema"] = "ciw.game-scenario.v2"
        with self.assertRaises(ValueError): c.validate_scenario(s)

    def test_false_historical_classification(self):
        s = courier_scenario(); s["source_class"] = "documented_history"
        with self.assertRaises(ValueError): c.validate_scenario(s)

    def test_zero_tick_duration(self):
        s = courier_scenario(); s["clock"]["tick_seconds"] = 0
        with self.assertRaises(ValueError): c.validate_scenario(s)

    def test_boolean_tick_count(self):
        s = courier_scenario(); s["clock"]["duration_ticks"] = True
        with self.assertRaises(ValueError): c.validate_scenario(s)

    def test_duplicate_entity(self):
        s = courier_scenario(); s["entities"].append("recipient")
        with self.assertRaises(ValueError): c.validate_scenario(s)

    def test_unknown_perspective(self):
        s = courier_scenario(); s["channels"]["knowledge"]["perspective"] = "omniscient-new-actor"
        with self.assertRaises(ValueError): c.validate_scenario(s)

    def test_duplicate_quantity_identity(self):
        s = courier_scenario(); s["channels"]["alias"] = deepcopy(s["channels"]["knowledge"])
        with self.assertRaises(ValueError): c.validate_scenario(s)

    def test_unknown_rule(self):
        s = courier_scenario(); s["checks"][0]["kind"] = "eval_python"
        with self.assertRaises(ValueError): c.validate_scenario(s)

    def test_duplicate_rule_id(self):
        s = courier_scenario(); s["checks"].append(deepcopy(s["checks"][0]))
        with self.assertRaises(ValueError): c.validate_scenario(s)

    def test_reversed_rule_bounds(self):
        s = courier_scenario(); s["checks"][1]["minimum"] = 10
        with self.assertRaises(ValueError): c.validate_scenario(s)

    def test_nonce_binding(self):
        self.reject(lambda t: t.update(request_nonce="another-attempt"))

    def test_scenario_binding(self):
        self.reject(lambda t: t.update(scenario_digest="sha256:" + "0" * 64))

    def test_duplicate_sample(self):
        self.reject(lambda t: t["samples"].insert(1, deepcopy(t["samples"][0])))

    def test_unknown_channel(self):
        self.reject(lambda t: t["samples"][0].update(channel="secret"))

    def test_backwards_samples(self):
        self.reject(lambda t: t["samples"].reverse())

    def test_boolean_value(self):
        self.reject(lambda t: t["samples"][0].update(value=True))

    def test_nonfinite_value(self):
        self.reject(lambda t: t["samples"][0].update(value=float("nan")))

    def test_unaccounted_sample_loss(self):
        self.reject(lambda t: t["samples"].pop())

    def test_false_complete(self):
        value = fixture("drop-sample")
        value = edit_trace(value, lambda t: t.update(complete=True))
        with self.assertRaises(ValueError): c.validate_capture(value)

    def test_missing_value_is_not_zero(self):
        value = edit_trace(self.capture, lambda t: (t.update(complete=False), t["samples"][0].update(value=None)))
        c.validate_capture(value)
        self.assertIsNone(c.observations(value, "execution-1")["observations"][0]["value"])
        self.assertEqual(c.audit(value, "execution-1")["status"], "INDETERMINATE")

    def test_future_causal_reference(self):
        self.reject(lambda t: t["events"][0].update(causes=["e4"]))

    def test_self_causal_reference(self):
        self.reject(lambda t: t["events"][0].update(causes=["e0"]))

    def test_unknown_causal_reference(self):
        self.reject(lambda t: t["events"][1].update(causes=["missing"]))

    def test_duplicate_event(self):
        self.reject(lambda t: t["events"][1].update(id="e0"))

    def test_unknown_event_actor(self):
        self.reject(lambda t: t["events"][0].update(actor_id="undeclared"))

    def test_unknown_event_target(self):
        self.reject(lambda t: t["events"][0].update(target_ids=["undeclared"]))

    def test_backwards_event_ticks(self):
        self.reject(lambda t: t["events"][2].update(tick=0))

    def test_trace_text_digest(self):
        value = deepcopy(self.capture); value["trace_utf8"] += " "
        with self.assertRaises(ValueError): c.validate_capture(value)

    def test_duplicate_json_keys(self):
        value = deepcopy(self.capture)
        value["trace_utf8"] = value["trace_utf8"].replace('"complete": true', '"complete": true, "complete": false')
        value["trace_sha256"] = bytes_ref(value["trace_utf8"].encode())
        with self.assertRaises(ValueError): c.validate_capture(value)

    def test_unknown_fields(self):
        self.reject(lambda t: t.update(executable="evil"))

    def test_projection_preserves_identity_and_semantics(self):
        values = c.observations(self.capture, "actual-capture-execution")["observations"]
        self.assertEqual(len(values), 36)
        self.assertTrue(all(v["identity"]["execution_id"] == "actual-capture-execution" for v in values))
        self.assertTrue(all(v["provenance"]["semantics"] == "simulated" for v in values))
        self.assertTrue(all(v["provenance"]["sources"] == [self.capture["trace_sha256"]] for v in values))
        self.assertEqual(values[-1]["clock"]["time_s"], 2.0)
        self.assertTrue(all(v["uncertainty"] is None for v in values))

    def test_baseline_rules_pass(self):
        report = c.audit(self.capture, "e1")
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(len(report["checks"]), 5)
        self.assertIsNone(report["verification_id"])

    def test_early_knowledge_is_retained_and_detected(self):
        value = fixture("early-knowledge")
        c.validate_capture(value)
        report = c.audit(value, "e1")
        self.assertEqual(report["checks"][0]["status"], "FAIL")
        self.assertEqual(report["status"], "FAIL")

    def test_duplicate_reward_is_retained_and_detected(self):
        value = fixture("duplicate-reward")
        c.validate_capture(value)
        self.assertEqual(c.audit(value, "e1")["checks"][1]["status"], "FAIL")

    def test_dropped_capture_never_passes(self):
        self.assertEqual(c.audit(fixture("drop-sample"), "e1")["status"], "INDETERMINATE")

    def test_empty_check_suite_is_not_a_pass(self):
        s = courier_scenario(); s["checks"] = []
        self.assertEqual(c.audit(fixture(scenario=s), "e1")["status"], "INDETERMINATE")

    def test_missing_required_event(self):
        value = edit_trace(self.capture, lambda t: t["events"][-1].update(kind="other.event"))
        self.assertEqual(c.audit(value, "e1")["checks"][-1]["status"], "FAIL")

    def test_new_occurrence_same_values(self):
        result = c.comparison(self.capture, fixture(nonce="new-occurrence"), "e1", "e2", atol=0)
        self.assertEqual(result["status"], "PASS")
        self.assertIsNone(result["first_divergence_tick"])

    def test_first_knowledge_divergence(self):
        result = c.comparison(fixture("early-knowledge"), self.capture, "e2", "e1", atol=0)
        self.assertEqual((result["status"], result["first_divergence_tick"]), ("FAIL", 1))

    def test_first_reward_divergence(self):
        result = c.comparison(fixture("duplicate-reward"), self.capture, "e2", "e1", atol=0)
        self.assertEqual((result["status"], result["first_divergence_tick"]), ("FAIL", 7))

    def test_incomplete_comparison(self):
        result = c.comparison(fixture("drop-sample"), self.capture, "e2", "e1", atol=0)
        self.assertEqual(result["status"], "INDETERMINATE")
        self.assertEqual(result["channels"], {})
        self.assertIsNone(result["first_divergence_tick"])

    def test_project_mismatch(self):
        s = courier_scenario(); s["project_id"] = "other-game"
        self.assertEqual(c.comparison(fixture(scenario=s), self.capture, "e2", "e1", atol=0)["status"], "INDETERMINATE")

    def test_unit_mismatch(self):
        s = courier_scenario(); s["channels"]["cargo"]["unit"] = "kg"
        self.assertEqual(c.comparison(fixture(scenario=s), self.capture, "e2", "e1", atol=0)["status"], "INDETERMINATE")

    def test_clock_mismatch(self):
        s = courier_scenario(); s["clock"]["id"] = "wall-clock"
        self.assertEqual(c.comparison(fixture(scenario=s), self.capture, "e2", "e1", atol=0)["status"], "INDETERMINATE")

    def test_perspective_mismatch(self):
        s = courier_scenario(); s["channels"]["knowledge"]["perspective"] = "world"
        self.assertEqual(c.comparison(fixture(scenario=s), self.capture, "e2", "e1", atol=0)["status"], "INDETERMINATE")

    def test_event_ids_are_capture_local(self):
        def rename(t):
            for e in t["events"]:
                e["id"] = "new-" + e["id"]
                e["causes"] = ["new-" + p for p in e["causes"]]
        value = edit_trace(self.capture, rename)
        self.assertEqual(c.comparison(value, self.capture, "e2", "e1", atol=0)["status"], "PASS")

    def test_causal_structure_difference(self):
        value = edit_trace(self.capture, lambda t: t["events"][3].update(causes=["e0"]))
        result = c.comparison(value, self.capture, "e2", "e1", atol=0)
        self.assertEqual((result["status"], result["first_divergence_tick"]), ("FAIL", 6))

    def test_negative_tolerance_refused(self):
        with self.assertRaises(ValueError): c.comparison(self.capture, self.capture, "e1", "e2", atol=-1)

    def test_snapshot_does_not_alias_capture(self):
        original = deepcopy(self.capture)
        stream = c.observations(self.capture, "e1")
        stream["observations"][0]["value"] = 100
        self.assertEqual(self.capture, original)


if __name__ == "__main__":
    unittest.main()
