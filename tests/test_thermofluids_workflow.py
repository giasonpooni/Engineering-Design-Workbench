"""Audit lifecycle boundaries independently of thermofluid calculation formulas."""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from ciw import thermofluids_models as models
from ciw import thermofluids_workflow as workflow
from ciw.core.identities import content_identity, new_identity, validate_identity
from ciw.net import main
from ciw.operations.runner import check_seal, seal


@pytest.fixture(params=list(models.PROFILES))
def retained(request):
    return workflow.run(models.example_request(request.param))


def test_run_separates_evidence_operation_and_occurrence_identities(retained):
    request = retained["request"]
    fresh = workflow.run(request)
    assert retained["evidence_id"] == fresh["evidence_id"] == content_identity(request)
    assert retained["operation_id"] == fresh["operation_id"] == workflow.operation_id(request["profile"])
    assert retained["numerical_digest"] == fresh["numerical_digest"]
    for name, kind in (("execution_id", "execution"), ("result_id", "result")):
        validate_identity(retained[name], kind)
        assert retained[name] != fresh[name]
    assert retained["record_digest"] != fresh["record_digest"]
    assert retained["replay_of"] is None
    assert retained["authority"] == workflow.AUTHORITY
    assert "verification_id" not in retained
    check_seal(retained)


def test_run_retains_a_detached_request_and_data(retained):
    request = deepcopy(retained["request"])
    snapshot = deepcopy(request)
    fresh = workflow.run(request)
    assert request == snapshot
    request.clear()
    assert fresh["request"] == snapshot


def test_inspection_reads_without_recompute_or_runtime_probing(retained):
    before = deepcopy(retained)
    with patch.object(models, "calculate", side_effect=AssertionError("Numerical execution")), \
         patch.object(workflow, "runtime_identity", side_effect=AssertionError("Runtime execution")):
        view = workflow.inspect(retained)
    assert retained == before
    assert view["integrity"] == "PASS"
    assert view["numerical_verification"] == "not_performed_by_inspection"
    assert "verification_id" not in view
    assert view["data"] == retained["data"]
    view["data"]["quantities"].clear()
    assert retained == before


def test_verification_is_a_fresh_explicit_same_implementation_occurrence(retained):
    before = deepcopy(retained)
    first, second = workflow.verify(retained), workflow.verify(retained)
    assert first["status"] == second["status"] == "PASS"
    assert first["verification_id"] != second["verification_id"]
    validate_identity(first["verification_id"], "verification")
    assert first["independent"] is False
    assert first["scope"] == "same_implementation_exact_recomputation"
    assert first["authority"] == workflow.AUTHORITY
    assert first["checks"] == {"retained_integrity": True, "same_runtime": True, "exact_recomputation": True}
    for ref, key in (("record_ref", "record_digest"), ("execution_ref", "execution_id"),
                     ("result_ref", "result_id"), ("evidence_ref", "evidence_id")):
        assert first[ref] == retained[key]
    assert retained == before
    check_seal(first)


def test_resealed_numerical_forgery_is_structural_but_fails_fresh_verification(retained):
    forged = deepcopy(retained)
    quantity = next(iter(forged["data"]["quantities"].values()))
    quantity["value"] += abs(quantity["value"]) + 1.0
    forged["numerical_digest"] = content_identity(forged["data"])
    seal(forged)
    with patch.object(models, "calculate", side_effect=AssertionError("Inspection recomputed")):
        assert workflow.inspect(forged)["integrity"] == "PASS"
    checked = workflow.verify(forged)
    assert checked["status"] == "FAIL"
    assert checked["checks"]["exact_recomputation"] is False
    with pytest.raises(ValueError, match="reproducible"):
        workflow.replay(forged)


@pytest.mark.parametrize("field", ["authority", "schema", "runtime_implementation", "runtime_version",
                                  "runtime_hash", "unknown_field", "evidence", "operation",
                                  "execution_kind", "result_kind", "units", "limitations"])
def test_resealed_contract_tampering_is_rejected(field):
    record = workflow.run(models.example_request(next(iter(models.PROFILES))))
    if field == "authority":
        record["authority"]["physical_validation"] = "established"
    elif field == "schema":
        record["schema"] = "ciw.thermofluids-run.v2"
    elif field == "runtime_implementation":
        record["runtime"]["implementation"] = "untrusted.provider.v1"
    elif field == "runtime_version":
        record["runtime"]["python_version"] = "untrusted.import.path"
    elif field == "runtime_hash":
        record["runtime"]["source_sha256"]["models"] = "not-a-content-reference"
    elif field == "unknown_field":
        record["certified"] = True
    elif field == "evidence":
        record["evidence_id"] = content_identity({"different": "evidence"})
    elif field == "operation":
        record["operation_id"] = "ciw.other-operation.v1"
    elif field == "execution_kind":
        record["execution_id"] = new_identity("result")
    elif field == "result_kind":
        record["result_id"] = new_identity("execution")
    elif field == "units":
        next(iter(record["data"]["quantities"].values()))["unit"] = "unrelated"
        record["numerical_digest"] = content_identity(record["data"])
    else:
        record["data"]["limitations"] = []
        record["numerical_digest"] = content_identity(record["data"])
    seal(record)
    with patch.object(models, "calculate", side_effect=AssertionError("Must refuse before solving")):
        for action in (workflow.inspect, workflow.verify, workflow.replay):
            with pytest.raises(ValueError):
                action(record)


