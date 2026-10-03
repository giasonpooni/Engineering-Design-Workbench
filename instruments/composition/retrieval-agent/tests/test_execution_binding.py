from copy import deepcopy
import sys
import types

import pytest

from conftest import sampled_jacobian
from schematics import quadratic_drag, Status, run
from schematics import io
from schematics.adapters.jspt import call_jacobian_at
from schematics.adapters.covariance import call_first_order_covariance
from schematics.adapters.montecarlo import call_monte_carlo_covariance
from schematics.annotate import observer_next_step
from schematics.eligibility import _written_A, decide
from schematics.ir import Node, NodeKind, EdgeKind
from schematics.validate import SchematicError


def replace_attrs(sch, node_id, **changes):
    node = sch.node(node_id)
    sch.replace(Node(node.id, node.kind, {**deepcopy(dict(node.attrs)), **changes}))


def test_adapter_record_binds_actual_call_and_survives_json_replay():
    sch = sampled_jacobian(quadratic_drag(with_digest=True))
    cert = _written_A(sch, "f")
    assert cert is not None
    binding = cert.get("binding")
    assert binding["call_inputs"] == {"model_ref": "jspt.reference.quadratic_drag", "x_star": [1.0], "parameters": {"c": 0.5}}
    assert binding["provenance"]["authentication"] == "not_authenticated"
    assert binding["provenance"]["kernel_revision_status"] == "declared_pin_not_verified"
    assert len({binding["execution_id"], binding["declaration_id"], binding["result_id"]}) == 3
    assert _written_A(io.loads(io.dumps(sch)), "f") is not None
    assert [d.status for d in decide(sch) if d.tool == "lyapunov.evaluate"] == [Status.ELIGIBLE]
    assert "no further declared gap" in observer_next_step(sch)


def test_repeated_calls_keep_declaration_but_get_distinct_execution_records():
    sch = sampled_jacobian(quadratic_drag())
    first = deepcopy(sch.node("cert:jspt:f").get("binding"))
    sampled_jacobian(sch)
    second = sch.node("cert:jspt:f").get("binding")
    assert first["declaration_id"] == second["declaration_id"]
    assert first["execution_id"] != second["execution_id"]
    assert first["result_id"] != second["result_id"]


@pytest.mark.parametrize("changes", [
    {"x_star": [2.0]}, {"c": 0.7}, {"model_ref": "jspt.reference.affine2"},
    {"units": "mm"}, {"chart": "other"}, {"frame": {"id": "different"}},
    {"input_axes": ["new-axis"]}, {"parameters": {"gain": 3}}, {"class": "unknown"},
])
def test_changed_model_or_declared_context_invalidates_old_record(changes):
    sch = sampled_jacobian(quadratic_drag(with_digest=True))
    replace_attrs(sch, "f", **changes)
    assert _written_A(sch, "f") is None
    assert "not yet sampled" in observer_next_step(sch)
    assert all(d.status is Status.NOT_ELIGIBLE for d in decide(sch) if d.tool in {
        "lyapunov.evaluate", "jspt.first_order_covariance", "jspt.local_structure"})


def test_changed_wired_port_units_and_order_invalidate_record():
    sch = sampled_jacobian(quadratic_drag())
    replace_attrs(sch, "x", units="mm/s")
    assert _written_A(sch, "f") is None
    sch = sampled_jacobian(quadratic_drag())
    sch.edges[:2] = list(reversed(sch.edges[:2]))
    assert _written_A(sch, "f") is None


@pytest.mark.parametrize("field,value", [
    ("fixture", None), ("fixture", 0), ("fixture", True), ("tool", "foreign"),
    ("owner", "rci"), ("pin", "foreign@revision"), ("A", [[99.0]]),
    ("model_ref", "foreign"), ("binding", None),
])
def test_tampered_certificate_cannot_open_downstream_eligibility(field, value):
    sch = sampled_jacobian(quadratic_drag())
    replace_attrs(sch, "cert:jspt:f", **{field: value})
    assert _written_A(sch, "f") is None


def test_legacy_annotation_is_readable_but_not_authoritative():
    sch = quadratic_drag(with_digest=True)
    sch.add(Node("cert:jspt:f", NodeKind.CERTIFICATE, {"owner": "jspt", "result": "SAMPLED", "A": [[-1.0]], "fixture": False}))
    sch.connect(EdgeKind.LINEARIZES, "cert:jspt:f", "f")
    again = io.loads(io.dumps(sch))
    assert again.node("cert:jspt:f").get("A") == [[-1.0]]
    assert _written_A(again, "f") is None
    assert "not yet sampled" in observer_next_step(again)


def test_missing_provenance_or_wrong_declaration_id_fail_closed():
    for field, value in [("provenance", {}), ("declaration_id", "sha256:wrong"), ("execution_id", "")]:
        sch = sampled_jacobian(quadratic_drag())
        binding = deepcopy(sch.node("cert:jspt:f").get("binding"))
        binding[field] = value
        replace_attrs(sch, "cert:jspt:f", binding=binding)
        assert _written_A(sch, "f") is None


