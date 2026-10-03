"""Polymer evidence stays on NET Session, with explicit execution and audit identities.

These tests run the deterministic reference operations. They do not stand in for
factory trials, camera qualification, sensor calibration, or PLC commissioning.
"""
from copy import deepcopy
import json
import uuid

import pytest

from ciw import polymer_workflow as workflow
from ciw.adapters.protocol import AdapterRefusal
from ciw.agent_api import AgentHost, encode
from ciw.control_plane import experiment, plan_graph
from ciw.core.identities import validate_evidence_identity, validate_identity
from ciw.net import main as net_main
from ciw.operations.registry import default_registry
from ciw.operations.runner import check_seal, seal
from ciw.polymer_contract import AUTHORITY, MAX_BYTES, example_request
from ciw.session import Session


def _call(session, operation, parameters=None):
    response = session.handle({
        "protocol_version": 1, "request_id": uuid.uuid4().hex,
        "type": "operation.execute",
        "payload": {"operation_id": operation, "parameters": parameters or {}},
    })
    assert response["type"] == "response", response
    return response["payload"]


def _files(directory):
    return {str(path.relative_to(directory)): path.read_bytes()
            for path in directory.rglob("*") if path.is_file()}


def _workspace(directory):
    return json.loads((directory / "workspace.json").read_text(encoding="utf-8"))


def _write_workspace(directory, value):
    (directory / "workspace.json").write_text(
        json.dumps(value, allow_nan=False), encoding="utf-8")


@pytest.mark.parametrize("process", ["injection_molding", "extrusion_blow_molding"])
def test_cycle_runs_existing_session_operations_and_replays_with_fresh_occurrences(tmp_path, process):
    request = example_request(process)
    before = deepcopy(request)
    first_dir, replay_dir = tmp_path / "original", tmp_path / "replay"
    first = workflow.run(request, first_dir)
    assert request == before
    assert first["status"] == "PASS"
    assert first["identity"] == request["identity"]
    assert first["source_kind"] == "synthetic"
    assert first["authority"] == AUTHORITY
    assert first["fresh_execution"] is False
    assert first["fresh_numerical_verification"] is False
    assert first["assessment"]["process"] == process
    assert first["assessment"]["metrology"]["status"] == "NONCONFORMING"
    assert first["verification"]["report"]["status"] == "PASS"

    retained = _workspace(first_dir)
    validate_evidence_identity(retained["run"])
    assert retained["run"]["metadata"]["polymer_request"] == request
    assert retained["workspace_version"] == 2
    assert len(retained["executions"]) == len(retained["results"]) == 4
    assert {item["operation_id"] for item in retained["executions"]} == workflow.OPERATIONS
    executions = {item["execution_id"]: item for item in retained["executions"]}
    for result in retained["results"]:
        check_seal(result)
        check_seal(executions[result["execution_id"]])
        validate_identity(result["execution_id"], "execution")
        validate_identity(result["result_id"], "result")
        assert executions[result["execution_id"]]["status"] == "completed"
        assert executions[result["execution_id"]]["result_id"] == result["result_id"]
        assert result["evidence_id"] == first["evidence_id"]
        assert result["verification_id"] is None
        assert result["verification_status"] == "not_verified"
        assert result["data"]["authority"] == AUTHORITY
    assert {item["role"] for item in retained["results"]} == {"backend", "verification"}

    before_inspect = _files(first_dir)
    assert workflow.inspect(first_dir) == first
    assert _files(first_dir) == before_inspect
    replayed = workflow.replay(first_dir, replay_dir)
    assert replayed["status"] == "PASS"
    assert replayed["evidence_id"] == first["evidence_id"]
    assert replayed["replay_source_evidence_id"] == first["evidence_id"]
    assert replayed["assessment"] == first["assessment"]
    assert replayed["simulation"] == first["simulation"]
    assert replayed["copilot"]["context"] == first["copilot"]["context"]
    assert replayed["verification"]["report"] == first["verification"]["report"]
    for field in ("execution_id", "result_id"):
        assert {item[field] for item in first["occurrences"]}.isdisjoint(
            {item[field] for item in replayed["occurrences"]})
    assert (replayed["verification"]["verification_id"]
            != first["verification"]["verification_id"])
    assert _files(first_dir) == before_inspect


