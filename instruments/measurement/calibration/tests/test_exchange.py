from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest

contracts = pytest.importorskip("state_estimation_testbed.contracts")

from mcur.exchange import export_result


@pytest.fixture
def artifact():
    path = Path(__file__).parents[1] / "examples" / "exchange.py"
    spec = importlib.util.spec_from_file_location("mcur_exchange_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_artifact()


def _arguments(artifact):
    return {
        "operation_id": artifact["operation_id"], "execution_ref": artifact["execution_ref"],
        "source_revision": artifact["computation"]["source_revision"], "created_at": artifact["created_at"],
        "input_refs": artifact["input_refs"], "input_payload": artifact["computation"]["inputs"],
        "numerical_result": artifact["computation"]["numerical_result"],
        "components": artifact["components"], "covariance": artifact["covariance"],
        "applicability": artifact["applicability"], "model_refs": artifact["model_refs"],
        "calibration_refs": artifact["calibration_refs"],
    }


def test_real_set_contract_with_preserved_calibration_and_source(artifact):
    validation = contracts.validate_result_artifact(artifact)
    assert validation.dimension == 1
    assert artifact["components"][0]["value"] == 7.0
    assert artifact["covariance"]["matrix"][0][0] == pytest.approx(22.35)
    assert artifact["covariance"]["status"] == "propagated"
    assert artifact["covariance"]["calibration_refs"] == artifact["calibration_refs"]
    inputs = artifact["computation"]["inputs"]
    numerical = artifact["computation"]["numerical_result"]
    assert inputs["observation"]["raw_value"] == numerical["raw_value"] == 300.0
    assert inputs["observation"]["indicated_value"] == numerical["indicated_value"] == 3.0
    assert numerical["corrected_value"] == 7.0
    assert inputs["profile"]["coefficient_covariance"] == [[0.25, 0.05], [0.05, 1.0]]
    assert numerical["reference_ids"] == inputs["profile"]["reference_ids"]
    assert artifact["verification_refs"] == []
    assert artifact["computation"]["source_revision_status"] == "caller_supplied_unattested"


def test_identity_changes_with_execution_but_input_digest_does_not(artifact):
    arguments = _arguments(artifact)
    assert export_result(**arguments) == artifact
    arguments["execution_ref"] = "execution:synthetic:2"
    other = export_result(**arguments)
    assert other["result_id"] != artifact["result_id"]
    assert other["computation"]["input_digest"] == artifact["computation"]["input_digest"]
    assert len({artifact["operation_id"], artifact["execution_ref"], artifact["result_id"], *artifact["input_refs"]}) == 5


def test_export_detaches_input_and_covariance(artifact):
    arguments = _arguments(deepcopy(artifact))
    exported = export_result(**arguments)
    arguments["input_payload"]["observation"]["indicated_value"] = 999.0
    arguments["covariance"]["matrix"][0][0] = 0.0
    assert exported["computation"]["inputs"]["observation"]["indicated_value"] == 3.0
    assert exported["covariance"]["matrix"][0][0] == pytest.approx(22.35)


def test_export_rejects_identity_collision_and_bad_covariance(artifact):
    arguments = _arguments(deepcopy(artifact))
    arguments["execution_ref"] = arguments["operation_id"]
    with pytest.raises(ValueError, match="distinct"):
        export_result(**arguments)
    arguments = _arguments(deepcopy(artifact))
    arguments["covariance"]["matrix"][0][0] = -1e-200
    with pytest.raises(ValueError, match="negative variance"):
        export_result(**arguments)


def test_export_cannot_drop_covariance_calibration_refs(artifact):
    arguments = _arguments(deepcopy(artifact))
    arguments["calibration_refs"] = []
    with pytest.raises(ValueError, match="calibration_refs"):
        export_result(**arguments)
