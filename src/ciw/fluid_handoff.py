"""A qualified dynamic sample projected onto the existing scalar state contract.

This exports simulated values with their model time and occurrence bindings.
It does not manufacture measurements, sensor covariance, a temporal estimator,
or a qualified conversion between lumped fluid and spatial wave models.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from .control_contracts import save_new, state, validate_state
from .operations.runner import seal


def export_snapshot(destination: Path, output: Path, *, sample_index: int) -> dict:
    from .fluid_contract import profile_for_request
    from .fluid_workflow import _read, _verify_read, source_request
    session, candidate, verification = _read(Path(destination))
    if candidate is None or verification is None:
        raise ValueError("A dynamic snapshot requires a retained candidate and verification")
    request = source_request(session.run)
    if profile_for_request(request) != "reservoir":
        raise ValueError("Scalar two-reservoir projection requires the reservoir profile")
    checked = _verify_read(session, candidate, verification)
    if checked["status"] != "LOCAL":
        raise ValueError("Dynamic sample handoff requires fresh LOCAL numerical qualification")
    result = candidate["data"]
    trace = result["resolutions"]["finer"]["trace"]
    if type(sample_index) is not int or not 0 <= sample_index < len(trace["time_s"]):
        raise ValueError("sample_index must select one retained finer-resolution time node")
    units = result["units"]
    projection = state(
        identity={"model_id": request["scope"], "entity_id": "two_reservoir_and_compliant_boundary",
                  "execution_id": candidate["execution_id"]},
        clock={"id": request["clock"]["id"], "time_s": trace["time_s"][sample_index]},
        frame=result["representation"]["coordinate_frame"],
        variables={name: {"value": values[sample_index], "unit": units[name]}
                   for name, values in trace.items() if name != "time_s"},
        provenance={"provider": result["provider"],
                    "sources": [session.run["evidence_id"], candidate["record_digest"], result["record_digest"]],
                    "semantics": "simulated"}, uncertainty=None,
    )
    validate_state(projection)
    payload = seal({
        "schema": "ciw.fluid-reservoir-snapshot.v1", "sample_index": sample_index,
        "resolution": "finer", "source_evidence_id": session.run["evidence_id"],
        "source_result_id": candidate["result_id"], "source_execution_id": candidate["execution_id"],
        "source_result_digest": result["record_digest"],
        "retained_verification_id": verification["data"]["verification_id"],
        "fresh_verification_id": checked["fresh_verification_id"],
        "fresh_verification_execution_id": checked["fresh_verification_execution_id"],
        "fresh_verification_result_id": checked["fresh_verification_result_id"],
        "fresh_verification_record": deepcopy(checked["fresh_verification_record"]),
        "fresh_verification_runtime": deepcopy(checked["recomputed_with_runtime"]),
        "recomputed_report_digest": checked["recomputed_report_digest"], "state": projection,
        "mapping": {
            "preserved": ["selected SI scalar values", "provider-owned model time", "source and execution identities"],
            "discarded": ["remaining trajectory samples", "coarser refinement traces"],
            "receiver_requirements": ["explicit source class", "declared observation operator and sensor covariance for estimation"],
            "estimator_execution": "not_performed", "temporal_estimator_qualification": "not_established",
            "uncertainty": "not_established", "physical_validation": "not_established",
            "state_admission": "not_performed",
        },
    })
    save_new(Path(output), deepcopy(payload))
    return {"status": "exported", "output": str(output), "record_digest": payload["record_digest"],
            "sample_index": sample_index, "time_s": projection["clock"]["time_s"]}
