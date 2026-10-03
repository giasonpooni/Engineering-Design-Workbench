from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("TSDE_INSTALLED_TEST") != "1":
    sys.path.insert(0, str(ROOT / "src"))

from translation_surface_dynamics import run, validate_request
from translation_surface_dynamics import flow


def request():
    return {"schema": flow.REQUEST_SCHEMA,
            "gluing": {"right": [1, 0, 2], "up": [2, 1, 0]},
            "start": {"tile": 0, "position": ["1/4", "1/3"]},
            "direction": ["1", "1/2"], "duration": "3", "max_events": 128}


class FlowTests(unittest.TestCase):
    def test_higher_genus_surface_has_singular_vertex_and_directed_events(self):
        result = run(request())
        topology = result["gluing_validation"]
        self.assertEqual((topology["tile_count"], topology["edge_count"], topology["vertex_count"]), (3, 6, 1))
        self.assertEqual((topology["euler_characteristic"], topology["genus"]), (-2, 2))
        self.assertEqual(topology["vertices"][0]["cone_angle_multiple_of_2pi"], 3)
        self.assertTrue(topology["vertices"][0]["singular"])
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["final_state"], {"tile": 1, "position": ["1/4", "5/6"], "pending_edges": [], "vertex_id": None})
        self.assertEqual([(e["time"], e["edge"], e["from_tile"], e["to_tile"]) for e in result["events"]],
                         [("3/4", "right", 0, 1), ("4/3", "up", 1, 1), ("7/4", "right", 1, 0), ("11/4", "right", 0, 1)])
        self.assertTrue(all(result["invariants"].values()))

    def test_torus_cover_agrees_with_analytic_unfolding_in_all_direction_quadrants(self):
        # Independent oracle: rectangle [0,3]x[0,1], with opposite sides identified.
        for direction in (("1", "1/2"), ("-1", "1/2"), ("1", "-1/2"), ("-1", "-1/2"), ("0", "2")):
            with self.subTest(direction=direction):
                value = request()
                value["gluing"] = {"right": [1, 2, 0], "up": [0, 1, 2]}
                value["direction"] = list(direction)
                value["duration"] = "2"
                result = run(value)
                x = (Fraction(1, 4) + 2 * Fraction(direction[0])) % 3
                y = (Fraction(1, 3) + 2 * Fraction(direction[1])) % 1
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["final_state"]["tile"], x.numerator // x.denominator)
                self.assertEqual([Fraction(v) for v in result["final_state"]["position"]], [x % 1, y])
                self.assertEqual(result["gluing_validation"]["genus"], 1)
                self.assertTrue(all(v["cone_angle_multiple_of_2pi"] == 1 for v in result["gluing_validation"]["vertices"]))

    def test_noncommuting_gluing_changes_sheet_not_only_wrapped_coordinates(self):
        value = request()
        higher_genus = run(value)
        value["gluing"] = {"right": [1, 2, 0], "up": [0, 1, 2]}
        cover = run(value)
        self.assertNotEqual(higher_genus["final_state"]["tile"], cover["final_state"]["tile"])
        self.assertNotEqual(higher_genus["request_digest"], cover["request_digest"])
        self.assertNotEqual(higher_genus["artifact_digest"], cover["artifact_digest"])

    def test_inverse_flow_restores_initial_state_and_reverses_gluing_events(self):
        value = request()
        forward = run(value)
        reverse = deepcopy(value)
        reverse["start"] = {key: forward["final_state"][key] for key in ("tile", "position")}
        reverse["direction"] = [str(-Fraction(v)) for v in value["direction"]]
        backward = run(reverse)
        self.assertEqual(backward["status"], "completed")
        self.assertEqual({key: backward["final_state"][key] for key in ("tile", "position")}, value["start"])
        opposite = {"right": "left", "left": "right", "up": "down", "down": "up"}
        for first, second in zip(forward["events"], reversed(backward["events"])):
            self.assertEqual(first["edge"], opposite[second["edge"]])
            self.assertEqual(first["from_tile"], second["to_tile"])
            self.assertEqual(first["to_tile"], second["from_tile"])
            self.assertEqual(first["from_position"], second["to_position"])
            self.assertEqual(Fraction(first["time"]) + Fraction(second["time"]), 3)

    def test_noninvolutive_left_and_down_use_actual_inverse_permutations(self):
        for horizontal in (True, False):
            value = request()
            value["gluing"] = {"right": [1, 2, 0] if horizontal else [0, 1, 2],
                                "up": [0, 1, 2] if horizontal else [1, 2, 0]}
            value["direction"] = ["-1", "0"] if horizontal else ["0", "-1"]
            value["duration"] = "1/2"
            result = run(value)
            self.assertEqual(result["events"][0]["to_tile"], 2)
            self.assertEqual(result["gluing_validation"]["left" if horizontal else "down"], [2, 0, 1])
            self.assertEqual(result["events"][0]["translation"], ["1", "0"] if horizontal else ["0", "1"])

    def test_vertex_hit_stops_on_regular_and_singular_vertices_even_at_endpoint(self):
        for gluing in ({"right": [0], "up": [0]}, request()["gluing"]):
            for duration in ("3/4", "2"):
                with self.subTest(gluing=gluing, duration=duration):
                    value = request()
                    value.update(gluing=gluing, direction=["1", "1"], duration=duration)
                    value["start"]["position"] = ["1/4", "1/4"]
                    result = run(value)
                    self.assertEqual(result["status"], "stopped_at_vertex")
                    self.assertEqual(result["elapsed"], "3/4")
                    self.assertEqual(result["events"], [])
                    self.assertEqual(result["final_state"]["pending_edges"], ["right", "up"])
                    self.assertIsNotNone(result["final_state"]["vertex_id"])
                    self.assertFalse(result["invariants"]["requested_duration_completed"])

    def test_rational_near_corner_is_not_merged_by_float_epsilon(self):
        value = request()
        value.update(gluing={"right": [0], "up": [0]}, duration="1",
                     direction=["1", "9007199254740992/9007199254740991"])
        value["start"]["position"] = ["1/4", "1/4"]
        result = run(value)
        self.assertEqual(result["status"], "completed")
        self.assertEqual([event["edge"] for event in result["events"]], ["up", "right"])
        separation = Fraction(result["events"][1]["time"]) - Fraction(result["events"][0]["time"])
        self.assertTrue(0 < separation < Fraction(1, 10**15))

    def test_event_budget_returns_prefix_before_omitted_transition(self):
        for budget, elapsed, remaining in ((0, "3/4", "9/4"), (1, "7/4", "5/4")):
            value = request()
            value.update(direction=["1", "0"], max_events=budget)
            result = run(value)
            self.assertEqual(result["status"], "event_budget_exhausted")
            self.assertEqual((result["elapsed"], result["remaining"]), (elapsed, remaining))
            self.assertEqual(len(result["events"]), budget)
            self.assertEqual(result["final_state"]["pending_edges"], ["right"])
            self.assertEqual(result["final_state"]["position"][0], "1")
            self.assertFalse(result["invariants"]["requested_duration_completed"])

    def test_zero_duration_and_no_crossing_need_no_event_budget(self):
        for duration in ("0", "1/2"):
            value = request()
            value.update(duration=duration, max_events=0)
            result = run(value)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["elapsed"], duration)
            self.assertEqual(result["events"], [])

    def test_edge_crossing_at_endpoint_is_processed_or_explicitly_budget_stopped(self):
        value = request()
        value.update(direction=["1", "0"], duration="3/4")
        result = run(value)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["final_state"]["position"][0], "0")
        self.assertEqual(result["final_state"]["tile"], 1)
        self.assertEqual(len(result["events"]), 1)
        value["max_events"] = 0
        refused = run(value)
        self.assertEqual(refused["status"], "event_budget_exhausted")
        self.assertEqual(refused["remaining"], "0")

    def test_runtime_guard_refuses_bit_growth_instead_of_rounding(self):
        with patch.object(flow, "ARITHMETIC_BITS", 2):
            with self.assertRaisesRegex(ValueError, "bit budget"):
                run(request())

    def test_request_and_artifact_digests_are_independently_recomputable(self):
        value = request()
        before = deepcopy(value)
        result = run(value)
        self.assertEqual(value, before)
        self.assertEqual(result, run(value))
        encode = lambda item: json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        self.assertEqual(result["request_digest"], "sha256:" + sha256(encode(value)).hexdigest())
        artifact = {key: child for key, child in result.items() if key != "artifact_digest"}
        self.assertEqual(result["artifact_digest"], "sha256:" + sha256(encode(artifact)).hexdigest())
        value["start"]["position"][0] = "1/3"
        self.assertEqual(result["request"], before)

    def test_refuses_malformed_permutations_and_disconnected_surfaces(self):
        invalid = [[], [0, 0, 2], [0, 1], [0, 1, 3], [0, True, 2], [0, 1.0, 2], "012"]
        for permutation in invalid:
            for key in ("right", "up"):
                with self.subTest(permutation=permutation, key=key):
                    value = request()
                    value["gluing"][key] = permutation
                    with self.assertRaises(ValueError):
                        validate_request(value)
        value = request()
        value["gluing"] = {"right": [0, 1], "up": [0, 1]}
        with self.assertRaisesRegex(ValueError, "connected"):
            run(value)

    def test_rejects_noncanonical_rationals_and_unsupported_inputs(self):
        for rational in ("1.0", "+1", "01", "-0", "2/4", "1/0", "1/-2", "0/3", "NaN", "1e-3", "1/1", str(2**64), 0.5, True):
            with self.subTest(rational=rational):
                value = request()
                value["start"]["position"][0] = rational
                with self.assertRaises(ValueError):
                    run(value)
        for field, invalid in (("duration", "-1"), ("duration", "1025"), ("max_events", 1025),
                               ("max_events", True), ("direction", ["0", "0"]), ("direction", ["1025", "0"])):
            value = request()
            value[field] = invalid
            with self.assertRaises(ValueError):
                run(value)
        for position in (["0", "1/2"], ["1", "1/2"], ["-1", "1/2"]):
            value = request()
            value["start"]["position"] = position
            with self.assertRaisesRegex(ValueError, "strictly inside"):
                run(value)
        for value in (None, [], True, {**request(), "extra": 1}):
            with self.assertRaises(ValueError):
                run(value)

    def test_maximum_connected_tile_count_and_event_limit(self):
        value = request()
        value["gluing"] = {"right": list(range(1, 32)) + [0], "up": list(range(32))}
        value.update(direction=["2", "0"], duration="1024", max_events=1024)
        result = run(value)
        self.assertEqual(result["gluing_validation"]["genus"], 1)
        self.assertEqual(len(result["events"]), 1024)
        self.assertEqual(result["status"], "event_budget_exhausted")
        self.assertLess(len(flow.canonical(result)), 1024 * 1024)
        value["gluing"] = {"right": list(range(1, 33)) + [0], "up": list(range(33))}
        with self.assertRaisesRegex(ValueError, "1..32"):
            run(value)


class CliTests(unittest.TestCase):
    def invoke(self, raw):
        environment = dict(os.environ)
        if os.environ.get("TSDE_INSTALLED_TEST") != "1":
            environment["PYTHONPATH"] = str(ROOT / "src")
        else:
            environment.pop("PYTHONPATH", None)
        return subprocess.run([sys.executable, "-m", "translation_surface_dynamics"],
                              input=raw, capture_output=True, env=environment, timeout=10)

    def test_real_cli_matches_api(self):
        value = request()
        completed = self.invoke(flow.canonical(value))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout), run(value))
        self.assertEqual(completed.stderr, b"")

    def test_cli_refuses_duplicate_nonfinite_oversized_and_malformed_json(self):
        for raw in (b"", b"null", b"{", b'{"schema":1,"schema":2}', b'{"value":NaN}', b" " * 32769, b"\xff"):
            with self.subTest(raw=raw[:40]):
                refused = self.invoke(raw)
                self.assertEqual(refused.returncode, 2)
                self.assertEqual(refused.stdout, b"")
                self.assertTrue(refused.stderr)


if __name__ == "__main__":
    unittest.main()
