"""Cycle-associated sensor evidence with conservative interval decision rules.

Different modalities provide different quantities. Their association with one
cycle is not evidence of simultaneous sampling or full latent-state observability.
"""
from __future__ import annotations

from .polymer_contract import AUTHORITY


def assess_metrology(request: dict) -> dict:
    rows = []
    end = request["clock"]["end_s"]
    for sensor in request["sensors"]:
        sample = sensor["samples"][-1] if sensor["samples"] else None
        status = "MISSING" if sample is None else ("STALE" if end - sample["time_s"] > sensor["max_age_s"] else "VALID")
        rows.append({"sensor_id": sensor["sensor_id"], "quantity": sensor["quantity"], "unit": sensor["unit"],
                     "value": None if sample is None else sample["value"],
                     "standard_uncertainty": None if sample is None else sample["standard_uncertainty"],
                     "time_s": None if sample is None else sample["time_s"], "status": status,
                     "source_refs": [sensor["source_ref"], sensor["calibration_ref"], sensor["clock_ref"]]})
    # No independence assertion is inferred from different sensor names. Union
    # intervals avoid precision inflation and retain disagreement visibly.
    quantities = []
    for tolerance in request["tolerances"]:
        matching = [r for r in rows if r["quantity"] == tolerance["quantity"]]
        valid = [r for r in matching if r["status"] == "VALID"]
        interval = None
        reason = "missing_or_stale_required_channel"
        outcome = "INDETERMINATE"
        aligned = (not valid or max(r["time_s"] for r in valid) - min(r["time_s"] for r in valid)
                   <= request["clock"]["max_skew_s"])
        if not aligned:
            reason = "sensor_times_exceed_declared_skew"
            for row in valid:
                row["status"] = "UNALIGNED"
        elif request["measurement_condition"] != tolerance["condition"]:
            reason = "measurement_condition_differs_from_specification"
        elif matching and len(valid) == len(matching):
            k = tolerance["coverage_factor"]
            interval = [min(r["value"] - k * r["standard_uncertainty"] for r in valid),
                        max(r["value"] + k * r["standard_uncertainty"] for r in valid)]
            if tolerance["lower"] <= interval[0] and interval[1] <= tolerance["upper"]:
                outcome, reason = "CONFORMING", "entire_declared_uncertainty_interval_inside_tolerance"
            elif interval[1] < tolerance["lower"] or interval[0] > tolerance["upper"]:
                outcome, reason = "NONCONFORMING", "entire_declared_uncertainty_interval_outside_tolerance"
            else:
                reason = "declared_uncertainty_interval_overlaps_tolerance_boundary"
        refs = sorted({ref for row in matching for ref in row["source_refs"]})
        quantities.append({"quantity": tolerance["quantity"], "unit": tolerance["unit"], "status": outcome,
                           "interval": interval, "evidence_refs": refs, "reason": reason,
                           "specification_ref": tolerance["specification_ref"]})
    status = ("NONCONFORMING" if any(q["status"] == "NONCONFORMING" for q in quantities) else
              "INDETERMINATE" if any(q["status"] == "INDETERMINATE" for q in quantities) else "CONFORMING")
    return {"schema": "ciw.polymer-metrology.v1", "status": status, "quantities": quantities,
            "measurements": rows, "fusion_method": "conservative_interval_union_no_independence_assumption",
            "time_semantics": "cycle_associated_not_simultaneous_multimodal_state",
            "uncertainty_semantics": "caller_declared_standard_uncertainty_and_multiplier_not_coverage_validation",
            "measurement_condition": request["measurement_condition"], "authority": dict(AUTHORITY)}
