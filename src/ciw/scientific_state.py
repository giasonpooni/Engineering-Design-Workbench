"""Read-only full-covariance state selection from existing RCI/FSRT/JSPT results.

Projection is not a new estimate. No model code or process is executed here.
Native diagnostics and scope accompany the typed state, including held correction.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile

from .control_contracts import state, text, save_new
from .core.identities import content_identity


def _project(session, result_id: str, stage: str, entity_id: str) -> dict:
    from .investigation import _validate_source
    from .covariance_workflow import result_covariance
    from .core.covariance import validate_covariance_artifact
    text(result_id)
    text(entity_id)
    run = session.run
    if run["instrument"] != "org.notationsystems.rci":
        raise ValueError("This projection requires retained RCI evidence; simulated sources are not reclassified")
    source = _validate_source(run)
    result = session.results.get(result_id)
    if result is None:
        raise ValueError("Select an exact retained result; refused executions do not supply a state")
    if result["operation_id"] == "fsrt.tank-reconstruct.v2":
        if stage not in {"prior", "posterior", "reconciled"}:
            raise ValueError("Select prior, posterior or reconciled; innovations are not state estimates")
        semantics = "reference" if stage == "prior" else "estimated"
        diagnostics = deepcopy(result["data"]["diagnostics"])
        model = result["data"]["model"]
    elif result["operation_id"] == "jspt.covariance-propagate.v1":
        if stage != "output_covariance":
            raise ValueError("JSPT exposes output_covariance; no estimated mean is invented")
        # The output reference values are supplied by the caller, not calculated means.
        semantics = "reference"
        diagnostics = {"reference_scope": "caller_declared_not_a_new_measurement_or_computed_mean",
                       "map_kind": result["parameters"]["map_kind"]}
        model = {"source_covariance_id": result["parameters"]["source_covariance"]["covariance_id"],
                 "declared_map": {k: result["parameters"][k] for k in (
                     "jacobian", "output_quantity_ids", "output_units", "output_frame", "output_reference_values", "map_kind")}}
    else:
        raise ValueError("Selected result has no supported scientific-state projection")
    covariance = result_covariance(result, stage)
    validate_covariance_artifact(covariance)
    records = [sensor["measurement"]["records"][0] for sensor in source["sensors"]]
    timestamps = {record["observed_at"] for record in records}
    if len(timestamps) != 1 or run["time_s"] != [0.0]:
        raise ValueError("Only the existing simultaneous snapshot time basis is supported")
    instant = timestamps.pop()
    projected = state(
        identity={"model_id": content_identity(model), "entity_id": entity_id,
                  "execution_id": result["execution_id"]},
        clock={"id": "rci-snapshot:" + instant, "time_s": 0.0}, frame=covariance["frame"],
        variables={quantity: {"value": value, "unit": unit} for quantity, value, unit in zip(
            covariance["quantity_ids"], covariance["reference_values"], covariance["units"])},
        uncertainty=covariance,
        provenance={"provider": result["operation_id"], "semantics": semantics,
                    "sources": [run["evidence_id"], result["record_digest"], covariance["covariance_id"]]})
    return {"schema": "ciw.scientific-state-selection.v1", "state": projected,
            "context": {"result_id": result_id, "execution_id": result["execution_id"],
                        "operation_id": result["operation_id"], "stage": stage,
                        "source_evidence_id": run["evidence_id"], "observed_at": instant,
                        "time_basis": "one_simultaneous_snapshot; time_s=0 is not a sampling cadence",
                        "entity_identity": "caller_declared; no cross-source entity matching inferred",
                        "diagnostics": diagnostics, "runtime": deepcopy(result["runtime"]),
                        "verification_id": result["verification_id"],
                        "verification_status": result["verification_status"]},
            "runtime_launched": False, "state_admission": "not_performed",
            "validation_scope": "projection_of_selected_validated_workspace; not_independent_source_authentication"}


def select_state(session, *, result_id: str, stage: str, entity_id: str,
                 bundle_id: str | None = None) -> dict:
    """Select a root result or an exact inner result of a measurement-chain bundle.

    Validate a detached snapshot using the existing Session reader before projection.
    Original run/result/covariance IDs and full matrices are preserved. Inspection
    allocates no execution or verification occurrence.
    """
    from .session import Session
    from .scientific import selected_bundle
    with tempfile.TemporaryDirectory(prefix="net-state-selection-") as temporary:
        root = Path(temporary)
        frozen = root / "source.json"
        if bundle_id is None:
            # Existing serialization, not a new workspace or ledger schema.
            session.save_workspace(frozen)
        else:
            summary = selected_bundle(session, bundle_id)
            if summary["kind"] != "measurement-chain":
                raise ValueError("Only a selected measurement-chain bundle supplies this inner state path")
            native = session.workbench.get_bundle(bundle_id)
            workspace = native["steps"][0]["result"]["data"]["native_workspace"]
            save_new(frozen, workspace)
        checked = Session.from_workspace(frozen, root / "checked")
        value = _project(checked, result_id, stage, entity_id)
        value["context"]["bundle_id"] = bundle_id
        return value
