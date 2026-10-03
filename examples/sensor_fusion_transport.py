"""Run a synthetic metre-to-millimetre continuation through both pinned providers.

Run from a checkout with the NET package installed. Provider paths are explicit
operator bindings; the output directory must be new. No physical admission or
independent verification is claimed by this numerical example.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import json
from pathlib import Path

import numpy as np

from ciw import sensor_fusion_transport as transport
from ciw.sensor_fusion_transport_workflow import SensorFusionTransportWorkflow, algorithm_identity
from ciw.sensor_fusion_workflow import SensorFusionWorkflow
from ciw.telemetry import canonical


def encoded(value):
    return base64.b64encode(value).decode()


def save(directory, name, value):
    with (directory / name).open("xb") as handle:
        handle.write(canonical(value) + b"\n")


def estimates(bundle):
    return bundle["steps"][0]["result"]["data"]["estimates"]


def declaration(seed, upstream):
    step = upstream["steps"][0]
    selected = estimates(upstream)[-1]
    configuration = deepcopy(seed["configuration"])
    measured = deepcopy(seed["batches"][-1])
    measured["time"] = selected["time"] + 1
    for observation in measured["observations"]:
        record = json.loads(base64.b64decode(observation["record_b64"], validate=True))
        sensor = record["sensor_id"]
        record.update(time=measured["time"], acquisition_id=f"transport-example:{sensor}:5",
                      values=[5.1 if sensor == "position" else 1.02])
        record["raw_evidence_b64"] = encoded(canonical({
            "origin": "synthetic_fixture", "acquisition_id": record["acquisition_id"],
            "reading": record["values"], "physical_traceability": "not_established"}))
        observation["record_b64"] = encoded(canonical(record))
    prediction = deepcopy(measured)
    prediction.update(time=measured["time"] + 1, observations=[], measurement_noise=None)
    target = deepcopy(configuration["state"])
    target.update(units=["mm", "mm/s"])
    return {"schema": transport.SOURCE_SCHEMA, "experiment_id": "synthetic:millimetre-continuation",
        "configuration": deepcopy(transport.POLICY),
        "selection": {"upstream_bundle_id": upstream["bundle_digest"],
            "upstream_result_id": step["result_id"], "upstream_execution_id": step["execution_id"],
            "upstream_numerical_result_id": step["numerical_result_id"],
            "state_id": selected["state_id"], "batch_index": selected["batch_index"]},
        "transport": {"matrix": [[1000, 0], [0, 1000]], "target_state": target,
            "map_evidence_b64": encoded(canonical({
                "origin": "synthetic_fixture", "relation": "one metre equals 1000 millimetres",
                "offset": 0, "uncertainty": "declared_zero", "physical_calibration": "not_verified"}))},
        "continuation": {"configuration": configuration, "batches": [measured, prediction]}}


def run(jspt_repo, gsie_repo, output_dir):
    output_dir.mkdir(parents=True, exist_ok=False)
    seed_path = Path(__file__).with_name("sensor-fusion-tracking.json")
    seed_raw = seed_path.read_bytes()
    seed = json.loads(seed_raw)
    bindings = {"jspt": jspt_repo, "gsie": gsie_repo}
    fusion = SensorFusionWorkflow()
    upstream = fusion.create_session(seed_raw, {"gsie": gsie_repo})
    save(output_dir, "upstream.json", upstream)
    source = declaration(seed, upstream)
    save(output_dir, "transport-source.json", source)
    workflow = SensorFusionTransportWorkflow()
    bundle = workflow.create_session(canonical(source), upstream, bindings)
    save(output_dir, "transport.json", bundle)
    replay = workflow.replay_session(bundle, bindings)
    save(output_dir, "replay.json", replay["session"])
    baseline = fusion.create_session(canonical(transport.prepare(source, upstream)), {"gsie": gsie_repo})
    save(output_dir, "baseline.json", baseline)
    child = bundle["steps"][0]["result"]["data"]["continuation"]
    matrix = np.asarray(source["transport"]["matrix"], dtype=float)
    comparisons = []
    for original, mapped in zip(estimates(baseline), estimates(child), strict=True):
        expected_mean = matrix @ original["mean"]
        expected_covariance = matrix @ original["covariance"] @ matrix.T
        np.testing.assert_allclose(mapped["mean"], expected_mean, rtol=2e-12, atol=2e-9)
        np.testing.assert_allclose(mapped["covariance"], expected_covariance, rtol=2e-12, atol=2e-9)
        comparisons.append({"time": mapped["time"],
            "mean_max_absolute_error": float(np.max(np.abs(np.asarray(mapped["mean"]) - expected_mean))),
            "covariance_max_absolute_error": float(np.max(np.abs(np.asarray(mapped["covariance"]) - expected_covariance)))})
    old = bundle["steps"][0]
    fresh = replay["session"]["steps"][0]
    if old["numerical_result_id"] != fresh["numerical_result_id"] or old["execution_id"] == fresh["execution_id"]:
        raise RuntimeError("Replay must retain numerical content with a fresh execution")
    report = {"schema": "ciw.sensor-fusion-transport-example.v1", "status": "passed",
        "scope": "synthetic_coordinate_equivalence_and_same_provider_reproduction",
        "wrapper_sha256": algorithm_identity(), "runtimes": bundle["runtimes"],
        "selected_upstream": source["selection"], "transport_bundle_id": bundle["bundle_digest"],
        "replay_bundle_id": replay["session"]["bundle_digest"],
        "numerical_result_id": old["numerical_result_id"], "comparison": comparisons,
        "target_units": source["transport"]["target_state"]["units"],
        "independent_verification": False, "state_admission": "not_performed"}
    save(output_dir, "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jspt-repo", type=Path, required=True)
    parser.add_argument("--gsie-repo", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.jspt_repo, args.gsie_repo, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