def test_default_registry_does_not_grant_polymer_execution():
    default = default_registry()
    assert not workflow.OPERATIONS.intersection(
        item["operation_id"] for item in default.describe())
    for operation in workflow.OPERATIONS:
        with pytest.raises(AdapterRefusal):
            default.get(operation)
    explicit = workflow.registry()
    assert all(explicit.get(operation).operation_id == operation
               for operation in workflow.OPERATIONS)


def test_reopen_and_inspect_never_call_models_or_other_executable_providers(tmp_path, monkeypatch):
    from ciw import polymer_copilot, polymer_metrology, polymer_models, polymer_verification

    directory = tmp_path / "retained"
    original = workflow.run(example_request(), directory)
    before = _files(directory)

    def forbidden(*args, **kwargs):
        raise AssertionError("Retained inspection dispatched a polymer provider")

    for name in ("_assess", "_copilot", "_simulate", "_verify", "runtime_identity"):
        monkeypatch.setattr(workflow, name, forbidden)
    monkeypatch.setattr(polymer_metrology, "assess_metrology", forbidden)
    for name in ("engineering_estimate", "control_proposal", "simulate_control"):
        monkeypatch.setattr(polymer_models, name, forbidden)
    monkeypatch.setattr(polymer_copilot, "build_context", forbidden)
    monkeypatch.setattr(polymer_verification, "verify", forbidden)

    restored = Session.from_workspace(directory / "workspace.json", tmp_path / "restored")
    assert len(restored.executions) == len(restored.results) == 4
    assert workflow.inspect(directory) == original
    assert _files(directory) == before


def test_fresh_verification_has_distinct_identity_and_leaves_retained_bundle_unchanged(tmp_path):
    directory = tmp_path / "retained"
    original = workflow.run(example_request(), directory)
    before = _files(directory)
    first, second = workflow.verify_retained(directory), workflow.verify_retained(directory)
    assert first["status"] == second["status"] == "PASS"
    assert first["fresh_numerical_verification"] is True
    assert first["authority"] == second["authority"] == AUTHORITY
    ids = {first["verification_id"], second["verification_id"],
           original["verification"]["verification_id"]}
    assert len(ids) == 3
    for identity in ids:
        validate_identity(identity, "verification")
    assessment_occurrence = next(item for item in original["occurrences"]
                                 if item["operation_id"] == workflow.ASSESS)
    assert first["assessment_result_id"] == assessment_occurrence["result_id"]
    assert first["assessment_execution_id"] == assessment_occurrence["execution_id"]
    assert first["source_evidence_id"] == original["evidence_id"]
    assert first["report"] == second["report"] == original["verification"]["report"]
    assert _files(directory) == before


@pytest.mark.parametrize("field", ["request_ref", "assessment_ref"])
def test_resealed_verification_report_remains_bound_to_exact_evidence(tmp_path, field):
    directory = tmp_path / "retained"
    workflow.run(example_request(), directory)
    value = _workspace(directory)
    verification = next(item for item in value["results"] if item["operation_id"] == workflow.VERIFY)
    verification["data"]["report"][field] = "sha256:" + "0" * 64
    seal(verification["data"]["report"])
    seal(verification)
    _write_workspace(directory, value)
    before = _files(directory)
    with pytest.raises(ValueError, match="exact request and assessment"):
        workflow.inspect(directory)
    assert _files(directory) == before


