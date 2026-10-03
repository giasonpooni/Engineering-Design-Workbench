"""Composition/reference tests use labelled protocol doubles, never native evidence."""
from contextlib import contextmanager
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import uuid

import numpy as np
from ciw import polyglot_uncertainty as u
from ciw import native_interop_contract as nc
from ciw.telemetry import canonical, digest


def fixture(j=(1., -1., 1., 1.), matrix=((4., 3.), (3., 9.))):
    case = {"schema": "notation.linear-map.v1", "model": {"owner": "test", "kind": "synthetic", "digest": "sha256:"+"a"*64},
        "frame": "local", "inputs": [{"id": "x", "unit": "m", "scale": 1.}, {"id": "y", "unit": "m", "scale": 1.}],
        "outputs": [{"id": "difference", "unit": "m", "scale": 1.}, {"id": "sum", "unit": "m", "scale": 1.}],
        "baseline": [0., 0.], "delta": [2., 3.], "jacobian_row_major": list(j),
        "claim_scope": "first-order-mean-response-only", "covariance": "not_propagated", "may_authorize": False}
    return u.problem(case, u.bind_covariance(case, [list(r) for r in matrix], provider="test"))


@contextmanager
def protocol():
    """Local orchestration double; the real native reader rejects its records."""
    def create(self, raw, bindings):
        source = nc.source(raw)
        identity = "execution-"+uuid.uuid4().hex
        d = digest({"source": source, "execution": identity})
        return {"raw": raw.decode(), "runtimes": {"scr": "protocol-double-not-native"}, "bundle_digest": d,
            "verification": {"verification_id": d, "reproduction": {"execution_id": "execution-"+uuid.uuid4().hex}},
            "steps": [{"execution_id": identity, "result_id": d, "numerical_result_id": d,
                       "result": {"data": {"output": nc.affine_reference(source["payload"])}}}]}
    with patch.object(u.NativeInteropWorkflow, "create_session", create), \
         patch.object(u.NativeInteropWorkflow, "_validate", lambda self, b: b["raw"].encode()):
        yield


