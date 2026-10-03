"""Read-only nonlinear fusion candidates and retained approximation details."""
from copy import deepcopy

from .experiment_view import SCHEMA, _panel


def project(record, source, declaration, revision):
    native = record["native"]
    step, = native["steps"]
    data = step["result"]["data"]
    state = data["state_contract"]
    provenance = {"source_id": source["source_id"], "evidence_id": source["evidence_id"],
                  "result_id": step["result_id"], "execution_id": step["execution_id"]}
    panels = []
    for estimate in data["estimates"]:
        details = {key: value for key, value in estimate.items()
                   if key not in {"mean", "covariance", "batch_index", "time"}}
        panels.append(_panel("state-" + str(estimate["batch_index"]),
            "Nonlinear fusion candidate at " + str(estimate["time"]), state["quantity_ids"],
            estimate["mean"], state["units"], estimate["covariance"], provenance,
            state_contract=state, batch_index=estimate["batch_index"], time=estimate["time"],
            approximation="first_order_extended_kalman_filter",
            method=data["method"],
            uncertainty_scope="conditional_on_declared_models_noise_and_local_linearization",
            state_admission="not_performed", **details))
    return deepcopy({"schema": SCHEMA, "catalog_revision": revision,
        "bundle_id": record["bundle_id"], "kind": record["kind"], "label": source["label"],
        "source_id": source["source_id"], "evidence_id": source["evidence_id"],
        "upstream_bundle_id": None,
        "replay_source_bundle_ids": [r["source_bundle_digest"] for r in native.get("replay_receipts", [])],
        "experiment_id": declaration["experiment_id"],
        "fusion_context": {"object_kind": "declared_nonlinear_sensor_fusion_candidate", "owner": "gsie+jspt",
            "summary": "Pinned nonlinear models and first-order extended Kalman fusion",
            "configuration": declaration["configuration"], "state_contract": state,
            "initial_state_id": data["initial_state_id"],
            "approximation": "first_order_extended_kalman_filter",
            "method": data["method"],
            "covariance_status": "full_first_order_declared_model_posterior",
            "uncertainty_scope": "conditional_on_declared_models_noise_and_local_linearization",
            "sensor_fusion": "performed_under_declared_models", "state_admission": "not_performed",
            "authority": data["authority"], "estimate_count": len(data["estimates"])},
        "panels": panels,
        "graph": {"nodes": [{"role": step["runtime_ref"], "operation_id": step["operation_id"],
            "result_id": step["result_id"], "execution_id": step["execution_id"],
            "numerical_result_id": step["numerical_result_id"], "input_refs": step["input_refs"]}]},
        "model_declarations": declaration["configuration"],
        "raw_observations": declaration["batches"], "verification": native["verification"],
        "runtimes": native["runtimes"], "authority": {"read_only": True,
            "numerical_replay": "not_performed_by_inspection", "state_admission": "not_performed"}})
