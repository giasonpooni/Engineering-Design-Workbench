"""Read-only view of an explicit coordinate map and retained continuation."""
from copy import deepcopy

from .experiment_view import SCHEMA, _panel


def project(record, source, declaration, revision):
    native = record["native"]
    mapper = native["steps"][0]
    data = mapper["result"]["data"]
    mapped = data["transport"]
    child = data["continuation"]
    child_step = child["steps"][0]
    candidate = child_step["result"]["data"]
    upstream = native["upstream_fusion"]
    upstream_step = upstream["steps"][0]
    original = upstream_step["result"]["data"]["estimates"][declaration["selection"]["batch_index"]]
    source_state = upstream_step["result"]["data"]["state_contract"]
    target_state = mapped["target_state"]
    provenance = {"source_id": source["source_id"], "evidence_id": source["evidence_id"],
                  "result_id": mapper["result_id"], "execution_id": mapper["execution_id"]}
    source_provenance = {"bundle_id": upstream["bundle_digest"],
                         "evidence_id": upstream["source"]["evidence"][0]["artifact_ref"],
                         "result_id": upstream_step["result_id"], "execution_id": upstream_step["execution_id"]}
    child_provenance = {"source_id": source["source_id"],
                        "evidence_id": child["source"]["evidence"][0]["artifact_ref"],
                        "bundle_id": child["bundle_digest"], "result_id": child_step["result_id"],
                        "execution_id": child_step["execution_id"]}
    panels = [
        _panel("selected-upstream", "Selected upstream candidate", source_state["quantity_ids"],
               original["mean"], source_state["units"], original["covariance"], source_provenance,
               state_contract=source_state, state_id=original["state_id"], time=original["time"]),
        _panel("transported-prior", "Transported candidate prior", target_state["quantity_ids"],
               mapped["mapped_prior"]["mean"], target_state["units"], mapped["mapped_prior"]["covariance"], provenance,
               state_contract=target_state, state_id=mapped["mapped_state_id"], time=mapped["mapped_prior"]["time"],
               source_state_id=mapped["source_state_id"], map_id=mapped["map_id"]),
    ]
    for estimate in candidate["estimates"]:
        panels.append(_panel("continuation-" + str(estimate["batch_index"]), "Continuation candidate",
            target_state["quantity_ids"], estimate["mean"], target_state["units"], estimate["covariance"], child_provenance,
            state_contract=target_state, time=estimate["time"], state_id=estimate["state_id"],
            predecessor_state_id=estimate["predecessor_state_id"], configuration_id=estimate["configuration_id"],
            epoch_index=estimate["epoch_index"], diagnostics=estimate["diagnostics"],
            observation_refs=estimate["observation_refs"], observation_order=estimate["observation_order"]))
    nodes = [{"role": step["runtime_ref"], "operation_id": step["operation_id"],
              "result_id": step["result_id"], "execution_id": step["execution_id"],
              "numerical_result_id": step["numerical_result_id"], "input_refs": step["input_refs"]}
             for step in (mapper, child_step)]
    return deepcopy({"schema": SCHEMA, "catalog_revision": revision,
        "bundle_id": record["bundle_id"], "kind": record["kind"], "label": source["label"],
        "source_id": source["source_id"], "evidence_id": source["evidence_id"],
        "upstream_bundle_id": record["upstream_bundle_id"],
        "replay_source_bundle_ids": [r["source_bundle_digest"] for r in native.get("replay_receipts", [])],
        "experiment_id": declaration["experiment_id"],
        "fusion_context": {"object_kind": "transported_sensor_fusion_candidate", "owner": "jspt+gsie",
            "summary": "Explicit linear coordinate transport and GSIE continuation",
            "source_state_contract": source_state, "state_contract": target_state,
            "source_state_id": mapped["source_state_id"], "initial_state_id": mapped["mapped_state_id"],
            "map_id": mapped["map_id"], "map_matrix": declaration["transport"]["matrix"],
            "continuation_bundle_id": child["bundle_digest"],
            "covariance_status": "full_transformed_declared_model_covariance",
            "uncertainty_scope": "conditional_on_declared_models_noise_and_exact_coordinate_map",
            "sensor_fusion": "performed_under_declared_models", "state_admission": "not_performed",
            "authority": data["authority"], "estimate_count": len(candidate["estimates"])},
        "panels": panels, "graph": {"nodes": nodes, "transport_binding": {
            "upstream_result_id": upstream_step["result_id"], "source_state_id": mapped["source_state_id"],
            "transport_result_id": mapper["result_id"], "mapped_state_id": mapped["mapped_state_id"],
            "continuation_source_id": mapped["continuation_source_id"],
            "continuation_result_id": child_step["result_id"]}},
        "raw_observations": declaration["continuation"]["batches"],
        "verification": native["verification"], "continuation_verification": child["verification"],
        "runtimes": native["runtimes"], "authority": {"read_only": True,
            "numerical_replay": "not_performed_by_inspection", "state_admission": "not_performed"}})