def test_refused_assessment_retains_attempt_without_dispatching_descendants(tmp_path, monkeypatch):
    from ciw import polymer_copilot, polymer_metrology, polymer_models, polymer_verification

    def refuse(*args, **kwargs):
        raise ValueError("retained metrology is inconsistent")

    def forbidden(*args, **kwargs):
        raise AssertionError("A dependent operation ran after refused assessment")

    monkeypatch.setattr(polymer_metrology, "assess_metrology", refuse)
    monkeypatch.setattr(polymer_copilot, "build_context", forbidden)
    monkeypatch.setattr(polymer_models, "simulate_control", forbidden)
    monkeypatch.setattr(polymer_verification, "verify", forbidden)
    directory = tmp_path / "refused"
    outcome = workflow.run(example_request(), directory)
    assert outcome["status"] == "REFUSE"
    assert len(outcome["occurrences"]) == 1
    attempt = outcome["occurrences"][0]
    assert attempt["operation_id"] == workflow.ASSESS
    assert attempt["status"] == "refused"
    assert attempt["result_id"] is None
    assert attempt["refusal"]["message"] == "retained metrology is inconsistent"
    assert _workspace(directory)["results"] == []
    assert workflow.inspect(directory) == outcome
    assert workflow.verify_retained(directory) == outcome


@pytest.mark.parametrize("operation", [workflow.COPILOT, workflow.VERIFY])
@pytest.mark.parametrize("challenge", ["malformed", "other_cycle"])
def test_invalid_dependent_attempt_is_retained_as_refusal_with_no_result(tmp_path, operation, challenge):
    request = example_request()
    source_session = Session(workflow.make_source(request), tmp_path / "source", operations=workflow.registry())
    assessed = _call(source_session, workflow.ASSESS)
    assert assessed["status"] == "completed", assessed
    assessment = assessed["result"]
    other = deepcopy(request)
    other["identity"]["cycle_id"] = "synthetic.other-cycle"
    target = Session(workflow.make_source(other), tmp_path / "target", operations=workflow.registry())
    parameters = {"assessment": None if challenge == "malformed" else assessment}
    refused = _call(target, operation, parameters)
    assert refused["status"] == "refused"
    assert refused["result"] is None
    assert not target.results
    assert len(target.executions) == 1
    attempt = next(iter(target.executions.values()))
    check_seal(attempt)
    assert attempt["result_id"] is None
    assert attempt["parameters"] == parameters
    assert attempt["refusal"]["code"] and attempt["refusal"]["message"]
    saved = target.save_workspace(tmp_path / "refusal.json")
    restored = Session.from_workspace(saved, tmp_path / "restored")
    assert restored.executions == target.executions
    assert restored.results == {}


@pytest.mark.parametrize("operation", [workflow.COPILOT, workflow.VERIFY])
@pytest.mark.parametrize("challenge", ["invented_occurrence", "modified_assessment", "other_session"])
def test_live_dependency_refuses_before_runtime_or_provider_dispatch(tmp_path, monkeypatch, operation, challenge):
    source = workflow.make_source(example_request())
    target = Session(source, tmp_path / "target", operations=workflow.registry())
    assessed = _call(target, workflow.ASSESS)
    assert assessed["status"] == "completed", assessed
    candidate = deepcopy(assessed["result"])
    if challenge == "invented_occurrence":
        candidate["result_id"] = "result-" + uuid.uuid4().hex
        candidate["execution_id"] = "execution-" + uuid.uuid4().hex
        seal(candidate)
    elif challenge == "modified_assessment":
        candidate["data"]["engineering"]["cooling"]["temperature_k"] += 1.0
        seal(candidate["data"]["engineering"])
        seal(candidate)
    else:
        external = Session(source, tmp_path / "external", operations=workflow.registry())
        externally_assessed = _call(external, workflow.ASSESS)
        assert externally_assessed["status"] == "completed", externally_assessed
        candidate = externally_assessed["result"]
        assert candidate["evidence_id"] == assessed["result"]["evidence_id"]
        assert candidate["data"] == assessed["result"]["data"]
        assert candidate["result_id"] != assessed["result"]["result_id"]
    check_seal(candidate)
    retained_before = deepcopy(target.results)
    calls = []

    def runtime_forbidden(*args, **kwargs):
        calls.append("runtime")
        raise AssertionError("Invalid dependency reached runtime acquisition")

    def provider_forbidden(*args, **kwargs):
        calls.append("provider")
        raise AssertionError("Invalid dependency reached provider execution")

    monkeypatch.setattr(workflow, "runtime_identity", runtime_forbidden)
    monkeypatch.setattr(workflow, "_copilot", provider_forbidden)
    monkeypatch.setattr(workflow, "_verify", provider_forbidden)
    # Bind monitored callbacks after the real assessment has been retained.
    target.operations = workflow.registry()
    refused = _call(target, operation, {"assessment": candidate})
    assert calls == []
    assert refused["status"] == "refused"
    assert refused["result"] is None
    attempt = refused["execution"]
    check_seal(attempt)
    assert attempt["runtime"] is None
    assert attempt["result_id"] is None
    assert attempt["parameters"]["assessment"] == candidate
    assert attempt["refusal"]["code"] == "invalid_operation"
    assert "actually retained assessment occurrence" in attempt["refusal"]["message"]
    assert target.results == retained_before
    assert len(target.executions) == 2
    path = target.save_workspace(tmp_path / "refused-dependency.json")
    reopened = Session.from_workspace(path, tmp_path / "reopened")
    assert reopened.results == retained_before
    assert reopened.executions == target.executions
    assert calls == []


