import copy
import importlib.util
from pathlib import Path

import pytest

contracts = pytest.importorskip("state_estimation_testbed.contracts")

from oit.exchange import export_result


def example():
    path = Path(__file__).parents[1] / "examples" / "exchange.py"
    spec = importlib.util.spec_from_file_location("oit_exchange_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def export_arguments(artifact):
    return {
        "operation_id": artifact["operation_id"],
        "execution_ref": artifact["execution_ref"],
        "source_revision": artifact["computation"]["source_revision"],
        "created_at": artifact["created_at"],
        "input_refs": artifact["input_refs"],
        "model_refs": artifact["model_refs"],
        "calibration_refs": artifact["calibration_refs"],
        "input_payload": artifact["computation"]["inputs"],
        "numerical_result": artifact["computation"]["numerical_result"],
        "components": artifact["components"],
        "covariance": artifact["covariance"],
        "applicability": artifact["applicability"],
    }


def test_real_diagnostic_export_conforms_without_implying_verification():
    artifact = example().build_artifact()
    validated = contracts.validate_result_artifact(artifact)
    assert validated.effective_rank is None
    assert artifact["components"][0]["value"] == 2
    assert artifact["computation"]["numerical_result"]["observability_matrix"] == [[1, 0], [1, 1]]
    assert artifact["verification_refs"] == []
    assert artifact["computation"]["source_revision_status"] == "caller_supplied_unattested"


def test_execution_result_and_input_identities_have_distinct_semantics():
    first = example().build_artifact("execution:first")
    repeated = example().build_artifact("execution:first")
    second = example().build_artifact("execution:second")
    assert first == repeated
    assert first["result_id"] != second["result_id"]
    assert first["computation"]["input_digest"] == second["computation"]["input_digest"]
    arguments = export_arguments(first)
    arguments["input_payload"]["rank_rtol"] = 1e-10
    changed = export_result(**arguments)
    assert first["computation"]["input_digest"] != changed["computation"]["input_digest"]


def test_export_copies_inputs_without_mutation():
    arguments = export_arguments(example().build_artifact())
    snapshot = copy.deepcopy(arguments)
    artifact = export_result(**arguments)
    assert arguments == snapshot
    arguments["input_payload"]["transition"][0][0] = 9
    assert artifact["computation"]["inputs"]["transition"][0][0] == 1


def test_rejects_collapsed_identity_and_nonfinite_result():
    arguments = export_arguments(example().build_artifact())
    arguments["execution_ref"] = arguments["operation_id"]
    with pytest.raises(ValueError, match="distinct"):
        export_result(**arguments)
    arguments = export_arguments(example().build_artifact())
    arguments["numerical_result"]["condition"] = float("inf")
    with pytest.raises(ValueError):
        export_result(**arguments)
    arguments = export_arguments(example().build_artifact())
    arguments["covariance"]["variables"] = ["unrelated", "state_dimension"]
    with pytest.raises(ValueError):
        export_result(**arguments)
