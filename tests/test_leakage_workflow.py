"""Native boundary balances retain their actual NET events and offline evidence.

The integration fixture uses an operator-provisioned, exact FSRT checkout. A
numerical PASS never certifies a physical leak, calibration, or machine action.
"""
from copy import deepcopy
import csv
import json
import math
import os
from pathlib import Path
import shutil
import uuid

import pytest

from ciw import leakage_workflow as workflow
from ciw.adapters.protocol import AdapterRefusal
from ciw.agent_api import AgentHost, encode
from ciw.control_plane import experiment, plan_graph
from ciw.core.identities import evidence_id, new_identity, validate_evidence_identity, validate_identity
from ciw.leakage_contract import AUTHORITY, MAX_BYTES, example_request
from ciw.operations.registry import default_registry
from ciw.operations.runner import check_seal, digest, seal
from ciw.session import Session


@pytest.fixture(scope="module")
def native_backend():
    configured = os.environ.get("CIW_LEAKAGE_PROVIDER_CHECKOUT")
    if not configured or not Path(configured).exists():
        pytest.skip("CIW_LEAKAGE_PROVIDER_CHECKOUT must name an existing FSRT checkout")
    from ciw.leakage_native import NativeLeakageBackend
    # A present but wrong revision or incomplete runtime is a test failure.
    return NativeLeakageBackend(Path(configured))


@pytest.fixture(scope="module")
def retained(native_backend, tmp_path_factory):
    root = tmp_path_factory.mktemp("native-leakage")
    result = {}
    for basis in ("volume", "mass"):
        directory = root / basis
        inspection = workflow.run(example_request(basis), directory, backend=native_backend)
        assert inspection["status"] == "PASS", inspection
        result[basis] = directory
    return result


def _files(directory):
    return {str(p.relative_to(directory)): p.read_bytes()
            for p in directory.rglob("*") if p.is_file()}


def _workspace(directory):
    return json.loads((directory / "workspace.json").read_text(encoding="utf-8"))


def _write_workspace(directory, value):
    (directory / "workspace.json").write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


def _copy(retained, tmp_path, basis="volume"):
    destination = tmp_path / "retained"
    shutil.copytree(retained[basis], destination)
    return destination


def _call(session, operation, parameters=None):
    response = session.handle({"protocol_version": 1, "request_id": uuid.uuid4().hex,
        "type": "operation.execute", "payload": {"operation_id": operation,
        "parameters": parameters or {}}})
    assert response["type"] == "response", response
    return response["payload"]


def test_default_registry_and_advertisement_do_not_grant_leakage_execution():
    default = default_registry()
    assert not workflow.OPERATIONS.intersection(r["operation_id"] for r in default.describe())
    for operation in workflow.OPERATIONS:
        with pytest.raises(AdapterRefusal):
            default.get(operation)
    catalog = workflow.capability_registry().catalog()
    assert set(catalog["operations"]) == workflow.OPERATIONS
    assert all(not row["bound"] for row in catalog["operations"].values())
    assert catalog["authorizes_execution"] is False
    with pytest.raises(ValueError, match="explicit pinned backend"):
        workflow.capability_registry(bind=True)


def test_run_requires_explicit_backend_before_creating_any_artifact(tmp_path):
    output = tmp_path / "no-provider"
    with pytest.raises(ValueError, match="explicit pinned native backend"):
        workflow.run(example_request(), output, backend=None)
    assert not output.exists()


@pytest.mark.parametrize("field", ["authority", "provenance", "render"])
def test_rehashed_source_cannot_promote_authority_or_change_canonical_envelope(field):
    source = workflow.make_source(example_request())
    if field == "authority":
        source["metadata"]["authority"] = {"hardware_actuation": "permitted"}
    elif field == "provenance":
        source["metadata"]["provenance"]["source"] = "physically_validated"
    else:
        source["render"] = {"coordinate_frame": source["metadata"]["coordinate_frame"],
                            "physical_validation": "established"}
    source["evidence_id"] = evidence_id(source)
    with pytest.raises(ValueError, match="exact retained declaration"):
        workflow.source_request(source)