def test_changed_runtime_is_inspectable_but_refuses_recomputation(retained):
    historical = deepcopy(retained)
    historical["runtime"]["source_sha256"]["models"] = "sha256:" + "0" * 64
    seal(historical)
    before = deepcopy(historical)
    with patch.object(models, "calculate", side_effect=AssertionError("Changed runtime executed")):
        assert workflow.inspect(historical)["integrity"] == "PASS"
        checked = workflow.verify(historical)
        assert checked["status"] == "REFUSE"
        assert checked["checks"]["same_runtime"] is False
        assert checked["checks"]["exact_recomputation"] is None
        with pytest.raises(ValueError, match="reproducible"):
            workflow.replay(historical)
    assert historical == before


def test_replay_creates_new_occurrences_with_stable_evidence_and_numerical_content(retained):
    before = deepcopy(retained)
    replay = workflow.replay(retained)
    assert replay["replay_of"] == {name: retained[name] for name in ("record_digest", "execution_id", "result_id")}
    for name in ("execution_id", "result_id", "record_digest"):
        assert replay[name] != retained[name]
    for name in ("evidence_id", "operation_id", "numerical_digest", "request", "runtime", "data"):
        assert replay[name] == retained[name]
    assert workflow.verify(replay)["status"] == "PASS"
    assert retained == before


def test_replay_rejects_reused_occurrence_identity(retained):
    replay = workflow.replay(retained)
    replay["replay_of"]["execution_id"] = replay["execution_id"]
    seal(replay)
    with pytest.raises(ValueError, match="new occurrence"):
        workflow.inspect(replay)


def test_catalog_discovers_all_five_bounded_profiles_without_execution(capsys):
    with patch.object(models, "calculate", side_effect=AssertionError("Catalog executed")):
        assert main(["thermofluids", "catalog"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert len(catalog["profiles"]) == 5
    assert {item["profile"] for item in catalog["profiles"]} == set(models.PROFILES)
    assert catalog["authorizes_execution"] is False and catalog["read_only"] is True
    assert catalog["qualification"] == "not_performed_by_catalog"
    for item in catalog["profiles"]:
        assert item["operation_id"] == workflow.operation_id(item["profile"])
        assert item["assumptions"] and item["limitations"]
    catalog["profiles"][0]["limitations"].clear()
    assert workflow.catalog()["profiles"][0]["limitations"]


def test_cli_complete_journey_retains_new_files_and_never_overwrites(tmp_path, capsys):
    profile = next(iter(models.PROFILES))
    paths = {name: tmp_path / (name + ".json") for name in ("request", "run", "verification", "replay")}
    calls = [
        ["thermofluids", "example", "--profile", profile, "--output", str(paths["request"])],
        ["thermofluids", "run", str(paths["request"]), "--output", str(paths["run"])],
        ["thermofluids", "verify", str(paths["run"]), "--output", str(paths["verification"])],
        ["thermofluids", "replay", str(paths["run"]), "--output", str(paths["replay"])],
    ]
    for args in calls:
        assert main(args) == 0
        json.loads(capsys.readouterr().out)
    before = {name: path.read_bytes() for name, path in paths.items()}
    assert main(["thermofluids", "inspect", str(paths["run"])]) == 0
    assert json.loads(capsys.readouterr().out)["numerical_verification"] == "not_performed_by_inspection"
    for args in calls:
        assert main(args) == 1
        assert json.loads(capsys.readouterr().err)["status"] == "REFUSE"
    assert {name: path.read_bytes() for name, path in paths.items()} == before
    saved_run = json.loads(before["run"])
    saved_replay = json.loads(before["replay"])
    assert saved_run["evidence_id"] == saved_replay["evidence_id"]
    assert saved_run["execution_id"] != saved_replay["execution_id"]
    assert json.loads(before["verification"])["status"] == "PASS"


def test_cli_retains_a_failed_numerical_verification_with_failure_exit_code(tmp_path, capsys):
    forged = workflow.run(models.example_request(next(iter(models.PROFILES))))
    quantity = next(iter(forged["data"]["quantities"].values()))
    quantity["value"] += abs(quantity["value"]) + 1.0
    forged["numerical_digest"] = content_identity(forged["data"])
    seal(forged)
    source, output = tmp_path / "forged.json", tmp_path / "failed-check.json"
    source.write_text(json.dumps(forged), encoding="utf-8")
    assert main(["thermofluids", "verify", str(source), "--output", str(output)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "FAIL"
