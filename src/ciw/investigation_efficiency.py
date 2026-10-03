"""Measured investigation-efficiency records and refusal-safe comparisons.

The purpose is empirical: test whether a reduced/structured investigation
representation preserves declared required outputs/invariants while reducing
context, recomputation, or human translation. Unknown quantities remain unknown.
"""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

from .control_contracts import content_ref, detached, keys, record, text
from .operations.runner import check_seal

DOMAINS = {"PHYSICAL_SYSTEM", "SCIENTIFIC_COMPUTING", "CREATIVE_PRODUCTION", "OTHER"}
METHODS = {"CONVENTIONAL", "LLM_CENTRIC", "NET"}
PROVENANCE = {"MEASURED", "PROVIDER_REPORTED", "HUMAN_LOGGED", "DECLARED", "UNKNOWN"}
CHECK_KINDS = {"OUTPUT", "INVARIANT", "EPISTEMIC", "PROVENANCE"}
CHECK_STATUS = {"PASS", "FAIL", "NOT_MEASURED"}

METRICS = {
    "raw_evidence_bytes": "bytes",
    "retrieved_evidence_bytes": "bytes",
    "instrument_input_bytes": "bytes",
    "agent_context_tokens": "tokens",
    "input_tokens": "tokens",
    "output_tokens": "tokens",
    "deterministic_operation_calls": "count",
    "reused_operation_calls": "count",
    "recomputed_operation_calls": "count",
    "local_model_calls": "count",
    "remote_model_calls": "count",
    "compute_wall_seconds": "seconds",
    "human_active_seconds": "seconds",
    "human_interventions": "count",
    "accepted_outputs": "count",
    "rejected_outputs": "count",
    "errors": "count",
    "retries": "count",
    "model_cost_usd": "usd",
}
MAX_REFS = 128


def _measurement(value: Any, expected_unit: str) -> dict:
    keys(value, {"value", "unit", "provenance", "source_ref"})
    if value["unit"] != expected_unit:
        raise ValueError("Metric unit differs from schema")
    if value["provenance"] not in PROVENANCE:
        raise ValueError("Unknown metric provenance")
    if value["provenance"] == "UNKNOWN":
        if value["value"] is not None or value["source_ref"] is not None:
            raise ValueError("Unknown metric must not carry a value/source")
        return deepcopy(value)

    raw = value["value"]
    if type(raw) not in (int, float) or isinstance(raw, bool):
        raise ValueError("Known metric requires a finite nonnegative number")
    numeric = float(raw)
    if not math.isfinite(numeric) or numeric < 0 or numeric > 1e18:
        raise ValueError("Known metric requires a finite nonnegative number")
    if expected_unit in {"bytes", "tokens", "count"} and numeric != int(numeric):
        raise ValueError("Discrete metric must be an integer")
    if value["source_ref"] is None:
        raise ValueError("Known metric requires a retained source reference")
    content_ref(value["source_ref"])
    return {
        "value": int(numeric) if expected_unit in {"bytes", "tokens", "count"} else numeric,
        "unit": expected_unit,
        "provenance": value["provenance"],
        "source_ref": value["source_ref"],
    }


def _metrics(value: Any) -> dict:
    if type(value) is not dict or set(value) != set(METRICS):
        raise ValueError("Efficiency metrics must contain the complete V1 metric set")
    return {name: _measurement(value[name], unit) for name, unit in METRICS.items()}


def _representation(value: Any) -> dict:
    keys(value, {
        "source_representation_ref", "selected_representation_ref",
        "source_item_count", "selected_item_count", "reduction_method",
        "required_preservation_checks",
    })
    content_ref(value["source_representation_ref"])
    content_ref(value["selected_representation_ref"])
    for name in ("source_item_count", "selected_item_count"):
        item = value[name]
        if type(item) is not int or item < 1 or item > 10**9:
            raise ValueError("Representation item counts must be positive bounded integers")
    if value["selected_item_count"] > value["source_item_count"]:
        raise ValueError("Selected representation cannot contain more items than its declared source")
    text(value["reduction_method"])
    checks = value["required_preservation_checks"]
    if type(checks) is not list or not 1 <= len(checks) <= 128:
        raise ValueError("Require 1..128 preservation checks")
    seen = set()
    normalized = []
    for check in checks:
        keys(check, {"check_id", "kind", "status", "source_ref"})
        check_id = text(check["check_id"])
        if check_id in seen:
            raise ValueError("Duplicate preservation check")
        seen.add(check_id)
        if check["kind"] not in CHECK_KINDS:
            raise ValueError("Unknown preservation-check kind")
        if check["status"] not in CHECK_STATUS:
            raise ValueError("Unknown preservation-check status")
        source_ref = check["source_ref"]
        if check["status"] == "NOT_MEASURED":
            if source_ref is not None:
                raise ValueError("Unmeasured preservation check cannot cite result evidence")
        else:
            if source_ref is None:
                raise ValueError("Measured preservation check requires evidence")
            content_ref(source_ref)
        normalized.append({
            "check_id": check_id,
            "kind": check["kind"],
            "status": check["status"],
            "source_ref": source_ref,
        })
    return {
        "source_representation_ref": value["source_representation_ref"],
        "selected_representation_ref": value["selected_representation_ref"],
        "source_item_count": value["source_item_count"],
        "selected_item_count": value["selected_item_count"],
        "reduction_method": value["reduction_method"],
        "required_preservation_checks": normalized,
    }


