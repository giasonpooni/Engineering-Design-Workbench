import json
from pathlib import Path

import pytest

from set_lcm.bridge.calibrated_observable import (
    DeclarationRefusal, OPERATION_ID, declare, evaluate, experiment_digest, validate_experiment,
)


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    return json.loads((ROOT / "examples/calibrated_observable_two_reservoir.v1.json").read_text())


def test_two_reservoir_declaration_is_typed_content_bound_and_deterministic():
    experiment = fixture()
    validated = validate_experiment(experiment)
    result = declare(experiment, "execution:synthetic:1")
    assert result["operation_id"] == OPERATION_ID
    assert result["channel_order"] == ["tank-1.mass", "tank-2.mass"]
    assert result["experiment_digest"] == experiment_digest(validated)
    assert declare(experiment, "execution:synthetic:1") == result
    validated["channels"][0]["observation"]["indicated_value"] = 0.0
    assert experiment["channels"][0]["observation"]["indicated_value"] == 51.0


def test_missing_clock_map_and_reordered_state_contracts_refuse():
    experiment = fixture()
    experiment["channels"][0]["clock_model"]["synchronization_evidence_ids"] = []
    with pytest.raises(DeclarationRefusal, match="synchronization evidence"):
        validate_experiment(experiment)
    experiment = fixture()
    experiment["configuration"]["fdir"]["variable_order"].reverse()
    with pytest.raises(DeclarationRefusal, match="FDIR residual order"):
        validate_experiment(experiment)


def test_unknown_cross_covariance_is_retained_for_downstream_refusal():
    experiment = fixture()
    experiment["calibrated_covariance"]["cross_covariance_policy"] = "unknown"
    assert validate_experiment(experiment)["calibrated_covariance"]["cross_covariance_policy"] == "unknown"


@pytest.mark.parametrize("operation", ["alignment", "observability", "gsie", "cbsr", "fdir"])
def test_malformed_operation_configuration_is_a_structured_refusal(operation):
    experiment = fixture()
    experiment["configuration"][operation] = []
    response = evaluate({"schema": "ciw.adapter-request.v1", "operation_id": OPERATION_ID,
                         "inputs": {"experiment": experiment, "execution_id": "execution:1"}})
    assert response["status"] == "refused"
    assert response["refusal"]["code"] == "invalid_experiment"


def test_missing_independence_or_nonstationary_timing_model_is_refused():
    experiment = fixture()
    del experiment["configuration"]["gsie"]["prior_measurement_crosscov_policy"]
    with pytest.raises(DeclarationRefusal, match="independence"):
        validate_experiment(experiment)
    experiment = fixture()
    experiment["configuration"]["gsie"]["dynamics"]["process_covariance"][0][0] = 1.0
    with pytest.raises(DeclarationRefusal, match="stationary hold"):
        validate_experiment(experiment)


def test_clock_map_cannot_relabel_the_retained_raw_clock_frame():
    experiment = fixture()
    experiment["channels"][0]["clock_model"]["source_frame"]["clock_id"] = "other-clock"
    with pytest.raises(DeclarationRefusal, match="clock_frame differs") as failure:
        validate_experiment(experiment)
    assert failure.value.code == "clock_frame_mismatch"


@pytest.mark.parametrize("identity", [[], {}, 1, ""])
def test_channel_identity_is_strictly_typed(identity):
    experiment = fixture()
    experiment["channels"][0]["channel_id"] = identity
    with pytest.raises(DeclarationRefusal, match="identities"):
        validate_experiment(experiment)
