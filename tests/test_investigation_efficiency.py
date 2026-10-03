from copy import deepcopy
import json
import subprocess
import sys

import pytest

from ciw.investigation_efficiency import (
    compare_trials, inspect_trial, trial_from_spec, validate_trial,
)


def ref(char):
    return "sha256:" + char * 64


def metric(value, unit, provenance="MEASURED", source="a"):
    return {
        "value": value,
        "unit": unit,
        "provenance": provenance if value is not None else "UNKNOWN",
        "source_ref": ref(source) if value is not None else None,
    }


def metrics(*, context=4000, human=600.0, recomputed=8, reused=0, cost=1.0):
    return {
        "raw_evidence_bytes": metric(8_000_000, "bytes"),
        "retrieved_evidence_bytes": metric(2_000_000, "bytes"),
        "instrument_input_bytes": metric(500_000, "bytes"),
        "agent_context_tokens": metric(context, "tokens"),
        "input_tokens": metric(context, "tokens"),
        "output_tokens": metric(500, "tokens"),
        "deterministic_operation_calls": metric(8, "count"),
        "reused_operation_calls": metric(reused, "count"),
        "recomputed_operation_calls": metric(recomputed, "count"),
        "local_model_calls": metric(0, "count"),
        "remote_model_calls": metric(1, "count"),
        "compute_wall_seconds": metric(20.0, "seconds"),
        "human_active_seconds": metric(human, "seconds", "HUMAN_LOGGED"),
        "human_interventions": metric(3, "count", "HUMAN_LOGGED"),
        "accepted_outputs": metric(1, "count"),
        "rejected_outputs": metric(0, "count"),
        "errors": metric(0, "count"),
        "retries": metric(0, "count"),
        "model_cost_usd": metric(cost, "usd", "PROVIDER_REPORTED"),
    }


def spec(method="CONVENTIONAL", *, metrics_value=None, selected=100):
    return {
        "task_id": "pump-efficiency-fixture",
        "domain": "PHYSICAL_SYSTEM",
        "method": method,
        "acceptance_policy_id": "fixture-policy-v1",
        "outcome_class": "same-accepted-diagnosis",
        "accepted": True,
        "representation": {
            "source_representation_ref": ref("1"),
            "selected_representation_ref": ref("2" if method == "NET" else "3"),
            "source_item_count": 1000,
            "selected_item_count": selected,
            "reduction_method": "fixture-explicit-selection",
            "required_preservation_checks": [
                {"check_id": "output", "kind": "OUTPUT", "status": "PASS", "source_ref": ref("4")},
                {"check_id": "invariant", "kind": "INVARIANT", "status": "PASS", "source_ref": ref("5")},
                {"check_id": "epistemic", "kind": "EPISTEMIC", "status": "PASS", "source_ref": ref("6")},
                {"check_id": "provenance", "kind": "PROVENANCE", "status": "PASS", "source_ref": ref("7")},
            ],
        },
        "metrics": metrics_value or metrics(),
        "evidence_refs": [ref("8")],
        "notes": "Synthetic contract fixture only.",
    }


def test_trial_retains_measurement_provenance_and_no_multiplier_claim():
    value = trial_from_spec(spec())
    validate_trial(value)
    inspected = inspect_trial(value)
    assert inspected["accepted"] is True
    assert inspected["required_preservation_checks_pass"] is True
    assert inspected["derived"]["representation_fraction"] == pytest.approx(0.1)
    assert value["claims"]["causal_productivity_claim"] is False
    assert value["claims"]["general_scientific_equivalence"] is False


def test_unknown_metrics_remain_unknown_and_do_not_get_imputed():
    m = metrics()
    m["model_cost_usd"] = metric(None, "usd")
    m["human_active_seconds"] = metric(None, "seconds")
    value = trial_from_spec(spec(metrics_value=m))
    inspected = inspect_trial(value)
    assert "model_cost_usd" in inspected["unknown_metrics"]
    assert "human_active_seconds" in inspected["unknown_metrics"]
    assert inspected["derived"]["accepted_outputs_per_human_hour"] is None


