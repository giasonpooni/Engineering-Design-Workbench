"""Project retained thermal outputs into existing NET observations; no new solver.

The view retains the original native step but excludes synthetic evaluation truth.
Inspection reuses native numerical validators; it does not create an execution,
launch a provider or authenticate the original producer.
"""
from __future__ import annotations

import base64
from copy import deepcopy

from .control_contracts import _base, bytes_ref, content_ref, keys, text, observation
from .control_plane import ObservationBus
from .core.covariance import create_covariance_artifact
from .core.identities import content_identity
from .operations.runner import seal
from .thermal_workflow import KIND, OPERATION, ThermalWorkflow
from .telemetry import canonical

SCHEMA = "ciw.thermal-observation-view.v1"
STAGES = ("predicted", "posterior", "measurement")
AUTHORITY = {
    "kind": "retained_thermal_observation_projection",
    "source_origin": "synthetic_fixture",
    "reference_truth": "not_included",
    "physical_validation": "not_established",
    "state_admission": "not_performed",
    "hardware_actuation": "not_performed",
    "new_execution": "not_performed",
    "source_authentication": "not_established_by_hashes",
    "cross_tick_covariance": "not_supplied",
}


def _binding(value: dict) -> None:
    keys(value, {"workspace_sha256", "source_id", "source_evidence_id", "bundle_id", "runtime_digest"})
    for field in ("workspace_sha256", "source_evidence_id", "bundle_id", "runtime_digest"):
        content_ref(value[field])
    text(value["source_id"])
    if not value["source_id"].startswith("source:sha256:"):
        raise ValueError("Require a retained Workbench source identity")
    content_ref(value["source_id"][len("source:"):])


def _build(binding: dict, step: dict, stage: str, entity_id: str) -> dict:
    _binding(binding)
    text(entity_id)
    if stage not in STAGES:
        raise ValueError("Select predicted, posterior or measurement; no hidden reference-truth projection")
    request = step["request"]
    # Existing native validation includes the independent bounded numerical check.
    ThermalWorkflow._validate_step(step, {"request": request}, binding["source_evidence_id"])
    trace = step["result"]["data"]["observer"]["trace"]
    model_id = content_identity(request["model"])
    frame = "thermal-state:" + model_id
    clock_id = "thermal-source:" + binding["source_evidence_id"]
    sources = [binding["source_evidence_id"], step["result_id"], binding["bundle_id"]]
    provider = "ciw.thermal-observer-source.v1" if stage == "measurement" else OPERATION
    bus = ObservationBus(len(trace))
    rows = []
    for index, row in enumerate(trace):
        measured = stage == "measurement"
        values = request["observations"][index] if measured else row[stage + "_mean"]
        matrix = request["observation_noise_covariance"] if measured else row[stage + "_covariance"]
        native_path = ("request.observation_noise_covariance" if measured else
                       f"result.data.observer.trace[{index}].{stage}_covariance")
        missing = any(value is None for value in values)
        covariance = None
        if not missing:
            covariance = create_covariance_artifact(
                matrix=matrix, quantity_ids=["temperature[0]", "temperature[1]"],
                units=["K", "K"], frame=frame, reference_values=values,
                method="wrap_retained_native_matrix_without_recomputation",
                basis={"kind": "observation" if measured else "estimated_state",
                       "id": step["result_id"] + f"/{stage}/{index}"},
                provenance={"provider": provider, "source_evidence_ids": sources,
                            "source_covariance_ids": [],
                            "metadata": {"native_path": native_path, "stage": stage,
                                         "available_mask": row["available_mask"]}},
                assumptions=["Synthetic declared model; not empirical calibration or coverage",
                    "Marginal at this tick only; no cross-tick covariance supplied",
                    step["result"]["data"]["observer"]["noise_assumption"]])
        bus.publish(observation(
            identity={"model_id": model_id, "entity_id": entity_id,
                      "execution_id": None if measured else step["execution_id"]},
            clock={"id": clock_id, "time_s": (index + 1) * request["sample_interval_s"]},
            frame=frame, quantity="temperature", value=values, unit="K", uncertainty=covariance,
            provenance={"provider": provider, "sources": sources,
                        "semantics": "simulated" if measured else "estimated"}))
        rows.append({"index": index, "available_mask": row["available_mask"],
                     "native_covariance_path": native_path,
                     "covariance_attachment": "unattached_due_to_missing_values" if missing else "full_matrix"})
    return seal({"schema": SCHEMA, "binding": deepcopy(binding), "native_step": deepcopy(step),
                 "stage": stage, "entity_id": entity_id, "coordinate_order": deepcopy(request["model"]["state_order"]),
                 "time_basis": "post_transition; first_sample_is_dt; source_scoped_clock",
                 "stream": bus.snapshot(), "row_context": rows, "authority": deepcopy(AUTHORITY)})


def validate_view(value: dict) -> None:
    """Check retained native input/result and exact projection, not producer authenticity."""
    _base(value, "thermal-observation-view", {"binding", "native_step", "stage", "entity_id",
          "coordinate_order", "time_basis", "stream", "row_context", "authority"})
    try:
        expected = _build(value["binding"], value["native_step"], value["stage"], value["entity_id"])
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError, RecursionError) as exc:
        raise ValueError("Malformed retained thermal observation view") from exc
    if canonical(value) != canonical(expected):
        raise ValueError("Thermal observation view contradicts its retained native step")


def select_observations(session, *, bundle_id: str, stage: str, entity_id: str,
                        workspace_sha256: str) -> dict:
    """Project one exact validated bundle; the supplied digest names the source snapshot.

    The file-based export API verifies the digest against the bytes it actually
    reads. For direct Session callers it is a supplied provenance declaration.
    """
    from .scientific import selected_bundle
    content_ref(workspace_sha256)
    selected = selected_bundle(session, bundle_id)
    if selected["kind"] != KIND or selected["operation_id"] != OPERATION:
        raise ValueError("This projection accepts the existing thermal-observer bundle only")
    bundle = session.workbench.get_bundle(bundle_id)
    raw = ThermalWorkflow()._validate(bundle)
    descriptor = session.workbench.get_source(selected["source_id"])
    if (base64.b64decode(descriptor["bytes_b64"], validate=True) != raw or
            descriptor["evidence_id"] != bytes_ref(raw)):
        raise ValueError("Selected native source differs from retained Workbench evidence")
    return _build({"workspace_sha256": workspace_sha256, "source_id": selected["source_id"],
                   "source_evidence_id": descriptor["evidence_id"], "bundle_id": bundle_id,
                   "runtime_digest": content_identity(bundle["runtimes"])},
                  bundle["steps"][0], stage, entity_id)


def export_observations(workspace, *, expected_sha256: str, bundle_id: str,
                        stage: str, entity_id: str) -> dict:
    """Single bounded read bound to explicitly selected workspace bytes; no output writes."""
    from .scientific import open_workspace
    with open_workspace(workspace, expected_sha256=expected_sha256) as session:
        return select_observations(session, bundle_id=bundle_id, stage=stage,
                                   entity_id=entity_id, workspace_sha256=expected_sha256)


def match_workspace(value: dict, workspace) -> None:
    """Re-derive a retained view against the exact workspace named in its binding."""
    validate_view(value)
    expected = export_observations(workspace, expected_sha256=value["binding"]["workspace_sha256"],
        bundle_id=value["binding"]["bundle_id"], stage=value["stage"], entity_id=value["entity_id"])
    if canonical(value) != canonical(expected):
        raise ValueError("Thermal observation view does not match the selected workspace")
