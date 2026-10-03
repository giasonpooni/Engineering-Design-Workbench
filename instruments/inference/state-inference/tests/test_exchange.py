# SPDX-License-Identifier: MPL-2.0
"""Numerical import/export through the actual source-pinned exchange checker."""

from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from geometric_state_inference import LinearObservation, Observation, StatePrior, replay_estimate, update
from geometric_state_inference.exchange import (
    CHECKER_PATH, CHECKER_SHA256, OPERATION_REF, RESULT_SCHEMA,
    export_result_artifact, import_observation_batch,
)


EPOCH = "2026-09-20T12:00:00Z"
FRAME = {"id": "frame:synthetic-plane", "semantics": "intrinsic_physical",
         "basis": ["east", "north"]}


def observation_artifact():
    return {
        "schema": "notation.instrument.observation-batch.v1",
        "batch_id": "example:synthetic-position",
        "observed_at": "2026-09-20T12:00:02Z",
        "received_at": "2026-09-20T12:00:03Z",
        "clock_basis": "synthetic UTC fixture",
        "components": [
            {"name": "east", "value": 1.2, "unit": "m"},
            {"name": "north", "value": -0.4, "unit": "m"},
        ],
        "covariance": {
            "status": "reported", "variables": ["east", "north"],
            "units": ["m", "m"], "matrix": [[0.04, 0.01], [0.01, 0.09]],
            "frame": deepcopy(FRAME), "method": "synthetic declaration",
            "source_refs": ["example:raw-source"],
            "calibration_refs": ["example:declared-calibration"],
            "numerical_status": "unchecked",
        },
        "source_artifact_refs": ["example:raw-source"],
        "calibration_refs": ["example:declared-calibration"],
        "admission_ref": "example:unresolved-admission",
        "admission_status": "reference_only",
    }


@pytest.fixture
def validator_repo():
    path = os.environ.get("GSIE_SET_REPO")
    if not path:
        pytest.skip("Set GSIE_SET_REPO to the documented source-pinned SET checkout")
    return Path(path)


def imported(repo, artifact=None, **overrides):
    arguments = dict(epoch=EPOCH, variables=("east", "north"), units=("m", "m"),
                     frame=deepcopy(FRAME), validator_repo=repo)
    arguments.update(overrides)
    return import_observation_batch(observation_artifact() if artifact is None else artifact,
                                    **arguments)


def estimated(source):
    prior = StatePrior(time=source.observation.time, mean=[0.0, 0.0],
                       covariance=[[1.0, 0.2], [0.2, 2.0]],
                       frame_id=FRAME["id"], units=("m", "m"), state_id="example:prior")
    return update(prior, source.observation,
                  LinearObservation(np.eye(2), model_id="example:identity-model"))


def exported(repo, source, estimate=None, **overrides):
    arguments = dict(source=source, variables=("east", "north"), frame=deepcopy(FRAME),
                     execution_ref="example:execution-1", created_at="2026-09-20T12:00:04Z",
                     applicability="synthetic two-dimensional linear estimate only",
                     validator_repo=repo)
    arguments.update(overrides)
    return export_result_artifact(estimated(source) if estimate is None else estimate,
                                  **arguments)


def test_source_pin_refuses_unapproved_code_before_execution(tmp_path):
    source = tmp_path / CHECKER_PATH
    source.parent.mkdir()
    source.write_text("raise AssertionError('unapproved code must not execute')")
    with pytest.raises(ValueError, match="source pin"):
        imported(tmp_path)


def test_import_preserves_full_covariance_and_metadata_without_mutation(validator_repo):
    artifact = observation_artifact()
    before = deepcopy(artifact)
    source = imported(validator_repo, artifact)
    np.testing.assert_array_equal(source.observation.covariance, [[0.04, 0.01], [0.01, 0.09]])
    assert source.observation.time == 2.0
    assert source.observation.observation_id == artifact["batch_id"]
    assert source.observation.evidence_refs == ("example:raw-source",)
    assert source.artifact == before == artifact
    artifact["components"][0]["value"] = 900.0
    source.artifact["covariance"]["matrix"][0][0] = 999.0
    assert source.artifact == before
    assert source.artifact["received_at"] != source.artifact["observed_at"]