def _refs(value: Any) -> list[str]:
    if type(value) is not list or len(value) > MAX_REFS:
        raise ValueError("Evidence references must be a bounded list")
    refs = [content_ref(item) for item in value]
    if len(refs) != len(set(refs)):
        raise ValueError("Duplicate evidence reference")
    return refs


def trial_from_spec(spec: dict) -> dict:
    keys(spec, {
        "task_id", "domain", "method", "acceptance_policy_id", "outcome_class",
        "accepted", "representation", "metrics", "evidence_refs", "notes",
    })
    if spec["domain"] not in DOMAINS:
        raise ValueError("Unknown investigation domain")
    if spec["method"] not in METHODS:
        raise ValueError("Unknown investigation method")
    if type(spec["accepted"]) is not bool:
        raise ValueError("accepted must be boolean")
    notes = spec["notes"]
    if type(notes) is not str or len(notes) > 4096:
        raise ValueError("notes must be bounded text")
    value = record(
        "investigation-efficiency",
        task_id=text(spec["task_id"]),
        domain=spec["domain"],
        method=spec["method"],
        acceptance_policy_id=text(spec["acceptance_policy_id"]),
        outcome_class=text(spec["outcome_class"]),
        accepted=spec["accepted"],
        representation=_representation(spec["representation"]),
        metrics=_metrics(spec["metrics"]),
        evidence_refs=_refs(spec["evidence_refs"]),
        notes=notes,
        claims={
            "resource_measurement": True,
            "general_scientific_equivalence": False,
            "causal_productivity_claim": False,
            "human_replacement_claim": False,
        },
    )
    validate_trial(value)
    return value


def validate_trial(value: dict) -> dict:
    keys(value, {
        "schema", "record_digest", "task_id", "domain", "method",
        "acceptance_policy_id", "outcome_class", "accepted",
        "representation", "metrics", "evidence_refs", "notes", "claims",
    })
    if value["schema"] != "ciw.investigation-efficiency.v1":
        raise ValueError("Wrong investigation-efficiency schema")
    check_seal(value)
    text(value["task_id"])
    text(value["acceptance_policy_id"])
    text(value["outcome_class"])
    if value["domain"] not in DOMAINS or value["method"] not in METHODS:
        raise ValueError("Unknown domain/method")
    if type(value["accepted"]) is not bool:
        raise ValueError("accepted must be boolean")
    _representation(value["representation"])
    _metrics(value["metrics"])
    _refs(value["evidence_refs"])
    if type(value["notes"]) is not str or len(value["notes"]) > 4096:
        raise ValueError("notes must be bounded text")
    expected = {
        "resource_measurement": True,
        "general_scientific_equivalence": False,
        "causal_productivity_claim": False,
        "human_replacement_claim": False,
    }
    if value["claims"] != expected:
        raise ValueError("Efficiency trial claims exceed evidence scope")
    return detached(value)


def _preservation_passes(value: dict) -> bool:
    return all(
        check["status"] == "PASS"
        for check in value["representation"]["required_preservation_checks"]
    )


def _metric_ratio(name: str, baseline: dict, candidate: dict) -> dict:
    left = baseline["metrics"][name]
    right = candidate["metrics"][name]
    if left["value"] is None or right["value"] is None:
        return {
            "metric": name,
            "unit": METRICS[name],
            "status": "UNKNOWN",
            "candidate_over_baseline": None,
            "delta_candidate_minus_baseline": None,
        }
    ratio = None if left["value"] == 0 else right["value"] / left["value"]
    return {
        "metric": name,
        "unit": METRICS[name],
        "status": "MEASURED",
        "candidate_over_baseline": ratio,
        "delta_candidate_minus_baseline": right["value"] - left["value"],
    }