def test_comparison_reports_metric_ratios_without_aggregate_winner():
    baseline = trial_from_spec(spec("CONVENTIONAL", metrics_value=metrics(context=8000, human=1200, recomputed=8, reused=0, cost=2.0), selected=1000))
    candidate = trial_from_spec(spec("NET", metrics_value=metrics(context=2000, human=300, recomputed=2, reused=6, cost=0.5), selected=100))
    value = compare_trials(baseline, candidate)
    assert value["metric_comparisons"]["agent_context_tokens"]["candidate_over_baseline"] == pytest.approx(0.25)
    assert value["candidate_derived"]["operation_reuse_fraction"] == pytest.approx(0.75)
    assert value["candidate_derived"]["accepted_outputs_per_human_hour"] == pytest.approx(12.0)
    assert value["claims"]["aggregate_winner"] is False
    assert value["claims"]["general_domain_multiplier"] is False


def test_comparison_refuses_different_task_or_acceptance_policy():
    left = trial_from_spec(spec("CONVENTIONAL"))
    right_spec = spec("NET")
    right_spec["task_id"] = "different"
    right = trial_from_spec(right_spec)
    with pytest.raises(ValueError, match="task_id"):
        compare_trials(left, right)


def test_comparison_refuses_failed_preservation_check():
    left = trial_from_spec(spec("CONVENTIONAL"))
    right_spec = spec("NET")
    right_spec["representation"]["required_preservation_checks"][1]["status"] = "FAIL"
    right = trial_from_spec(right_spec)
    with pytest.raises(ValueError, match="preservation"):
        compare_trials(left, right)


def test_comparison_refuses_unaccepted_outcome():
    left = trial_from_spec(spec("CONVENTIONAL"))
    right_spec = spec("NET")
    right_spec["accepted"] = False
    right = trial_from_spec(right_spec)
    with pytest.raises(ValueError, match="acceptance"):
        compare_trials(left, right)


def test_known_metric_requires_source_reference():
    value = spec()
    value["metrics"]["agent_context_tokens"]["source_ref"] = None
    with pytest.raises(ValueError, match="source reference"):
        trial_from_spec(value)


def test_unknown_metric_cannot_smuggle_a_value():
    value = spec()
    value["metrics"]["model_cost_usd"] = {
        "value": 99.0, "unit": "usd", "provenance": "UNKNOWN", "source_ref": None}
    with pytest.raises(ValueError, match="Unknown metric"):
        trial_from_spec(value)


def test_discrete_metrics_refuse_fractional_counts():
    value = spec()
    value["metrics"]["remote_model_calls"] = metric(1.5, "count")
    with pytest.raises(ValueError, match="integer"):
        trial_from_spec(value)


def test_tamper_breaks_trial_integrity():
    value = trial_from_spec(spec())
    value["accepted"] = False
    with pytest.raises(ValueError):
        validate_trial(value)


def test_cli_create_compare_and_inspect(tmp_path):
    left_spec = tmp_path / "left-spec.json"
    right_spec = tmp_path / "right-spec.json"
    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    comparison = tmp_path / "comparison.json"
    left_spec.write_text(json.dumps(spec("CONVENTIONAL", metrics_value=metrics(context=8000, human=1200), selected=1000)))
    right_spec.write_text(json.dumps(spec("NET", metrics_value=metrics(context=2000, human=300, recomputed=2, reused=6), selected=100)))
    subprocess.run([sys.executable, "-m", "ciw.net", "efficiency", "create", str(left_spec), "--output", str(left)], cwd=tmp_path, check=True)
    subprocess.run([sys.executable, "-m", "ciw.net", "efficiency", "create", str(right_spec), "--output", str(right)], cwd=tmp_path, check=True)
    subprocess.run([sys.executable, "-m", "ciw.net", "efficiency", "compare", str(left), str(right), "--output", str(comparison)], cwd=tmp_path, check=True)
    result = json.loads(subprocess.check_output([sys.executable, "-m", "ciw.net", "efficiency", "inspect-comparison", str(comparison)], cwd=tmp_path, text=True))
    assert result["aggregate_winner"] is False
    assert result["general_domain_multiplier"] is False