def test_multiple_current_records_require_explicit_resolution():
    sch = sampled_jacobian(quadratic_drag())
    cert = sch.node("cert:jspt:f")
    sch.add(Node("cert:other", NodeKind.CERTIFICATE, deepcopy(dict(cert.attrs))))
    sch.connect(EdgeKind.LINEARIZES, "cert:other", "f")
    assert _written_A(sch, "f") is None


def test_failed_rerun_cannot_leave_previous_or_alternate_record_eligible(monkeypatch):
    sch = sampled_jacobian(quadratic_drag())
    cert = sch.node("cert:jspt:f")
    sch.add(Node("cert:old", NodeKind.CERTIFICATE, deepcopy(dict(cert.attrs))))
    sch.connect(EdgeKind.LINEARIZES, "cert:old", "f")
    monkeypatch.setitem(sys.modules, "sensitivity", None)
    assert call_jacobian_at(sch, "f").result is Status.NOT_CHECKED
    assert _written_A(sch, "f") is None


def test_derived_rank_or_new_covariance_does_not_change_jacobian_binding():
    sch = sampled_jacobian(quadratic_drag())
    replace_attrs(sch, "f", rank=1, invisible_dim=0, sigma_x=[[0.04]])
    assert _written_A(sch, "f") is not None


@pytest.mark.parametrize("value", [True, "1", float("nan"), float("inf"), 1j])
def test_malformed_kernel_matrix_is_a_bounded_refusal(monkeypatch, value):
    fake = types.ModuleType("sensitivity")
    fake.DifferentiableModel = lambda **kwargs: object()
    fake.jacobian_at = lambda model, point: types.SimpleNamespace(matrix=[[value]])
    monkeypatch.setitem(sys.modules, "sensitivity", fake)
    sch = quadratic_drag()
    assert call_jacobian_at(sch, "f").result is Status.REFUSED
    assert _written_A(sch, "f") is None


@pytest.mark.parametrize("sigma", [[["bad"]], [[True]], [[float("nan")]], [[float("inf")]], [1], [[1], [2, 3]], [], "bad"])
def test_malformed_covariance_has_bounded_refusals_in_both_adapters(sigma):
    sch = sampled_jacobian(quadratic_drag())
    replace_attrs(sch, "f", sigma_x=sigma)
    assert call_first_order_covariance(sch, "f").result is Status.REFUSED
    assert call_monte_carlo_covariance(sch, "f").result is Status.REFUSED
    assert sch.node("cert:jspt.cov:f").get("result") == "REFUSED"


@pytest.mark.parametrize("payload", [
    {"schema": "alien@99"}, {"meta": {"schema": "alien@99"}},
    {"schema": "alien@99", "meta": {"schema": "NsObservabilitySchematic@0.1"}},
    {"schema": "NsObservabilitySchematic@0.1", "meta": {"schema": "alien@99"}},
    {"schema": None}, {"meta": None}, [],
])
def test_unknown_conflicting_or_malformed_schema_is_rejected(payload):
    with pytest.raises(SchematicError):
        io.from_dict(payload)


def test_legacy_missing_schema_remains_readable():
    assert io.from_dict({"nodes": [], "edges": []}).nodes == {}


def test_direct_adapter_cannot_bypass_unknown_class_gate(monkeypatch):
    fake = types.ModuleType("sensitivity")
    fake.DifferentiableModel = lambda **kwargs: pytest.fail("unknown class reached kernel")
    monkeypatch.setitem(sys.modules, "sensitivity", fake)
    sch = quadratic_drag()
    replace_attrs(sch, "f", **{"class": "unknown"})
    assert call_jacobian_at(sch, "f").result is Status.REFUSED
    assert _written_A(sch, "f") is None


@pytest.mark.parametrize("via_run", [False, True])
def test_invalid_covariance_rerun_preserves_previous_numeric_evidence(monkeypatch, via_run):
    sch = sampled_jacobian(quadratic_drag())
    replace_attrs(sch, "f", sigma_x=[[0.04]])
    fake = types.ModuleType("sensitivity")
    fake.first_order_covariance = lambda A, sigma: [[0.04]]
    monkeypatch.setitem(sys.modules, "sensitivity", fake)
    assert call_first_order_covariance(sch, "f").result is Status.SAMPLED
    replace_attrs(sch, "f", sigma_x=[[True]])
    if via_run:
        run(sch)
    else:
        assert call_first_order_covariance(sch, "f").result is Status.REFUSED
    current = sch.node("cert:jspt.cov:f")
    assert current.get("result") == Status.REFUSED.value
    assert current.get("historical_sample")["sigma_x"] == [[0.04]]
    assert current.get("historical_sample")["sigma_y"] == [[0.04]]


@pytest.mark.parametrize("value", [True, "1", 1j, float("nan")])
def test_invalid_covariance_kernel_output_is_not_coerced_to_real(monkeypatch, value):
    sch = sampled_jacobian(quadratic_drag())
    replace_attrs(sch, "f", sigma_x=[[0.04]])
    fake = types.ModuleType("sensitivity")
    fake.first_order_covariance = lambda A, sigma: [[value]]
    monkeypatch.setitem(sys.modules, "sensitivity", fake)
    assert call_first_order_covariance(sch, "f").result is Status.REFUSED