@pytest.mark.parametrize("operation", [workflow.COPILOT, workflow.VERIFY])
def test_exact_retained_dependency_succeeds_after_read_only_reopening_and_explicit_binding(tmp_path, operation):
    session = Session(workflow.make_source(example_request()), tmp_path / "source", operations=workflow.registry())
    assessment = _call(session, workflow.ASSESS)
    assert assessment["status"] == "completed", assessment
    parameters = {"assessment": assessment["result"]}
    first = _call(session, operation, parameters)
    assert first["status"] == "completed", first
    assert first["result"]["data"]["assessment_result_id"] == assessment["result"]["result_id"]
    saved = session.save_workspace(tmp_path / "saved.json")
    before = saved.read_bytes()
    reopened = Session.from_workspace(saved, tmp_path / "reopened")
    assert reopened.results == session.results
    assert saved.read_bytes() == before
    with pytest.raises(AdapterRefusal):
        reopened.operations.get(operation)
    reopened.operations = workflow.registry()
    fresh = _call(reopened, operation, parameters)
    assert fresh["status"] == "completed", fresh
    assert fresh["result"]["result_id"] != first["result"]["result_id"]
    assert fresh["execution"]["execution_id"] != first["execution"]["execution_id"]
    assert fresh["result"]["data"]["assessment_record_digest"] == assessment["result"]["record_digest"]
    second_path = reopened.save_workspace(tmp_path / "reexecuted.json")
    final = Session.from_workspace(second_path, tmp_path / "final")
    assert len(final.results) == len(final.executions) == 3
    assert saved.read_bytes() == before


@pytest.mark.parametrize("operation", [workflow.COPILOT, workflow.VERIFY])
def test_resealed_dependency_cannot_invent_an_assessment_occurrence(tmp_path, operation):
    directory = tmp_path / "retained"
    workflow.run(example_request(), directory)
    value = _workspace(directory)
    dependent = next(item for item in value["results"] if item["operation_id"] == operation)
    candidate = dependent["parameters"]["assessment"]
    candidate["execution_id"] = "execution-" + uuid.uuid4().hex
    candidate["result_id"] = "result-" + uuid.uuid4().hex
    seal(candidate)
    dependent["data"].update(assessment_result_id=candidate["result_id"],
        assessment_execution_id=candidate["execution_id"], assessment_record_digest=candidate["record_digest"])
    execution = next(item for item in value["executions"]
                     if item["execution_id"] == dependent["execution_id"])
    execution["parameters"] = deepcopy(dependent["parameters"])
    seal(execution)
    seal(dependent)
    _write_workspace(directory, value)
    with pytest.raises(ValueError, match="retained assessment occurrence"):
        workflow.inspect(directory)


@pytest.mark.parametrize("operation", sorted(workflow.OPERATIONS))
def test_resealed_operation_cannot_promote_hardware_authority(tmp_path, operation):
    directory = tmp_path / "retained"
    workflow.run(example_request(), directory)
    value = _workspace(directory)
    result = next(item for item in value["results"] if item["operation_id"] == operation)
    result["data"]["authority"]["hardware_actuation"] = "performed"
    seal(result)
    _write_workspace(directory, value)
    with pytest.raises(ValueError):
        workflow.inspect(directory)


