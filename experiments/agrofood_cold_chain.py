"""Synthetic agro-food cold-chain workload over the existing thermal instrument.

This is a transfer experiment, not a new agriculture engine. The underlying
two-capacity thermal model, Kalman reference, covariance handling and prospective
sensor selection are unchanged. Only the application fixture is cold-chain
product core/shell temperature under refrigerated ambient conditions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from ciw import thermal_contract as contract
from ciw import thermal_reference as reference
from ciw.thermal_workflow import ThermalWorkflow


def make_source() -> dict:
    model = {
        "state_order": ["core_temperature", "shell_temperature"],
        "state_units": ["K", "K"],
        "input_order": ["heat_power", "ambient_temperature"],
        "input_units": ["W", "K"],
        "sensor_order": ["core", "shell"],
        "sensor_units": ["K", "K"],
        "capacities_j_per_k": [60000.0, 12000.0],
        "conductances_w_per_k": [12.0, 6.0],
        "observation_matrix": [[1, 0], [0, 1]],
    }
    dt = 300.0
    inputs = [
        [12.0, 274.0],
        [10.0, 274.0],
        [9.0, 274.5],
        [8.0, 275.0],
        [10.0, 275.0],
        [11.0, 274.5],
    ]
    process_noise = [
        [0.02, -0.01],
        [0.00, 0.02],
        [-0.01, 0.01],
        [0.01, 0.00],
        [0.00, -0.01],
        [0.01, 0.01],
    ]
    measurement_noise = [
        [0.10, -0.08],
        [0.05, 0.04],
        [-0.06, 0.03],
        [0.04, -0.02],
        [-0.03, 0.05],
        [0.02, -0.04],
    ]
    matrices = reference.model_matrices(model, dt)
    ad = np.asarray(matrices["Ad"], dtype=float)
    bd = np.asarray(matrices["Bd"], dtype=float)
    state = np.asarray([279.0, 277.0], dtype=float)
    states = []
    observations = []
    for index, input_row in enumerate(inputs):
        state = ad @ state + bd @ np.asarray(input_row, dtype=float) + np.asarray(process_noise[index], dtype=float)
        states.append(state.tolist())
        measured = state + np.asarray(measurement_noise[index], dtype=float)
        row = measured.tolist()
        if index == 2:
            row[0] = None
        if index == 4:
            row[1] = None
        observations.append(row)

    held_input = [9.0, 274.0]
    held_process = [0.0, 0.0]
    held_measurement = [0.03, -0.02]
    held_state = ad @ state + bd @ np.asarray(held_input, dtype=float) + np.asarray(held_process, dtype=float)
    held_obs = held_state + np.asarray(held_measurement, dtype=float)

    request = {
        "schema": contract.REQUEST_SCHEMA,
        "operation_id": contract.OPERATION_ID,
        "model": model,
        "sample_interval_s": dt,
        "prior": {
            "mean": [278.5, 276.5],
            "covariance": [[1.0, 0.1], [0.1, 1.5]],
        },
        "process_noise_covariance": [[0.02, 0.0], [0.0, 0.03]],
        "observation_noise_covariance": [[0.25, 0.0], [0.0, 0.36]],
        "inputs": inputs,
        "observations": observations,
        "selection": {
            "costs": [2.0, 1.0],
            "budget": 2.0,
            "minimum_sensors": 1,
            "tie_tolerance_nats": 1e-10,
            "tie_policy": "lowest_mask_within_tolerance",
        },
    }
    source = {
        "schema": contract.SOURCE_SCHEMA,
        "experiment_id": "agrofood:cold-chain-thermal-v1",
        "configuration": dict(contract.POLICY),
        "request": request,
        "evaluation": {
            "origin": "synthetic_fixture",
            "generator_model": model,
            "initial_state": [279.0, 277.0],
            "process_noise": process_noise,
            "measurement_noise": measurement_noise,
            "states": states,
            "held_out": {
                "input": held_input,
                "process_noise": held_process,
                "state": held_state.tolist(),
                "measurement_noise": held_measurement,
                "observations": held_obs.tolist(),
            },
            "noise_law": "operator_declared_not_authenticated",
        },
    }
    contract.validate_source(contract.canonical(source))
    return source


def run() -> dict:
    source = make_source()
    raw = contract.canonical(source)
    workflow = ThermalWorkflow()
    session = workflow.create_session(raw, {})
    step = session["steps"][0]
    native = step["result"]["data"]
    observer = native["observer"]
    selection = native["selection"]
    evaluation = reference.evaluate(source, observer)

    if native["claim_scope"] != contract.CLAIM_SCOPE:
        raise AssertionError("thermal claim scope changed")
    if selection["status"] != "optimal" or selection["selected_mask"] is None:
        raise AssertionError("cold-chain fixture requires a feasible sensor selection")
    if evaluation["physical_validation"] != "not_established":
        raise AssertionError("synthetic cold-chain fixture cannot claim physical validation")

    result = {
        "schema": "notations.agrofood-cold-chain-thermal-experiment.v1",
        "application": {
            "domain": "agro-food",
            "workload": "synthetic_postharvest_cold_chain",
            "system": "two-capacity product core/shell thermal state",
            "decision_scope": "thermal-state estimation and prospective sensor selection only",
            "product_quality_or_spoilage_model": "not_present",
        },
        "instrument": {
            "operation_id": contract.OPERATION_ID,
            "claim_scope": native["claim_scope"],
            "runtime_profile": session["runtimes"]["thermal"]["profile"],
        },
        "observations": {
            "steps": len(source["request"]["inputs"]),
            "explicit_dropouts": sum(
                value is None
                for row in source["request"]["observations"]
                for value in row
            ),
            "sample_interval_s": source["request"]["sample_interval_s"],
        },
        "estimate": {
            "final_mean_k": observer["final_mean"],
            "final_covariance_k2": observer["final_covariance"],
            "trajectory_rmse_k": evaluation["trajectory_rmse_k"],
            "held_out_nis": evaluation["held_out"]["nis"],
        },
        "sensor_selection": {
            "selected_mask": selection["selected_mask"],
            "selected_sensors": next(
                row["sensors"]
                for row in selection["candidates"]
                if row["mask"] == selection["selected_mask"]
            ),
            "objective_nats": selection["objective_nats"],
            "budget": source["request"]["selection"]["budget"],
            "costs": source["request"]["selection"]["costs"],
        },
        "transfer_claim": {
            "existing_thermal_instrument_reused_unchanged": True,
            "new_agriculture_architecture_introduced": False,
            "physical_validation": False,
            "product_quality_prediction": False,
            "state_admission": False,
        },
    }
    return {"source": source, "session": session, "summary": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    artifacts = run()
    for name, value in artifacts.items():
        (args.output_dir / f"{name}.json").write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(artifacts["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
