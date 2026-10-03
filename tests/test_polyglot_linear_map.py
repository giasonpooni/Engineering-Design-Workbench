"""Contract/reference tests. Protocol doubles below are not native qualification."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from ciw import polyglot_linear_map as p
from ciw.native_interop_contract import affine_reference
from ciw.telemetry import canonical, digest


def case():
    return {"schema": p.CASE_SCHEMA, "model": {"owner": "fixture", "kind": "rectangular-tangent", "digest": "sha256:" + "a"*64},
            "frame": "quantity-coordinates", "inputs": [
                {"id": "length", "unit": "m", "scale": 0.001}, {"id": "angle", "unit": "radian", "scale": 0.1}],
            "outputs": [{"id": "response", "unit": "m", "scale": 0.01}],
            "baseline": [2.0], "jacobian_row_major": [3.0, -2.0], "delta": [0.002, 0.05],
            "claim_scope": p.CLAIM, "covariance": "not_propagated", "may_authorize": False}


def protocol_double(c):
    """Exercise projection only, explicitly bypassing the separately tested native reader."""
    source = p.compile_case(c, "cpp")
    d = "sha256:" + "b"*64
    bundle = {"bundle_digest": d, "runtimes": {"scr": "protocol-double"},
              "verification": {"verification_id": d}, "steps": [{
                  "result_id": d, "numerical_result_id": d, "execution_id": "execution-" + "c"*32,
                  "result": {"data": {"output": affine_reference(source["payload"])}}}]}
    return {"schema": p.RUN_SCHEMA, "case": deepcopy(c), "native": bundle}, canonical(source)


class LinearMapTests(unittest.TestCase):
    def test_cpp_and_julia_select_same_declared_math(self):
        for provider in ("cpp", "julia"):
            with self.subTest(provider=provider):
                c = case(); source = p.compile_case(c, provider)
                output = affine_reference(source["payload"])
                self.assertEqual(source["provider"], provider)
                self.assertEqual(source["profile"], "affine-binary64.v1")
                self.assertAlmostEqual(output["model_output"][0] * .01, 1.906, places=14)
                self.assertEqual(source["experiment_id"], "linear-map:" + digest(c))

    def test_rectangular_map_row_major(self):
        c = case(); c["outputs"].append({"id": "other", "unit": "m", "scale": 2.0})
        c["baseline"].append(-1.0); c["jacobian_row_major"] += [-4.0, 6.0]
        s = p.compile_case(c, "cpp"); values = affine_reference(s["payload"])["model_output"]
        self.assertAlmostEqual(values[1] * 2, -.708)

    def test_dimensions_not_square(self):
        c = case(); self.assertEqual(p.compile_case(c, "cpp")["payload"]["rows"], 1)
        self.assertEqual(p.compile_case(c, "cpp")["payload"]["columns"], 2)

    def test_metadata_changes_request_binding_not_coefficients(self):
        first = p.compile_case(case(), "cpp")
        for field, value in (("frame", "other-frame"), ("model", {"owner": "fixture", "kind": "other", "digest": "sha256:"+"c"*64})):
            c = case(); c[field] = value; changed = p.compile_case(c, "cpp")
            self.assertEqual(first["payload"], changed["payload"])
            self.assertNotEqual(first["experiment_id"], changed["experiment_id"])

    def test_scale_changes_preserve_units_and_physical_values(self):
        c = case(); c["inputs"][0]["scale"] = .02; c["outputs"][0]["scale"] = .3
        values = affine_reference(p.compile_case(c, "julia")["payload"])
        self.assertAlmostEqual(values["model_output"][0] * .3, 1.906)
        self.assertEqual(c["inputs"][0]["unit"], "m")

    def test_validate_detaches(self):
        c = case(); validated = p.validate_case(c); validated["inputs"][0]["scale"] = 1
        self.assertEqual(c["inputs"][0]["scale"], .001)

    def test_rejects_bad_numbers(self):
        for value in (True, "1", None, float("nan"), float("inf"), 10**400):
            c = case(); c["delta"][0] = value
            with self.subTest(value=repr(value)), self.assertRaises(ValueError): p.compile_case(c, "cpp")

    def test_rejects_bad_scales(self):
        for value in (0, -1, True, 1e-101, 1e101):
            c = case(); c["inputs"][0]["scale"] = value
            with self.subTest(value=value), self.assertRaises(ValueError): p.compile_case(c, "cpp")

    def test_native_bounds_are_not_relaxed(self):
        c = case(); c["delta"][0] = 1e9
        with self.assertRaises(ValueError): p.compile_case(c, "cpp")

    def test_normalization_underflow_refused(self):
        c = case(); c["jacobian_row_major"][0] = 1e-300
        c["inputs"][0]["scale"] = 1e-100
        with self.assertRaises(ValueError): p.compile_case(c, "cpp")

    def test_normalization_overflow_refused(self):
        c = case(); c["jacobian_row_major"][0] = 1e300
        c["inputs"][0]["scale"] = 1e100
        with self.assertRaises(ValueError): p.compile_case(c, "cpp")

    def test_unknown_provider_has_no_fallback(self):
        for provider in ("python", "rust", "", "shell"):
            with self.subTest(provider=provider), self.assertRaises(ValueError): p.compile_case(case(), provider)

    def test_claims_fail_closed(self):
        for field, value in (("may_authorize", True), ("may_authorize", 0), ("covariance", "propagated"), ("claim_scope", "physical-validation"), ("schema", "v2")):
            c = case(); c[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): p.compile_case(c, "cpp")

    def test_unknown_or_missing_fields(self):
        c = case(); c["command"] = "run"
        with self.assertRaises(ValueError): p.validate_case(c)
        c = case(); del c["frame"]
        with self.assertRaises(ValueError): p.validate_case(c)

    def test_shape_duplicate_and_dimension_refusals(self):
        for mutate in (lambda c: c["delta"].pop(), lambda c: c["jacobian_row_major"].append(1),
                       lambda c: c["inputs"][1].update(id="length"), lambda c: c.update(inputs=[])):
            c = case(); mutate(c)
            with self.assertRaises(ValueError): p.validate_case(c)

    def test_full_digest_required(self):
        c = case(); c["model"]["digest"] = "sha256:abcd"
        with self.assertRaises(ValueError): p.validate_case(c)

    def test_strict_bytes_parser(self):
        raw = canonical(case())
        self.assertEqual(p.read_case(raw), case())
        with self.assertRaises(ValueError): p.read_case(raw.replace(b'"baseline":', b'"frame":"duplicate","baseline":'))
        with self.assertRaises(ValueError): p.read_case(b" " * (p.MAX_CASE_BYTES + 1))

    def test_compilation_launches_nothing(self):
        with patch.object(p.NativeInteropWorkflow, "create_session", side_effect=AssertionError("launched")):
            p.compile_case(case(), "cpp")

    def test_missing_native_runtime_is_not_a_pass(self):
        with patch.object(p.NativeInteropWorkflow, "create_session", side_effect=ValueError("runtime unavailable")) as call:
            with self.assertRaisesRegex(ValueError, "runtime unavailable"):
                p.create_run(case(), provider="julia", bindings={"runtime": "missing"})
            self.assertEqual(call.call_count, 1)

    def test_protocol_double_projection_and_exact_byte_envelope(self):
        run, raw = protocol_double(case())
        with patch.object(p.NativeInteropWorkflow, "_validate", return_value=raw), patch.object(p.NativeInteropWorkflow, "_adapters", side_effect=AssertionError("launched")):
            envelope = p.export_view(run)
        self.assertEqual(envelope["sha256"], p.byte_digest(envelope["payload"].encode()))
        view = json.loads(envelope["payload"])
        self.assertAlmostEqual(view["outputs"][0]["value"], 1.906)
        self.assertEqual(view["covariance"], "not_propagated")
        self.assertIs(view["may_authorize"], False)

    def test_protocol_double_cannot_rebind_a_different_case(self):
        run, raw = protocol_double(case()); run["case"]["frame"] = "changed"
        with patch.object(p.NativeInteropWorkflow, "_validate", return_value=raw):
            with self.assertRaisesRegex(ValueError, "complete model case"): p.inspect_run(run)

    def test_unmocked_reader_rejects_the_protocol_double(self):
        run, _ = protocol_double(case())
        with self.assertRaises(ValueError): p.inspect_run(run)


if __name__ == "__main__": unittest.main()
