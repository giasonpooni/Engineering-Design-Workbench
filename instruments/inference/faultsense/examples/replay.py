# SPDX-License-Identifier: MPL-2.0
"""Run after `python -m pip install -e .`; output contains no clock or randomness."""

from dataclasses import asdict
import json

from fdir import CusumState, cusum_step, evaluate_residual


def replay() -> dict:
    innovation = evaluate_residual(
        [2.0, 3.0], [[4.0, 2.0], [2.0, 5.0]],
        threshold=4.0,
        variable_order=["position_x_m", "position_y_m"],
        source_ids=["fixture:gsie-innovation:0001"],
    )
    state = CusumState()
    sequence = []
    for index, residual in enumerate([0.0, 1.5, 1.5, 1.5]):
        transition = cusum_step(
            residual, state, drift=0.5, threshold=3.0,
            direction="two_sided", reset_on_alarm=True,
            source_ids=[f"fixture:normalized-residual:{index:04d}"],
        )
        sequence.append(asdict(transition))
        state = transition.next_state
    return {"residual_diagnostics": asdict(innovation), "cusum_transitions": sequence}


if __name__ == "__main__":
    print(json.dumps(replay(), indent=2, sort_keys=True, allow_nan=False))
