# SPDX-License-Identifier: AGPL-3.0-or-later
"""Controller contracts use labelled fixtures; native qualification is separate."""
from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

from ciw import csr_microtools as m
from ciw.adapters.protocol import AdapterRefusal
from ciw.control_plane import CapabilityRegistry
from ciw.instruments import make_demo_run
from ciw.operations.runner import seal
from ciw.session import Session


def request(op=m.OPERATIONS[1]):
    value = {"arc_length": [0, 1, 2], "curvature": 0, "length_unit": "m", "frame": "fixture"}
    value.update({m.OPERATIONS[0]: {"initial_error": [.002, -.001]},
        m.OPERATIONS[1]: {"initial_bounds": [.002, .001], "tolerances": [.003, .001]},
        m.OPERATIONS[2]: {"covariance": [[4e-6, 1e-6], [1e-6, 1e-6]]}}[op])
    return value


def fixture_response(op, req):
    # Precomputed plane fixtures; not a production/reference solver or native evidence.
    values = {m.OPERATIONS[0]: [[.002, -.001], [.001, -.001], [0., -.001]],
        m.OPERATIONS[1]: [[.002, .001], [.003, .001], [.004, .001]],
        m.OPERATIONS[2]: [[[4e-6, 1e-6], [1e-6, 1e-6]],
            [[7e-6, 2e-6], [2e-6, 1e-6]], [[12e-6, 3e-6], [3e-6, 1e-6]]]}[op]
    check = None
    if op == m.OPERATIONS[1]:
        check = {"status": "FAIL", "sample_pass": [True, True, False],
                 "maximum_excess": [.004-.003, 0.]}
    return {"schema": m.SCHEMA, "operation_id": op, "request": deepcopy(req),
        "model": m.MODEL, "coordinate": "arc_length", "basis": ["lateral", "heading"],
        "units": ["m", "rad"], "scope": m.SCOPE,
        "transfer_matrices": [[[1.,0.],[0.,1.]], [[1.,1.],[0.,1.]], [[1.,2.],[0.,1.]]],
        "values": values, "tolerance_check": check, "verification_id": None,
        "verification_status": "not_verified"}


class FixtureAdapter:
    def __init__(self, transform=None):
        self.calls = 0
        self.transform = transform
        self.identity = {"module": m.MODULE, "fixture_only": True, "revision": "fixture-1"}

    def runtime_identity(self):
        return deepcopy(self.identity)

    def invoke(self, op, req):
        self.calls += 1
        result = fixture_response(op, req)
        if self.transform:
            self.transform(result)
        return result


def setup(tmp_path, adapter=None):
    adapter = adapter or FixtureAdapter()
    registry = CapabilityRegistry()
    m.register_csr(registry, adapter)
    source = tmp_path / "source.json"
    Session(make_demo_run(), tmp_path / "context").save_workspace(source)
    return source, registry, adapter


def execute(tmp_path, op=m.OPERATIONS[1], adapter=None):
    source, registry, adapter = setup(tmp_path, adapter)
    result = m.run(source, tmp_path / "result", registry, operation_id=op, request=request(op))
    return result, registry, adapter


@pytest.mark.parametrize("op", m.OPERATIONS)
def test_completed_recorded_bound_operation_and_offline_inspection(tmp_path, op, monkeypatch):
    result, registry, adapter = execute(tmp_path, op)
    assert result["status"] == "completed" and adapter.calls == 1
    artifact, execution = result["result"], result["execution"]
    assert artifact["operation_id"] == op and artifact["execution_id"] == execution["execution_id"]
    assert artifact["result_id"] != artifact["execution_id"]
    assert artifact["verification_status"] == "not_verified"
    assert artifact["parameters"]["recording_role"] == m.CONTEXT
    monkeypatch.setattr(adapter, "invoke", lambda *_: pytest.fail("inspection invoked provider"))
    saved = m.inspect(Path(result["workspace"]))
    assert saved["results"] == [artifact] and saved["executions"] == [execution]
    assert registry.catalog("geometry.surface_path")["operations"]


def test_replay_retains_original_ids_and_creates_new_occurrence(tmp_path):
    first, registry, adapter = execute(tmp_path)
    second = m.run(Path(first["workspace"]), tmp_path / "again", registry,
                   replay_result=first["result"]["result_id"])
    assert second["same_runtime_exact_data_equal"] is True
    assert second["result"]["execution_id"] != first["result"]["execution_id"]
    assert second["result"]["result_id"] != first["result"]["result_id"]
    saved = m.inspect(Path(second["workspace"]))
    assert first["result"] in saved["results"] and len(saved["results"]) == 2
    assert adapter.calls == 2


@pytest.mark.parametrize("change", ["runtime", "missing_result", "replacement_request"])
def test_replay_mismatch_does_not_create_output(tmp_path, change):
    first, registry, adapter = execute(tmp_path)
    kwargs = {"replay_result": first["result"]["result_id"]}
    if change == "runtime":
        adapter.identity["revision"] = "fixture-2"
    elif change == "missing_result":
        kwargs["replay_result"] = "result-does-not-exist"
    else:
        kwargs["request"] = request()
    with pytest.raises(ValueError):
        m.run(Path(first["workspace"]), tmp_path / "bad", registry, **kwargs)
    assert not (tmp_path / "bad").exists() and adapter.calls == 1


