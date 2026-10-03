"""Synthetic, explicitly declared candidate identification and fresh replay."""
from sidt import identify_declared, replay_identification


request = {
    "schema": "sidt.declared-identification-input.v1",
    "model_id": "model:synthetic-reservoir",
    "clock_frame": "clock:reference-seconds",
    "state_frame": "frame:reservoir-mass",
    "sample_interval": 0.5,
    "state_names": ["mass"], "state_units": ["kg"],
    "input_names": ["feed"], "input_units": ["kg/s"],
    "condition_limit": 1e6,
    "training": {
        "states": [[1.0], [2.5], [1.25], [4.625], [0.3125]],
        "inputs": [[1.0], [0.0], [2.0], [-1.0]],
        "sample_times": [0.0, 0.5, 1.0, 1.5, 2.0],
        "sample_refs": [f"sample:synthetic-training:{i}" for i in range(5)],
        "evidence_refs": ["evidence:synthetic-training"],
    },
}
original = identify_declared(request, execution_ref="execution:synthetic-original")
replay = replay_identification(original, execution_ref="execution:synthetic-replay")
print(original["numerical_result"])
print("Same numerical identity:", original["numerical_id"] == replay["numerical_id"])
print("Fresh result occurrence:", original["result_id"] != replay["result_id"])