def _derived(value: dict) -> dict:
    metrics = value["metrics"]
    raw = metrics["raw_evidence_bytes"]["value"]
    retrieved = metrics["retrieved_evidence_bytes"]["value"]
    reused = metrics["reused_operation_calls"]["value"]
    recomputed = metrics["recomputed_operation_calls"]["value"]
    accepted = metrics["accepted_outputs"]["value"]
    human = metrics["human_active_seconds"]["value"]

    evidence_fraction = None
    if raw is not None and retrieved is not None and raw > 0:
        evidence_fraction = retrieved / raw

    reuse_fraction = None
    if reused is not None and recomputed is not None and reused + recomputed > 0:
        reuse_fraction = reused / (reused + recomputed)

    accepted_per_hour = None
    if accepted is not None and human is not None and human > 0:
        accepted_per_hour = accepted / (human / 3600.0)

    representation_fraction = (
        value["representation"]["selected_item_count"]
        / value["representation"]["source_item_count"]
    )
    return {
        "representation_fraction": representation_fraction,
        "evidence_retrieval_fraction": evidence_fraction,
        "operation_reuse_fraction": reuse_fraction,
        "accepted_outputs_per_human_hour": accepted_per_hour,
    }


def compare_trials(baseline: dict, candidate: dict) -> dict:
    baseline = validate_trial(baseline)
    candidate = validate_trial(candidate)
    for key in ("task_id", "domain", "acceptance_policy_id", "outcome_class"):
        if baseline[key] != candidate[key]:
            raise ValueError(f"Cannot compare trials with different {key}")
    if baseline["method"] == candidate["method"]:
        raise ValueError("Comparison requires two different methods")
    if not baseline["accepted"] or not candidate["accepted"]:
        raise ValueError("Both trials must satisfy the declared acceptance policy")
    if not _preservation_passes(baseline) or not _preservation_passes(candidate):
        raise ValueError("All required preservation checks must PASS before efficiency comparison")

    metric_comparisons = {
        name: _metric_ratio(name, baseline, candidate)
        for name in METRICS
    }
    result = record(
        "investigation-comparison",
        task_id=baseline["task_id"],
        domain=baseline["domain"],
        acceptance_policy_id=baseline["acceptance_policy_id"],
        outcome_class=baseline["outcome_class"],
        baseline_ref=baseline["record_digest"],
        baseline_method=baseline["method"],
        candidate_ref=candidate["record_digest"],
        candidate_method=candidate["method"],
        preservation={
            "required_checks_passed": True,
            "scope": "same declared task, acceptance policy, outcome class and required preservation checks",
            "general_scientific_equivalence": False,
        },
        baseline_derived=_derived(baseline),
        candidate_derived=_derived(candidate),
        metric_comparisons=metric_comparisons,
        claims={
            "comparative_measurement": True,
            "aggregate_winner": False,
            "causal_productivity_claim": False,
            "general_domain_multiplier": False,
        },
    )
    validate_comparison(result)
    return result


def validate_comparison(value: dict) -> dict:
    keys(value, {
        "schema", "record_digest", "task_id", "domain", "acceptance_policy_id",
        "outcome_class", "baseline_ref", "baseline_method", "candidate_ref",
        "candidate_method", "preservation", "baseline_derived",
        "candidate_derived", "metric_comparisons", "claims",
    })
    if value["schema"] != "ciw.investigation-comparison.v1":
        raise ValueError("Wrong investigation-comparison schema")
    check_seal(value)
    for key in ("task_id", "acceptance_policy_id", "outcome_class"):
        text(value[key])
    if value["domain"] not in DOMAINS:
        raise ValueError("Unknown comparison domain")
    content_ref(value["baseline_ref"]); content_ref(value["candidate_ref"])
    if value["baseline_method"] not in METHODS or value["candidate_method"] not in METHODS:
        raise ValueError("Unknown comparison method")
    if value["baseline_method"] == value["candidate_method"]:
        raise ValueError("Comparison methods must differ")
    if value["preservation"] != {
        "required_checks_passed": True,
        "scope": "same declared task, acceptance policy, outcome class and required preservation checks",
        "general_scientific_equivalence": False,
    }:
        raise ValueError("Comparison preservation scope mismatch")
    if type(value["metric_comparisons"]) is not dict or set(value["metric_comparisons"]) != set(METRICS):
        raise ValueError("Comparison metric set mismatch")
    expected_claims = {
        "comparative_measurement": True,
        "aggregate_winner": False,
        "causal_productivity_claim": False,
        "general_domain_multiplier": False,
    }
    if value["claims"] != expected_claims:
        raise ValueError("Comparison claims exceed evidence scope")
    return detached(value)


def inspect_trial(value: dict) -> dict:
    value = validate_trial(value)
    return {
        "schema": "ciw.investigation-efficiency-inspection.v1",
        "record_digest": value["record_digest"],
        "task_id": value["task_id"],
        "domain": value["domain"],
        "method": value["method"],
        "accepted": value["accepted"],
        "required_preservation_checks_pass": _preservation_passes(value),
        "derived": _derived(value),
        "unknown_metrics": sorted(
            name for name, row in value["metrics"].items() if row["value"] is None),
        "general_scientific_equivalence": False,
        "causal_productivity_claim": False,
    }
