# SPDX-License-Identifier: MPL-2.0
from copy import deepcopy
from pathlib import Path
import runpy

import pytest

pytest.importorskip("state_estimation_testbed.contracts", reason="Install the optional pinned exchange dependency")
from state_estimation_testbed.contracts import validate_result_artifact

from fdir.exchange import export_result


def arguments():
    example = Path(__file__).resolve().parents[1] / "examples" / "exchange.py"
    return runpy.run_path(str(example))["example_arguments"]()


def test_exchange_real_validator_and_scientific_mapping():
    artifact = export_result(**arguments())
    validation = validate_result_artifact(artifact)
    assert validation.dimension == 1
    assert validation.effective_rank is None
    assert artifact["components"] == [{"name": "nis", "unit": "1", "value": 2.0}]
    assert artifact["covariance"]["status"] == "not_applicable"
    assert "matrix" not in artifact["covariance"]
    assert artifact["computation"]["inputs"]["innovation_covariance"] == [[4., 2.], [2., 5.]]
    assert artifact["computation"]["numerical_result"]["raw_residual"] == [2., 3.]
    assert artifact["computation"]["numerical_result"]["whitened_residual"] == [1., 1.]
    assert artifact["verification_refs"] == []
    assert artifact["computation"]["source_revision_status"] == "caller_supplied_unattested"


def test_identity_tracks_execution_and_parameters_separately():
    kwargs = arguments()
    first = export_result(**kwargs)
    assert export_result(**kwargs) == first
    second = export_result(**{**kwargs, "execution_ref": "execution:synthetic-fdir-example:0002"})
    assert first["result_id"] != second["result_id"]
    assert first["computation"]["input_digest"] == second["computation"]["input_digest"]
    changed = deepcopy(kwargs)
    changed["input_payload"]["threshold"] = 5.
    third = export_result(**changed)
    assert first["computation"]["input_digest"] != third["computation"]["input_digest"]
    assert first["result_id"] != third["result_id"]
    assert first["operation_id"] not in [first["execution_ref"], first["result_id"], *first["input_refs"]]


def test_export_snapshots_without_mutating_caller_data():
    kwargs = arguments()
    before = deepcopy(kwargs)
    artifact = export_result(**kwargs)
    assert kwargs == before
    kwargs["input_payload"]["residual"][0] = 999.
    kwargs["components"][0]["value"] = 999.
    assert artifact["computation"]["inputs"]["residual"][0] == 2.
    assert artifact["components"][0]["value"] == 2.
    artifact["computation"]["inputs"]["innovation_covariance"][0][0] = 999.
    assert kwargs["input_payload"]["innovation_covariance"][0][0] == 4.


@pytest.mark.parametrize("change", [
    {"execution_ref": "operation:fdir:nis-cholesky.v1"},
    {"operation_id": "fixture:gsie-innovation:0001"},
    {"source_revision": "main"},
    {"input_refs": []},
    {"input_payload": {"residual": [float("nan")]}},
    {"created_at": "not-a-timestamp"},
    {"components": [{"name": "wrong-order", "unit": "1", "value": 2.}]},
])
def test_invalid_export_claims_rejected(change):
    with pytest.raises(ValueError):
        export_result(**{**arguments(), **change})