@pytest.mark.parametrize("changes, message", [
    ({"variables": ("north", "east")}, "component order"),
    ({"units": ("mm", "m")}, "declared units"),
    ({"frame": {**FRAME, "basis": ["north", "east"]}}, "complete declared frame"),
    ({"epoch": "2026-09-20"}, "UTC instant"),
    ({"epoch": "2026-09-20T12:00:00.0000001Z"}, "six fractional digits"),
])
def test_import_refuses_implicit_interpretation_changes(validator_repo, changes, message):
    with pytest.raises(ValueError, match=message):
        imported(validator_repo, **changes)


@pytest.mark.parametrize("change, message", [
    (lambda x: x["covariance"].update(status="unknown", matrix=None), "explicit observation covariance"),
    (lambda x: x["covariance"].update(matrix=[[1, 2], [2, 1]]), "positive-semidefinite"),
    (lambda x: x["covariance"].update(matrix=[[1, 0], [0.1, 1]]), "symmetric"),
    (lambda x: x["covariance"].update(variables=["north", "east"]), "component order"),
    (lambda x: x.update(calibration_refs=[]), "calibration_refs"),
    (lambda x: x.update(observed_at="2026-09-20T12:00:02.0000001Z"), "six fractional digits"),
])
def test_import_uses_actual_scientific_contract_refusals(validator_repo, change, message):
    artifact = observation_artifact()
    change(artifact)
    with pytest.raises(ValueError, match=message):
        imported(validator_repo, artifact)