class UncertaintyTests(unittest.TestCase):
    def test_full_correlated_covariance(self):
        for provider in ("cpp", "julia"):
            with self.subTest(provider=provider), protocol():
                run = u.execute(fixture(), provider=provider, bindings={})
                np.testing.assert_array_equal(u.inspect(run)["matrix"], [[7., -5.], [-5., 19.]])
                self.assertEqual(len(run["stages"]), 5)
                self.assertEqual(run["output_covariance"]["provenance"]["source_covariance_ids"],
                                 [run["problem"]["input_covariance"]["covariance_id"]])

    def test_common_mode_cancels_without_jitter(self):
        p = fixture(matrix=((4.,4.), (4.,4.)))
        with protocol():
            a = u.inspect(u.execute(p, provider="cpp", bindings={}))
        np.testing.assert_array_equal(a["matrix"], [[0.,0.],[0.,16.]])

    def test_zero_covariance_stays_zero(self):
        with protocol():
            a = u.inspect(u.execute(fixture(matrix=((0.,0.),(0.,0.))), provider="julia", bindings={}))
        self.assertEqual(a["matrix"], [[0.,0.],[0.,0.]])

    def test_normalization_is_not_unit_conversion(self):
        p=fixture(); c=p["case"]; c["inputs"][0]["scale"]=.1; c["outputs"][1]["scale"]=10.
        p=u.problem(c,u.bind_covariance(c,[[4.,3.],[3.,9.]],provider="test"))
        with protocol():
            a=u.inspect(u.execute(p,provider="cpp",bindings={}))
        np.testing.assert_allclose(a["matrix"],[[7.,-5.],[-5.,19.]],rtol=1e-14,atol=0)
        self.assertEqual(a["units"],["m","m"])

    def test_rectangular_covariance(self):
        p=fixture(); c=p["case"]; c["outputs"]=c["outputs"][:1]; c["baseline"]=[0.]; c["jacobian_row_major"]=[1.,-1.]
        p=u.problem(c,u.bind_covariance(c,[[4.,3.],[3.,9.]],provider="test"))
        with protocol():
            run=u.execute(p,provider="cpp",bindings={})
            self.assertEqual(u.inspect(run)["matrix"],[[7.]])
            self.assertEqual(len(run["stages"]),4)

    def test_bad_covariances(self):
        for c in (((-1.,0.),(0.,1.)), ((0.,1e-15),(1e-15,1.)), ((1.,2.),(2.,1.)), ((True,0.),(0.,1.)), ((1.,0.),(1.,1.))):
            with self.subTest(c=c),self.assertRaises(ValueError): fixture(matrix=c)

    def test_axis_unit_frame_and_reference_mismatch(self):
        for key,value in (("quantity_ids",["y","x"]),("units",["mm","m"]),("frame","other"),("reference_values",[0,0])):
            p=fixture(); c=p["input_covariance"]; c[key]=value
            from ciw.core.covariance import covariance_identity
            c["covariance_id"]=covariance_identity(c)
            with self.subTest(key=key),self.assertRaises(ValueError): u.validate_problem(p)

    def test_no_execution_on_invalid_case(self):
        p=fixture(); p["may_authorize"]=True
        with patch.object(u.NativeInteropWorkflow,"create_session",side_effect=AssertionError("started")),self.assertRaises(ValueError):
            u.execute(p,provider="cpp",bindings={})

    def test_normalized_bounds_are_preserved(self):
        p=fixture(matrix=((1e8,0.),(0.,1e8)))
        with patch.object(u.NativeInteropWorkflow,"create_session",side_effect=AssertionError("started")),self.assertRaises(ValueError):
            u.execute(p,provider="cpp",bindings={})

    def test_reference_detects_erased_variance_and_wrong_values(self):
        for matrix in ([[0.,-5.],[-5.,19.]],[[8.,-5.],[-5.,19.]]):
            with self.subTest(matrix=matrix),self.assertRaises(ValueError):u.reference_check(fixture(),matrix)

    def test_reopen_does_not_execute_reference_or_provider(self):
        with protocol():
            run=u.execute(fixture(),provider="cpp",bindings={})
            saved=json.loads(canonical(run))
            with patch.object(u,"reference_check",side_effect=AssertionError("reference rerun")), \
                 patch.object(u.NativeInteropWorkflow,"create_session",side_effect=AssertionError("native rerun")):
                self.assertEqual(u.inspect(saved)["matrix"],[[7.,-5.],[-5.,19.]])
                e=u.export_view(saved); self.assertEqual(e["sha256"],u.byte_digest(e["payload"].encode()))

    def test_rehashed_output_edit_is_refused(self):
        with protocol():
            run=u.execute(fixture(),provider="cpp",bindings={})
            run["output_covariance"]["matrix"][0][0]=8.
            run["calculation_id"]=digest({k:v for k,v in run.items() if k!="calculation_id"})
            with self.assertRaises(ValueError):u.inspect(run)

    def test_reordered_stage_is_refused(self):
        with protocol():
            run=u.execute(fixture(),provider="cpp",bindings={})
            run["stages"][1],run["stages"][2]=run["stages"][2],run["stages"][1]
            run["calculation_id"]=digest({k:v for k,v in run.items() if k!="calculation_id"})
            with self.assertRaises(ValueError):u.inspect(run)

    def test_original_mean_schema_stays_mean_only(self):
        p=fixture()
        with protocol():
            run=u.execute(p,provider="cpp",bindings={}); view=json.loads(u.export_view(run)["payload"])
        mean=json.loads(view["mean"]["payload"])
        self.assertEqual(mean["covariance"],"not_propagated")
        self.assertEqual(view["scope"],u.SCOPE)
        self.assertIs(view["may_authorize"],False)

    def test_real_reader_rejects_protocol_double(self):
        with protocol():run=u.execute(fixture(),provider="cpp",bindings={})
        with self.assertRaises(ValueError):u.inspect(run)

    def test_replay_has_new_execution_and_verification_identities(self):
        with protocol(),patch.object(u.NativeInteropWorkflow,"_adapters",return_value=None):
            original=u.execute(fixture(),provider="cpp",bindings={})
            result=u.replay(original,bindings={})
            self.assertNotEqual(original["calculation_id"],result["run"]["calculation_id"])
            self.assertNotEqual(original["check"]["verification_id"],result["run"]["check"]["verification_id"])
            self.assertIs(result["receipt"]["bit_identity_claimed"],False)

    def test_domain_export(self):
        p=fixture()
        export={"schema":"notation.domain-uncertainty-inputs.v1","case":p["case"],"covariance_matrix":[[4.,3.],[3.,9.]],
                "source_evidence_ids":[],"source_covariance_ids":[],"assumptions":["synthetic"]}
        q=u.from_domain(export)
        self.assertEqual(q["input_covariance"]["matrix"],export["covariance_matrix"])
        q["input_covariance"]["matrix"][0][0]=100
        self.assertEqual(export["covariance_matrix"][0][0],4.)

if __name__=="__main__":unittest.main()