@pytest.mark.integration
class TestNativeWorkflow:
    @pytest.mark.parametrize("basis,unit", [("volume", "m3"), ("mass", "kg")])
    def test_native_loss_retains_two_sealed_events_and_full_covariance(self, retained, basis, unit):
        request = example_request(basis)
        inspection = workflow.inspect(retained[basis])
        assert inspection["workflow_status"] == inspection["numerical_audit_status"] == "PASS"
        assert inspection["balance_status"] == "UNACCOUNTED_LOSS"
        assert inspection["unit"] == unit
        assert inspection["authority"] == AUTHORITY
        assert inspection["fresh_execution"] is inspection["fresh_numerical_verification"] is False
        calculation = inspection["assessment"]["calculation"]
        assert calculation["interval"]["residual"] == pytest.approx([-.05] * 4, abs=1e-13)
        assert calculation["cumulative"]["residual"][-1] == pytest.approx(-.2, abs=1e-13)
        assert calculation["raw"]["covariance"] == request["covariance"]["matrix"]
        assert calculation["runtime"]["revision"] == "09a756dd9cdd3a9bb6cb14b5cd498f6259937ac2"
        assert inspection["assessment"]["decision"]["cause_status"] == "NOT_ISOLATED"
        assert len(inspection["assessment"]["decision"]["competing_explanations"]) > 1
        workspace = _workspace(retained[basis])
        validate_evidence_identity(workspace["run"])
        assert workspace["run"]["metadata"]["leakage_request"] == request
        assert len(workspace["results"]) == len(workspace["executions"]) == 2
        assert [e["operation_id"] for e in workspace["executions"]] == [workflow.ASSESS, workflow.VERIFY]
        events = {e["execution_id"]: e for e in workspace["executions"]}
        for result in workspace["results"]:
            event = events[result["execution_id"]]
            check_seal(result)
            check_seal(event)
            validate_identity(result["result_id"], "result")
            validate_identity(result["execution_id"], "execution")
            assert event["status"] == "completed" and event["result_id"] == result["result_id"]
            assert result["evidence_id"] == inspection["evidence_id"]
            assert result["verification_id"] is None and result["verification_status"] == "not_verified"
        assess, verify = workspace["results"]
        assert verify["parameters"]["assessment"] == assess
        assert verify["data"]["assessment_record_digest"] == assess["record_digest"]

    @pytest.mark.parametrize("basis", ["volume", "mass"])
    def test_balanced_amounts_have_zero_residual_and_small_declared_band(self, native_backend, tmp_path, basis):
        request = example_request(basis)
        for i, reading in enumerate(request["inventory"]["readings"]):
            reading["value"] = 10 + .2 * i
        request["covariance"]["matrix"] = [[v * 1e-4 for v in row]
            for row in request["covariance"]["matrix"]]
        before = deepcopy(request)
        result = workflow.run(request, tmp_path / basis, backend=native_backend)
        assert request == before
        assert result["status"] == result["numerical_audit_status"] == "PASS"
        assert result["balance_status"] == "WITHIN_DECLARED_BAND"
        assert result["assessment"]["calculation"]["interval"]["residual"] == pytest.approx([0] * 4, abs=1e-13)
        assert result["assessment"]["decision"]["cause_status"] == "NOT_ISOLATED"

    def test_correlated_endpoint_uncertainty_cancels_in_cumulative_accounting(self, native_backend, tmp_path):
        request = example_request()
        # A shared inventory bias cancels in every storage difference. Adjacent
        # intervals still share their measured endpoint with opposite signs.
        matrix = request["covariance"]["matrix"]
        for i in range(5):
            for j in range(5):
                matrix[i][j] += .003
        result = workflow.run(request, tmp_path / "correlated", backend=native_backend)
        calculation = result["assessment"]["calculation"]
        assert result["numerical_audit_status"] == "PASS"
        assert calculation["raw"]["covariance"] == matrix
        interval, cumulative = calculation["interval"]["covariance"], calculation["cumulative"]["covariance"]
        assert interval[0][0] == pytest.approx(.000202, abs=1e-15)
        assert interval[0][1] == pytest.approx(-.0001, abs=1e-15)
        assert interval[0][2] == pytest.approx(0, abs=1e-15)
        assert cumulative[-1][-1] == pytest.approx(.000208, abs=1e-15)
        assert cumulative[-1][-1] < sum(interval[i][i] for i in range(4))

    def test_lawful_one_ulp_threshold_difference_cannot_resolve_unaccounted_loss(self, native_backend):
        from ciw.leakage_contract import raw_order
        from ciw.leakage_verification import verify
        request = example_request()
        request["edges_s"] = request["edges_s"][:2]
        request["clock"]["end_s"] = request["edges_s"][-1]
        request["inventory"]["readings"] = request["inventory"]["readings"][:2]
        for reading in request["inventory"]["readings"]:
            reading["value"] = 10.0
        request["channels"] = request["channels"][:1]
        request["channels"][0]["readings"] = request["channels"][0]["readings"][:1]
        request["channels"][0]["readings"][0]["value"] = .001
        request["decision_policy"]["loss_threshold"] = .001
        request["covariance"]["raw_order"] = raw_order(request)
        request["covariance"]["matrix"] = [[0.0] * 3 for _ in range(3)]
        calculation = native_backend.calculate(request)
        for label in ("interval", "cumulative"):
            calculation[label]["residual"][0] = math.nextafter(-.001, -math.inf)
        assert verify(request, calculation)["status"] == "PASS"
        decision = workflow.decision_projection(request, calculation)
        assert decision["status"] == "INDETERMINATE"
        for row in (*decision["intervals"], decision["window"]):
            assert row["loss_estimate"] > .001
            assert row["declared_interval"][0] > .001
            assert row["decision_interval"][0] < .001 < row["decision_interval"][1]
            assert row["numerical_guard"]["residual_error_bound"] > 0
            assert row["numerical_guard"]["covariance_diagonal_error_bound"] == 0
            assert row["status"] == "INDETERMINATE"

    def test_saved_inspection_never_executes_runtime_or_scientific_provider(self, retained, tmp_path, monkeypatch):
        directory = _copy(retained, tmp_path)
        original, before = workflow.inspect(directory), _files(directory)
        from ciw import leakage_native, leakage_verification
        def forbidden(*args, **kwargs):
            pytest.fail("Reading saved evidence invoked an executable provider")
        for name in ("_assess", "_verify", "runtime_identity"):
            monkeypatch.setattr(workflow, name, forbidden)
        monkeypatch.setattr(leakage_native.NativeLeakageBackend, "__init__", forbidden)
        monkeypatch.setattr(leakage_native.NativeLeakageBackend, "calculate", forbidden)
        monkeypatch.setattr(leakage_native.NativeLeakageBackend, "runtime_identity", forbidden)
        monkeypatch.setattr(leakage_verification, "verify", forbidden)
        restored = Session.from_workspace(directory / "workspace.json", tmp_path / "restored")
        assert len(restored.executions) == len(restored.results) == 2
        assert workflow.inspect(directory) == original
        assert _files(directory) == before

    def test_fresh_audit_has_new_identity_without_native_execution_or_source_mutation(self, retained, tmp_path, monkeypatch):
        directory = _copy(retained, tmp_path)
        original, before = workflow.inspect(directory), _files(directory)
        from ciw.leakage_native import NativeLeakageBackend
        def forbidden(*args, **kwargs):
            pytest.fail("Offline numerical verification executed the native provider")
        for name in ("__init__", "calculate", "runtime_identity"):
            monkeypatch.setattr(NativeLeakageBackend, name, forbidden)
        monkeypatch.setattr(workflow, "runtime_identity", forbidden)
        first, second = workflow.verify_retained(directory), workflow.verify_retained(directory)
        assert first["status"] == second["status"] == "PASS"
        identities = {first["verification_id"], second["verification_id"], original["verification"]["verification_id"]}
        assert len(identities) == 3
        for identity in identities:
            validate_identity(identity, "verification")
        assert first["fresh_numerical_verification"] is True
        assert first["source_evidence_id"] == original["evidence_id"]
        assert first["report"] == second["report"] == original["verification"]["report"]
        assert first["authority"] == AUTHORITY
        assert _files(directory) == before

    @pytest.mark.parametrize("basis", ["volume", "mass"])
    def test_replay_executes_fresh_occurrences_with_identical_evidence(self, retained, native_backend, tmp_path, basis):
        original = workflow.inspect(retained[basis])
        before = _files(retained[basis])
        repeated = workflow.replay(retained[basis], tmp_path / "replayed", backend=native_backend)
        assert repeated["status"] == "PASS"
        assert repeated["evidence_id"] == repeated["replay_source_evidence_id"] == original["evidence_id"]
        assert repeated["assessment"] == original["assessment"]
        assert repeated["verification"]["report"] == original["verification"]["report"]
        for field in ("execution_id", "result_id"):
            assert {e[field] for e in original["occurrences"]}.isdisjoint(e[field] for e in repeated["occurrences"])
        assert repeated["verification"]["verification_id"] != original["verification"]["verification_id"]
        assert _files(retained[basis]) == before

    def test_export_preserves_full_workspace_and_hashes_every_artifact(self, retained, tmp_path, monkeypatch):
        source = retained["volume"]
        before = _files(source)
        from ciw.leakage_native import NativeLeakageBackend
        def forbidden(*args, **kwargs):
            pytest.fail("Export executed native code")
        monkeypatch.setattr(NativeLeakageBackend, "__init__", forbidden)
        destination = tmp_path / "report"
        result = workflow.export(source, destination)
        assert result["status"] == "created" and result["authority"] == AUTHORITY
        assert (destination / "workspace.json").read_bytes() == before["workspace.json"]
        assert result["source_workspace_ref"] == "sha256:" + __import__("hashlib").sha256(before["workspace.json"]).hexdigest()
        assert {a["path"] for a in result["artifacts"]} == {"workspace.json", "request.json", "inspection.json", "balance.csv", "report.html"}
        for artifact in result["artifacts"]:
            raw = (destination / artifact["path"]).read_bytes()
            assert artifact["size_bytes"] == len(raw)
            assert artifact["sha256"] == "sha256:" + __import__("hashlib").sha256(raw).hexdigest()
        with (destination / "balance.csv").open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 5 and rows[-1]["scope"] == "whole_window"
        assert rows[-1]["status"] == "UNACCOUNTED_LOSS"
        assert "cause and location are not isolated" in (destination / "report.html").read_text()
        assert workflow.inspect(destination)["status"] == "PASS"
        with pytest.raises(FileExistsError):
            workflow.export(source, destination)
        assert _files(source) == before

    @pytest.mark.parametrize("challenge", ["missing_attempt", "duplicate_execution", "duplicate_result", "promoted_authority", "changed_residual", "changed_scientific_ref", "invented_dependency"])
    def test_tampered_retained_graph_is_refused_even_after_resealing(self, retained, tmp_path, challenge):
        directory = _copy(retained, tmp_path)
        value = _workspace(directory)
        assessment, verification = value["results"]
        if challenge == "missing_attempt":
            value["executions"] = value["executions"][:1]
        elif challenge == "duplicate_execution":
            value["executions"].append(deepcopy(value["executions"][0]))
        elif challenge == "duplicate_result":
            value["results"].append(deepcopy(assessment))
        elif challenge == "promoted_authority":
            assessment["data"]["authority"]["physical_validation"] = "established"
            seal(assessment)
        elif challenge == "changed_residual":
            assessment["data"]["calculation"]["interval"]["residual"][0] = 123.0
            seal(assessment)
        elif challenge == "changed_scientific_ref":
            verification["data"]["report"]["calculation_ref"] = "sha256:" + "0" * 64
            seal(verification["data"]["report"])
            seal(verification)
        else:
            candidate = verification["parameters"]["assessment"]
            candidate["result_id"] = new_identity("result")
            candidate["execution_id"] = new_identity("execution")
            seal(candidate)
            verification["data"]["assessment_result_id"] = candidate["result_id"]
            verification["data"]["assessment_execution_id"] = candidate["execution_id"]
            verification["data"]["assessment_record_digest"] = candidate["record_digest"]
            value["executions"][1]["parameters"] = deepcopy(verification["parameters"])
            seal(value["executions"][1])
            seal(verification)
        _write_workspace(directory, value)
        before = _files(directory)
        with pytest.raises(ValueError):
            workflow.inspect(directory)
        assert _files(directory) == before

    def test_refused_native_attempt_is_retained_without_dependent_result(self, native_backend, tmp_path, monkeypatch):
        def refuse(*args, **kwargs):
            raise AdapterRefusal("TEST_PROVIDER_REFUSAL", "Unsupported declared covariance")
        def forbidden(*args, **kwargs):
            pytest.fail("Audit executed after a refused balance")
        monkeypatch.setattr(native_backend, "calculate", refuse)
        monkeypatch.setattr(workflow, "_verify", forbidden)
        directory = tmp_path / "refused"
        result = workflow.run(example_request(), directory, backend=native_backend)
        assert result["status"] == "REFUSE"
        assert result["assessment"] is result["verification"] is None
        assert len(result["occurrences"]) == 1
        attempt = _workspace(directory)["executions"][0]
        check_seal(attempt)
        assert attempt["status"] == "refused" and attempt["result_id"] is None
        assert attempt["refusal"]["code"] == "TEST_PROVIDER_REFUSAL"
        assert _workspace(directory)["results"] == []
        assert workflow.inspect(directory) == workflow.verify_retained(directory) == result

    def test_actual_mass_kernel_refuses_supported_contract_with_non_spd_covariance(self, native_backend, tmp_path):
        request = example_request("mass")
        size = len(request["covariance"]["matrix"])
        request["covariance"]["matrix"] = [[0.0] * size for _ in range(size)]
        directory = tmp_path / "mass-psd"
        result = workflow.run(request, directory, backend=native_backend)
        assert result["status"] == "REFUSE" and result["assessment"] is None
        workspace = _workspace(directory)
        assert workspace["results"] == [] and len(workspace["executions"]) == 1
        attempt = workspace["executions"][0]
        check_seal(attempt)
        assert attempt["status"] == "refused" and attempt["runtime"]["native"]["revision"]
        assert attempt["refusal"]["code"] == "LEAKAGE_UNSUPPORTED_COVARIANCE"

    def test_fresh_oracle_rejects_coherently_resealed_wrong_numerics(self, retained, tmp_path, monkeypatch):
        directory = _copy(retained, tmp_path)
        value = _workspace(directory)
        assessment, verification = value["results"]
        calculation = assessment["data"]["calculation"]
        calculation["interval"]["residual"][0] += .1
        assessment["data"]["decision"] = workflow.decision_projection(example_request(), calculation)
        seal(assessment)
        verification["parameters"]["assessment"] = deepcopy(assessment)
        verification["data"]["assessment_record_digest"] = assessment["record_digest"]
        verification["data"]["report"]["calculation_ref"] = digest(calculation)
        seal(verification["data"]["report"])
        seal(verification)
        value["executions"][1]["parameters"] = deepcopy(verification["parameters"])
        seal(value["executions"][1])
        _write_workspace(directory, value)
        before = _files(directory)
        from ciw.leakage_native import NativeLeakageBackend
        def forbidden(*args, **kwargs):
            pytest.fail("Fresh numerical oracle executed the native provider")
        monkeypatch.setattr(NativeLeakageBackend, "calculate", forbidden)
        monkeypatch.setattr(NativeLeakageBackend, "__init__", forbidden)
        fresh = workflow.verify_retained(directory)
        assert fresh["status"] == "FAIL"
        failed = {row["name"] for row in fresh["report"]["checks"] if not row["passed"]}
        assert "interval_residuals" in failed
        assert fresh["authority"] == AUTHORITY
        assert _files(directory) == before

    @pytest.mark.parametrize("challenge", ["invented_occurrence", "modified_candidate", "other_session"])
    def test_live_dependency_requires_actual_same_session_assessment(self, retained, native_backend, tmp_path, monkeypatch, challenge):
        target = Session.from_workspace(retained["volume"] / "workspace.json", tmp_path / "target")
        target.operations = workflow.registry(native_backend)
        candidate = deepcopy(next(r for r in target.results.values() if r["operation_id"] == workflow.ASSESS))
        if challenge == "invented_occurrence":
            candidate["result_id"] = new_identity("result")
            candidate["execution_id"] = new_identity("execution")
        elif challenge == "modified_candidate":
            candidate["data"]["decision"]["cause_status"] = "ISOLATED"
        else:
            foreign = workflow.run(example_request(), tmp_path / "foreign", backend=native_backend)
            assert foreign["evidence_id"] == target.run["evidence_id"]
            candidate = _workspace(tmp_path / "foreign")["results"][0]
        seal(candidate)
        def forbidden(*args, **kwargs):
            pytest.fail("Invalid dependency reached runtime or provider dispatch")
        monkeypatch.setattr(workflow, "runtime_identity", forbidden)
        monkeypatch.setattr(workflow, "_verify", forbidden)
        before_results = deepcopy(target.results)
        outcome = _call(target, workflow.VERIFY, {"assessment": candidate})
        assert outcome["status"] == "refused" and outcome["result"] is None
        assert target.results == before_results
        assert len(target.executions) == 3
        attempt = next(e for e in target.executions.values() if e["status"] == "refused")
        check_seal(attempt)

    def test_typed_agent_graph_uses_actual_assessment_edge_and_fresh_replay(self, native_backend, tmp_path):
        graph = experiment("native-leakage", model_id="fsrt-conservation.v1", nodes=[
            {"node_id": "assessment", "operation_id": workflow.ASSESS,
             "parameters": {}, "inputs": {}, "depends_on": []},
            {"node_id": "verification", "operation_id": workflow.VERIFY,
             "parameters": {}, "inputs": {"assessment": {"node_id": "assessment", "port": "result"}},
             "depends_on": ["assessment"]},
        ])
        bound = workflow.capability_registry(native_backend, bind=True)
        assert plan_graph(graph, bound) == ["assessment", "verification"]
        host = AgentHost(registry=bound,
            inputs={"source": encode(workflow.make_source(example_request())), "graph": encode(graph)},
            allow_operations=(workflow.ASSESS, workflow.VERIFY), output_dir=tmp_path / "agent-output")
        original = host.call("net_execute", {"source": "source", "graph": "graph", "attempt": "first"})
        assert original["status"] == "completed", original
        retained = _workspace(tmp_path / "agent-output" / "first")
        assessment, verification = retained["results"]
        assert verification["parameters"]["assessment"] == assessment
        assert verification["data"]["report"]["status"] == "PASS"
        retry = host.call("net_execute", {"source": "source", "graph": "graph", "attempt": "first"})
        assert retry["reused_response"] is True and retry["execution_ids"] == original["execution_ids"]
        repeated = host.call("net_replay", {"original_attempt": "first", "new_attempt": "second"})
        assert repeated["status"] == "completed"
        assert set(repeated["execution_ids"]).isdisjoint(original["execution_ids"])
        assert original["authority"]["state_admission"] == "not_performed"

    def test_replay_rejects_runtime_drift_before_creating_output(self, retained, native_backend, tmp_path, monkeypatch):
        runtime = deepcopy(native_backend.runtime_identity())
        runtime["dependencies"]["numpy"] = "99.0.0"
        monkeypatch.setattr(native_backend, "runtime_identity", lambda: deepcopy(runtime))
        def forbidden(*args, **kwargs):
            pytest.fail("Incompatible replay dispatched native conservation")
        monkeypatch.setattr(native_backend, "calculate", forbidden)
        output = tmp_path / "incompatible"
        with pytest.raises(ValueError):
            workflow.replay(retained["volume"], output, backend=native_backend)
        assert not output.exists()

    def test_parent_coupling_retains_actual_source_result_and_completed_event(self, native_backend, tmp_path):
        from ciw import polymer_workflow
        from ciw.polymer_contract import example_request as polymer_example
        parent_dir = tmp_path / "polymer"
        parent = polymer_workflow.run(polymer_example(), parent_dir)
        before = _files(parent_dir)
        child_dir = tmp_path / "leakage"
        child = workflow.run(example_request(), child_dir, backend=native_backend, polymer_directory=parent_dir)
        binding = _workspace(child_dir)["run"]["metadata"]["leakage_polymer_binding"]
        retained_parent = _workspace(parent_dir)
        actual = next(r for r in retained_parent["results"] if r["operation_id"] == polymer_workflow.ASSESS)
        assert binding["source"] == retained_parent["run"]
        assert binding["assessment"] == actual
        assert binding["execution"] == next(e for e in retained_parent["executions"] if e["execution_id"] == actual["execution_id"])
        assert child["polymer_binding"]["evidence_id"] == parent["evidence_id"]
        assert child["polymer_binding"]["assessment_result_id"] == actual["result_id"]
        assert child["polymer_binding"]["binding_ref"] == digest(binding)
        assert _files(parent_dir) == before
        repeated = workflow.replay(child_dir, tmp_path / "replay", backend=native_backend)
        assert repeated["polymer_binding"] == child["polymer_binding"]
        assert repeated["evidence_id"] == child["evidence_id"]

    @pytest.mark.parametrize("field", ["identity", "process", "frame", "source_kind", "clock", "outside_support"])
    def test_parent_mismatch_refuses_before_provider_or_destination_creation(self, native_backend, tmp_path, monkeypatch, field):
        from ciw import polymer_workflow
        from ciw.polymer_contract import example_request as polymer_example
        parent_dir = tmp_path / "polymer"
        polymer_workflow.run(polymer_example(), parent_dir)
        request = example_request()
        if field == "identity":
            request[field]["cycle_id"] = "synthetic.other-cycle"
        elif field == "process":
            request[field] = "extrusion_blow_molding"
        elif field == "clock":
            request[field]["id"] = "different-clock"
        elif field == "source_kind":
            request[field] = "retained_observation"
        elif field == "outside_support":
            request["clock"]["end_s"] = 11.0
            request["edges_s"] = [edge * 1.1 for edge in request["edges_s"]]
            for i, reading in enumerate(request["inventory"]["readings"]):
                reading["time_s"] = request["edges_s"][i]
            for channel in request["channels"]:
                for i, reading in enumerate(channel["readings"]):
                    reading["start_s"], reading["end_s"] = request["edges_s"][i:i + 2]
        else:
            request[field] = "different.frame.v1"
        def forbidden(*args, **kwargs):
            pytest.fail("Parent mismatch dispatched the native provider")
        monkeypatch.setattr(native_backend, "calculate", forbidden)
        monkeypatch.setattr(native_backend, "runtime_identity", forbidden)
        output = tmp_path / "refused"
        with pytest.raises(ValueError):
            workflow.run(request, output, backend=native_backend, polymer_directory=parent_dir)
        assert not output.exists()


@pytest.mark.parametrize("name,challenge", [("request.json", "symlink"), ("workspace.json", "symlink"), ("request.json", "oversize"), ("workspace.json", "oversize"), ("request.json", "duplicate"), ("request.json", "nonfinite")])
@pytest.mark.integration
def test_retained_file_boundaries_refuse_without_native_loading(retained, tmp_path, monkeypatch, name, challenge):
    directory = _copy(retained, tmp_path)
    path = directory / name
    if challenge == "symlink":
        real = directory / (name + ".target")
        path.rename(real)
        path.symlink_to(real)
    elif challenge == "oversize":
        with path.open("wb") as stream:
            stream.truncate((MAX_BYTES if name == "request.json" else workflow.MAX_WORKSPACE_BYTES) + 1)
    elif challenge == "duplicate":
        path.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    else:
        path.write_text('{"value":NaN}', encoding="utf-8")
    from ciw.leakage_native import NativeLeakageBackend
    def forbidden(*args, **kwargs):
        pytest.fail("Malformed retained evidence loaded an executable provider")
    monkeypatch.setattr(NativeLeakageBackend, "__init__", forbidden)
    with pytest.raises(ValueError):
        workflow.inspect(directory)