def test_explicit_capability_plan_and_agent_host_use_existing_operations(tmp_path):
    advertised = workflow.capability_registry()
    catalog = advertised.catalog()
    assert catalog["authorizes_execution"] is False
    assert set(catalog["operations"]) == workflow.OPERATIONS
    assert all(not item["bound"] for item in catalog["operations"].values())
    with pytest.raises(AdapterRefusal):
        advertised.operations.get(workflow.ASSESS)
    graph = experiment("polymer-observation", model_id="polymer-reference.v1", nodes=[
        {"node_id": "assess", "operation_id": workflow.ASSESS,
         "parameters": {}, "inputs": {}, "depends_on": []},
        {"node_id": "simulate", "operation_id": workflow.SIMULATE,
         "parameters": {}, "inputs": {}, "depends_on": ["assess"]},
    ])
    assert plan_graph(graph, advertised) == ["assess", "simulate"]
    bound = workflow.capability_registry(bind=True)
    host = AgentHost(registry=bound,
        inputs={"source": encode(workflow.make_source(example_request())), "graph": encode(graph)},
        allow_operations=(workflow.ASSESS, workflow.SIMULATE), output_dir=tmp_path / "agent-output")
    outcome = host.call("net_execute", {"source": "source", "graph": "graph", "attempt": "polymer-first"})
    assert outcome["status"] == "completed"
    assert len(outcome["execution_ids"]) == len(outcome["result_ids"]) == 2
    assert outcome["authority"]["state_admission"] == "not_performed"
    retry = host.call("net_execute", {"source": "source", "graph": "graph", "attempt": "polymer-first"})
    assert retry["reused_response"] is True
    assert retry["execution_ids"] == outcome["execution_ids"]
    retained = _workspace(tmp_path / "agent-output" / "polymer-first")
    assert {item["operation_id"] for item in retained["results"]} == {workflow.ASSESS, workflow.SIMULATE}
    assert all(item["data"]["authority"] == AUTHORITY for item in retained["results"])


def test_net_cli_creates_runs_inspects_verifies_and_replays_example(tmp_path, capsys):
    request, bundle, replay = tmp_path / "request.json", tmp_path / "bundle", tmp_path / "replay"
    assert net_main(["polymer", "example", "--output", str(request)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "created"
    assert net_main(["polymer", "run", str(request), "--output-dir", str(bundle)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["status"] == "PASS"
    before = _files(bundle)
    assert net_main(["polymer", "inspect", str(bundle)]) == 0
    assert json.loads(capsys.readouterr().out) == first
    assert net_main(["polymer", "verify", str(bundle)]) == 0
    assert json.loads(capsys.readouterr().out)["fresh_numerical_verification"] is True
    assert net_main(["polymer", "replay", str(bundle), "--output-dir", str(replay)]) == 0
    repeated = json.loads(capsys.readouterr().out)
    assert repeated["evidence_id"] == first["evidence_id"]
    assert repeated["occurrences"] != first["occurrences"]
    assert _files(bundle) == before
    original_request = request.read_bytes()
    assert net_main(["polymer", "example", "--output", str(request)]) == 1
    assert json.loads(capsys.readouterr().err)["status"] == "REFUSE"
    assert request.read_bytes() == original_request


@pytest.mark.parametrize("challenge", ["malformed", "symlink", "oversize"])
def test_cli_refuses_invalid_input_before_creating_a_bundle(tmp_path, capsys, challenge):
    request = tmp_path / "invalid.json"
    if challenge == "symlink":
        regular = tmp_path / "regular.json"
        regular.write_text(json.dumps(example_request()), encoding="utf-8")
        request.symlink_to(regular)
    elif challenge == "oversize":
        request.write_bytes(b" " * (MAX_BYTES + 1))
    else:
        request.write_text('{"schema":"bad"}', encoding="utf-8")
    output = tmp_path / "refused"
    assert net_main(["polymer", "run", str(request), "--output-dir", str(output)]) == 1
    captured = capsys.readouterr()
    assert not captured.out
    assert json.loads(captured.err)["status"] == "REFUSE"
    assert not output.exists()
