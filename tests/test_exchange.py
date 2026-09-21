import copy
import json
from pathlib import Path
import runpy

import pytest

pytest.importorskip("state_estimation_testbed.contracts")
from state_estimation_testbed.contracts import validate_result_artifact

from edspt.exchange import SET_REVISION, export_result


def arguments():
    return runpy.run_path(str(Path(__file__).parents[1] / "examples" / "exchange.py"))["example_arguments"]()


def test_real_ranking_conforms_and_retains_full_numerical_result():
    artifact = export_result(**arguments())
    validation = validate_result_artifact(artifact)
    assert validation.effective_rank is None
    assert artifact["covariance"]["status"] == "not_applicable"
    assert artifact["verification_refs"] == []
    result = artifact["computation"]["numerical_result"]
    assert result["selected_candidate_id"] == "two-axis"
    assert result["scores"][0]["status"] == "singular"
    assert result["scores"][0]["d_opt_logdet"] is None
    assert artifact["computation"]["source_revision_status"] == "caller_supplied_unattested"
    assert SET_REVISION == "c4d39c755187796ce2c72552a90454871c516c8f"
    json.dumps(artifact, allow_nan=False)


def test_content_execution_and_operation_identities_stay_distinct():
    args = arguments()
    first = export_result(**args)
    assert first == export_result(**args)
    args["execution_ref"] = "execution:edspt:second-synthetic-run"
    second = export_result(**args)
    assert first["result_id"] != second["result_id"]
    assert first["computation"]["input_digest"] == second["computation"]["input_digest"]
    assert len({first["operation_id"], first["execution_ref"], first["result_id"], *first["input_refs"]}) == 4
    args["input_payload"]["criterion"] = "a_opt"
    third = export_result(**args)
    assert second["computation"]["input_digest"] != third["computation"]["input_digest"]


def test_export_does_not_mutate_or_retain_mutable_input_aliases():
    args = arguments()
    before = copy.deepcopy(args)
    artifact = export_result(**args)
    assert args == before
    saved = copy.deepcopy(artifact)
    args["numerical_result"]["scores"].clear()
    args["input_payload"]["candidates"].clear()
    args["components"][0]["value"] = 999
    assert artifact == saved


@pytest.mark.parametrize("field,value", [
    ("source_revision", "main"),
    ("created_at", "2026-09-20"),
    ("input_refs", []),
    ("numerical_result", {"score": float("nan")}),
    ("components", [{"name": "count", "value": None, "unit": "1"}]),
])
def test_invalid_explicit_mapping_is_rejected(field, value):
    args = arguments()
    args[field] = value
    with pytest.raises(ValueError):
        export_result(**args)


def test_covariance_mapping_cannot_silently_disagree_with_components():
    args = arguments()
    args["covariance"]["variables"] = ["unrelated"]
    with pytest.raises(ValueError):
        export_result(**args)


def test_execution_cannot_impersonate_evidence():
    args = arguments()
    args["execution_ref"] = args["input_refs"][0]
    with pytest.raises(ValueError, match="distinct"):
        export_result(**args)
