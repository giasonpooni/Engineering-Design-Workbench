"""Qualified multiscale providers share the retained Session and authority gates."""
from contextlib import ExitStack
from hashlib import sha256
import json
from unittest.mock import patch

import pytest

from ciw import fluid_contract as contract, fluid_cli, fluid_workflow as workflow
from ciw.operations.registry import default_registry
from ciw.session import read_json
from ciw.core.identities import new_identity
from ciw.operations.runner import seal
from ciw.session import Session


def snapshot(directory):
    return {str(path.relative_to(directory)): sha256(path.read_bytes()).hexdigest()
            for path in directory.rglob("*") if path.is_file()}


@pytest.mark.parametrize("profile", contract.EXTENDED_PROFILES)
def test_extended_retained_lifecycle_is_explicit_read_only_and_fresh(tmp_path, profile):
    request = contract.example_request(profile)
    directory = tmp_path / "run"
    for operation in contract.ALL_OPERATIONS[profile]:
        assert operation not in {row["operation_id"] for row in default_registry().describe()}
    retained = workflow.run(request, directory)
    assert retained["status"] == "LOCAL"
    before = snapshot(directory)
    with ExitStack() as stack:
        for name, function in (("solver", "simulate"), ("reference", "reference"), ("verification", "verify")):
            module = contract.provider_module(profile, name)
            stack.enter_context(patch.object(module, function, side_effect=AssertionError("Unexpected numerical replay")))
        stack.enter_context(patch("ciw.session.execute_operation", side_effect=AssertionError("Unexpected execution")))
        inspected = workflow.inspect(directory)
    assert inspected["fresh_numerical_verification"] is False
    fresh = workflow.verify_retained(directory)
    assert fresh["fresh_numerical_verification"] is True
    for new, original in (("fresh_verification_id", "verification_id"),
                          ("fresh_verification_execution_id", "verification_execution_id"),
                          ("fresh_verification_result_id", "result_id")):
        assert fresh[new] != retained[original]
    exported = workflow.export_csv(directory, tmp_path / "trajectory.csv")
    assert exported["fresh_verification_id"] != fresh["fresh_verification_id"]
    assert snapshot(directory) == before
    workspace = read_json(directory / "workspace.json")
    assert len(workspace["results"]) == len(workspace["executions"]) == 2
    assert len({row["execution_id"] for row in workspace["results"]}) == 2
    assert len({row["result_id"] for row in workspace["results"]}) == 2
    receipt = read_json(directory / "preservation.json")
    assert receipt["claims"]["physical_validation_established"] is False
    assert receipt["claims"]["canonical_state_mutated"] is False
    assert receipt["model_scope"]["particle_meaning"] == contract.module(profile).preservation_scope(request)["particle_meaning"]
    if profile == "molecular":
        representation = next(iter(receipt["registry"]["representations"].values()))
        assert representation["scale"]["length_m"] is None
        assert "Lennard-Jones" in representation["unit_semantics"]


@pytest.mark.parametrize("profile,bins", [("molecular", [2, 2, 2]), ("sph", [4])])
def test_cli_reduction_binds_fresh_source_and_explicit_loss(tmp_path, capsys, profile, bins):
    directory = tmp_path / "run"
    workflow.run(contract.example_request(profile), directory)
    before = snapshot(directory)
    output = tmp_path / "mapped.json"
    assert fluid_cli.main(["reduce", str(directory), "--sample-index", "0", "--bins", *map(str, bins),
                           "--output", str(output)]) == 0
    artifact = read_json(output)
    assert artifact["map_verification"]["status"] == "PASS"
    assert artifact["fresh_source_verification"]["verification_id"] == artifact["source_occurrences"]["fresh_verification_id"]
    assert artifact["mapped"]["claims"]["constitutive_model_supplied"] is False
    assert artifact["snapshot"]["profile"] == profile
    assert snapshot(directory) == before
    assert fluid_cli.main(["reduce", str(directory), "--sample-index", "0", "--bins", *map(str, bins),
                           "--output", str(output)]) == 1
    capsys.readouterr()


def test_full_catalog_preserves_legacy_collections_and_rejects_saved_imports():
    assert contract.PROFILES == ("reservoir", "wave")
    assert set(contract.ALL_PROFILES) == {"reservoir", "wave", "molecular", "sph", "fsi"}
    assert set(contract.OPERATIONS) == set(contract.PROFILES)
    for malicious in ("os", "ciw.fluid_molecular", "../solver", "fsi.solver"):
        with pytest.raises(ValueError):
            contract.module(malicious)
    with pytest.raises(ValueError):
        contract.provider_module("molecular", "__init__")


@pytest.mark.parametrize("profile", contract.EXTENDED_PROFILES)
def test_invented_simulation_occurrence_is_refused_before_reference_activation(tmp_path, profile):
    request = contract.example_request(profile)
    session = Session(workflow.make_source(request), tmp_path / "session", operations=workflow.registry())
    simulation, verification = contract.ALL_OPERATIONS[profile]
    actual = workflow._execute(session, simulation, {})["result"]
    ghost = dict(actual, result_id=new_identity("result"), execution_id=new_identity("execution"))
    seal(ghost)
    with patch.object(contract.provider_module(profile, "verification"), "verify", side_effect=AssertionError("Verifier activation")):
        refused = workflow._execute(session, verification, {"candidate": ghost})
    assert refused["status"] == "refused"
    assert len(session.results) == 1 and actual["result_id"] in session.results
    assert "actually retained" in refused["execution"]["refusal"]["message"]