def test_no_overwrite_or_second_execution(tmp_path):
    first, registry, adapter = execute(tmp_path)
    before = Path(first["workspace"]).read_bytes()
    with pytest.raises(FileExistsError):
        m.run(Path(first["workspace"]), tmp_path / "result", registry,
              operation_id=m.OPERATIONS[1], request=request())
    assert Path(first["workspace"]).read_bytes() == before and adapter.calls == 1


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(scope="continuous_path_guarantee"),
    lambda d: d.update(verification_status="verified"),
    lambda d: d.update(verification_id="verification-invented"),
    lambda d: d.update(units=["mm", "rad"]),
    lambda d: d.update(coordinate="time"),
    lambda d: d.update(basis=["heading", "lateral"]),
    lambda d: d.update(values=[]),
    lambda d: d["request"].update(frame="somewhere_else"),
    lambda d: d["tolerance_check"].update(status="PASS"),
    lambda d: d["tolerance_check"].update(sample_pass=[1, 1, 0]),
    lambda d: d.update(joint_covariance=[]),
])
def test_invalid_provider_response_retains_refusal_without_result(tmp_path, mutation):
    result, _, adapter = execute(tmp_path, adapter=FixtureAdapter(mutation))
    assert result["status"] == "refused" and result["result"] is None
    saved = m.inspect(Path(result["workspace"]))
    assert saved["results"] == [] and len(saved["executions"]) == 1 and adapter.calls == 1


def test_declared_provider_failure_retained(tmp_path):
    class Refusing(FixtureAdapter):
        def invoke(self, *_):
            raise AdapterRefusal("NO_NATIVE_RESULT", "explicit fixture refusal")
    result, _, _ = execute(tmp_path, adapter=Refusing())
    assert result["status"] == "refused" and result["result"] is None
    assert result["execution"]["refusal"]["code"] == "NO_NATIVE_RESULT"


@pytest.mark.parametrize("changes", [{"arc_length": [0, True]}, {"curvature": "0"},
    {"arc_length": [0, 0]}, {"arc_length": [-1, 0]}, {"curvature": 1e-15},
    {"frame": " "}, {"initial_bounds": [-1, 0]}, {"tolerances": [True, 1]},
    {"extra": 42}, {"arc_length": []}, {"curvature": float("nan")}])
def test_invalid_request_does_not_execute_or_publish(tmp_path, changes):
    source, registry, adapter = setup(tmp_path)
    req = request(); req.update(changes)
    with pytest.raises(ValueError):
        m.run(source, tmp_path / "bad", registry, operation_id=m.OPERATIONS[1], request=req)
    assert not (tmp_path / "bad").exists() and adapter.calls == 0


def test_covariance_matrix_is_not_repaired():
    req = request(m.OPERATIONS[2]); req["covariance"] = [[1, 2], [2, 1]]
    with pytest.raises(ValueError):
        m.validate_request(m.OPERATIONS[2], req)


def test_saved_tampering_refused_even_when_outer_seals_are_updated(tmp_path):
    first, _, _ = execute(tmp_path)
    path = Path(first["workspace"])
    value = json.loads(path.read_text())
    result = value["results"][0]
    result["data"]["scope"] = "whole_path"
    value["results"][0] = seal({k:v for k,v in result.items() if k != "record_digest"})
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        m.inspect(path)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":1e-999}', b' '*65537],
                         ids=["duplicate", "nan", "underflow", "oversize"])
def test_bounded_strict_reader(tmp_path, raw):
    path = tmp_path / "request.json"; path.write_bytes(raw)
    with pytest.raises(ValueError):
        m._load(path, 65536)


def test_catalog_and_example_are_provider_free(capsys, monkeypatch):
    monkeypatch.setattr(m, "bind_csr", lambda *_a, **_k: pytest.fail("discovery bound provider"))
    assert m.main(["catalog"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["authorizes_execution"] is False and len(value["tools"]) == 3
    for op in m.OPERATIONS:
        assert m.main(["example", "--operation", op]) == 0
        m.validate_request(op, json.loads(capsys.readouterr().out))
    assert "geodesic_testbed.microtools" not in sys.modules


def test_same_registry_rejects_duplicate_binding():
    registry = CapabilityRegistry(); adapter = FixtureAdapter()
    m.register_csr(registry, adapter)
    with pytest.raises(ValueError):
        m.register_csr(registry, adapter)


def test_fixed_module_binding_only():
    adapter = FixtureAdapter(); adapter.identity["module"] = "unexpected.module"
    with pytest.raises(ValueError):
        m.register_csr(CapabilityRegistry(), adapter)


def test_operations_are_usable_in_existing_typed_graph(tmp_path):
    from ciw.control_plane import experiment, run_graph
    source, registry, adapter = setup(tmp_path)
    session = Session.from_workspace(source, tmp_path / "graph")
    session.operations = registry.operations
    graph = experiment("fixture-graph", model_id=m.MODEL, nodes=[
        {"node_id": f"node-{i}", "operation_id": op,
         "parameters": {"request": request(op), "recording_role": m.CONTEXT},
         "inputs": {}, "depends_on": []} for i, op in enumerate(m.OPERATIONS)])
    result = run_graph(session, graph, registry)
    assert result["status"] == "completed" and adapter.calls == 3
    assert len(session.results) == 3
    for contract in result["contracts"].values():
        assert contract["outputs"]["response"]["type"]["schema"] == m.SCHEMA