def test_result_preserves_sources_covariance_and_distinct_identities(validator_repo):
    source = imported(validator_repo)
    estimate = estimated(source)
    artifact = exported(validator_repo, source, estimate)
    assert artifact["input_refs"] == ["example:prior", "example:synthetic-position", "example:raw-source"]
    assert artifact["calibration_refs"] == ["example:declared-calibration"]
    assert artifact["covariance"]["source_refs"] == artifact["input_refs"]
    assert artifact["covariance"]["matrix"] == estimate.covariance.tolist()
    assert artifact["covariance"]["matrix"][0][1] != 0
    assert artifact["observation_binding"]["source_snapshot"] == source.artifact
    assert artifact["observation_binding"]["canonical_json_digest"] == source.source_digest
    assert artifact["operation_ref"] == OPERATION_REF
    assert artifact["execution_ref"] != artifact["result_id"]
    assert "verification_id" not in artifact
    assert artifact["authority"]["independent_verification"] == "not_performed"
    assert artifact["authority"]["may_authorize"] is False
    result_id = artifact.pop("result_id")
    content = json.dumps(artifact, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()
    assert result_id == "sha256:" + sha256(RESULT_SCHEMA.encode() + b"\0" + content).hexdigest()


def test_result_identity_changes_for_replay_occurrence(validator_repo):
    source = imported(validator_repo)
    first = exported(validator_repo, source)
    second = exported(validator_repo, source, execution_ref="example:execution-2")
    assert first["components"] == second["components"]
    assert first["result_id"] != second["result_id"]
    assert first["numerical_result_id"] == second["numerical_result_id"]
    assert first["state_id"] == second["state_id"]
    third = exported(validator_repo, source, created_at="2026-09-20T12:00:05Z")
    assert third["result_id"] != first["result_id"]
    assert third["numerical_result_id"] == first["numerical_result_id"]


def test_full_replay_binding_reproduces_result_without_external_model_configuration(validator_repo):
    source = imported(validator_repo)
    artifact = exported(validator_repo, source)
    binding = artifact["replay_binding"]
    assert binding["status"] == "local_replay_matched"
    assert binding["verification_independence"] == "not_established"
    replayed = replay_estimate(binding["snapshot"])
    assert replayed.numerical_result_id == artifact["numerical_result_id"]
    assert replayed.state_id == artifact["state_id"]
    assert binding["snapshot"]["prior"]["covariance"] == [[1.0, 0.2], [0.2, 2.0]]
    assert binding["snapshot"]["model"]["matrix"] == [[1.0, 0.0], [0.0, 1.0]]
    encoded = json.dumps(binding["snapshot"], sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False, allow_nan=False).encode()
    assert binding["canonical_json_digest"] == "sha256:" + sha256(encoded).hexdigest()


@pytest.mark.parametrize("field,value", [
    ("mean", [100, 200]),
    ("covariance", [[2, 0], [0, 2]]),
    ("nis", 100),
    ("observation_model_id", "model:forged"),
    ("state_id", "state:forged"),
    ("replay_json", None),
])
def test_export_refuses_result_mutation_or_unbound_replay(validator_repo, field, value):
    source = imported(validator_repo)
    forged = replace(estimated(source), **{field: value})
    with pytest.raises(ValueError, match="replay"):
        exported(validator_repo, source, forged)


def test_numerical_identity_excludes_observation_receipt_identity(validator_repo):
    first = imported(validator_repo)
    altered_artifact = observation_artifact()
    altered_artifact["batch_id"] = "example:second-occurrence"
    second = imported(validator_repo, altered_artifact)
    one, two = exported(validator_repo, first), exported(validator_repo, second)
    assert one["numerical_result_id"] == two["numerical_result_id"]
    assert one["state_id"] != two["state_id"]
    assert one["result_id"] != two["result_id"]


def test_export_cannot_attach_same_id_different_covariance_observation(validator_repo):
    original = imported(validator_repo)
    altered_artifact = observation_artifact()
    altered_artifact["covariance"]["matrix"] = [[0.4, 0], [0, 0.9]]
    altered = imported(validator_repo, altered_artifact)
    with pytest.raises(ValueError, match="replay observation"):
        exported(validator_repo, altered, estimated(original))


@pytest.mark.parametrize("field,value", [
    ("observation_id", "example:unrelated-observation"),
    ("evidence_refs", ("example:unrelated-evidence",)),
    ("time", 90.0),
    ("prior_state_id", "example:synthetic-position"),
])
def test_result_cannot_reattach_unrelated_source(validator_repo, field, value):
    source = imported(validator_repo)
    estimate = replace(estimated(source), **{field: value})
    with pytest.raises(ValueError, match="references|identity"):
        exported(validator_repo, source, estimate)


def test_result_refuses_changed_numerical_source_wrapper(validator_repo):
    source = imported(validator_repo)
    original = source.observation
    changed = Observation(original.time, [90.0, 90.0], original.covariance,
                          original.frame_id, original.units, original.observation_id,
                          original.evidence_refs)
    forged = replace(source, observation=changed)
    with pytest.raises(ValueError, match="retained source snapshot"):
        exported(validator_repo, forged)


@pytest.mark.parametrize("execution_ref", ["example:prior", "example:synthetic-position", OPERATION_REF])
def test_execution_identity_cannot_be_an_input_or_operation(validator_repo, execution_ref):
    with pytest.raises(ValueError, match="distinct"):
        exported(validator_repo, imported(validator_repo), execution_ref=execution_ref)


def test_checker_package_initializer_is_not_imported(validator_repo, tmp_path):
    original = (validator_repo / CHECKER_PATH).read_bytes()
    assert sha256(original.replace(b"\r\n", b"\n")).hexdigest() == CHECKER_SHA256
    source = tmp_path / CHECKER_PATH
    source.parent.mkdir()
    source.write_bytes(original)
    (source.parent / "__init__.py").write_text("raise AssertionError('must not import package')")
    assert imported(tmp_path).observation.time == 2.0


def test_actual_ciw_cli_inspects_result_without_promoting_authority(validator_repo, tmp_path):
    ciw_repo = os.environ.get("GSIE_CIW_REPO")
    if not ciw_repo:
        pytest.skip("Set GSIE_CIW_REPO to the documented CIW checkout")
    source = imported(validator_repo)
    artifact = exported(validator_repo, source)
    paths = [tmp_path / "observation.json", tmp_path / "estimate.json"]
    for path, item in zip(paths, (source.artifact, artifact)):
        path.write_text(json.dumps(item, indent=2), encoding="utf-8")
    original = [path.read_bytes() for path in paths]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(Path(ciw_repo).resolve() / "src")
    result = subprocess.run(
        [sys.executable, "-m", "ciw", "exchange", "inspect", *map(str, paths),
         "--validator-repo", str(validator_repo.resolve())],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "conformant"
    assert report["artifacts"][1]["artifact"] == artifact
    assert report["authority"]["native_workspace_import"] == "not_performed"
    assert report["authority"]["may_authorize"] is False
    assert report["authority"]["verification_independence"] == "not_established"
    assert any(link["to"] == source.observation.observation_id
               and link["status"] == "matched_supplied_reference" for link in report["links"])
    assert [path.read_bytes() for path in paths] == original
    artifact["components"][0]["value"] += 0.5
    paths[1].write_text(json.dumps(artifact), encoding="utf-8")
    refused = subprocess.run(
        [sys.executable, "-m", "ciw", "exchange", "inspect", *map(str, paths),
         "--validator-repo", str(validator_repo.resolve())],
        cwd=tmp_path, env=environment, capture_output=True, text=True, timeout=30,
    )
    assert refused.returncode == 2
    assert "result_id does not match" in refused.stderr
    assert refused.stdout == ""
