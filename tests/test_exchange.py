import copy
from pathlib import Path
import runpy

import pytest

pytest.importorskip("state_estimation_testbed.contracts")
from state_estimation_testbed.contracts import validate_result_artifact
from tbrt.exchange import export_result


def arguments():
    module = runpy.run_path(str(Path(__file__).resolve().parents[1] / "examples" / "exchange.py"))
    return module["build_export_arguments"]()


def test_real_reconciliation_exports_existing_contract_and_propagated_variance():
    artifact = export_result(**arguments())
    validation = validate_result_artifact(artifact)
    assert validation.dimension == 1
    assert artifact["schema"] == "notation.instrument.result-artifact.v1"
    numerical = artifact["computation"]["numerical_result"]
    assert artifact["components"][0]["value"] == numerical["event_time_delta"]
    assert artifact["covariance"]["matrix"] == [[numerical["variance"]]]
    assert numerical["model"]["reference_origin"] == 200.0
    assert numerical["model"]["reference_frame"]["time_scale"] == "reference-monotonic"
    assert artifact["verification_refs"] == []


def test_export_snapshots_complete_inputs_without_mutation():
    supplied = arguments()
    before = copy.deepcopy(supplied)
    artifact = export_result(**supplied)
    assert supplied == before
    supplied["input_payload"]["observation"]["device_time"] = 9000.0
    supplied["numerical_result"]["variance"] = 999.0
    assert artifact["computation"]["inputs"]["observation"]["device_time"] == 1003.0
    assert artifact["computation"]["numerical_result"]["variance"] != 999.0


def test_execution_identity_changes_result_but_not_input_identity():
    supplied = arguments()
    first = export_result(**supplied)
    second = export_result(**(supplied | {"execution_ref": "synthetic-execution-0002"}))
    assert first["result_id"] != second["result_id"]
    assert first["computation"]["input_digest"] == second["computation"]["input_digest"]
    assert first["result_id"] != first["execution_ref"]
    assert first["result_id"] not in first["input_refs"]
    assert export_result(**supplied) == first


def test_aliasing_execution_with_evidence_is_rejected():
    supplied = arguments()
    supplied["execution_ref"] = supplied["input_refs"][0]
    with pytest.raises(ValueError, match="distinct"):
        export_result(**supplied)


def test_invalid_exported_covariance_is_rejected():
    supplied = arguments()
    supplied["covariance"]["matrix"] = [[-1.0]]
    with pytest.raises(ValueError, match="negative variance"):
        export_result(**supplied)
