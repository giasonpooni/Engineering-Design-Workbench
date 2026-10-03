"""Run a deterministic synthetic fit and independently generated holdout."""
import json

import numpy as np

from sidt import evaluate_one_step, fit_lti


def trajectory(seed, count):
    rng = np.random.default_rng(seed)
    u = rng.uniform(-1, 1, size=(count, 1))
    x = np.empty((count + 1, 2))
    x[0] = [0.1, -0.2]
    a = np.array([[0.8, 0.1], [-0.2, 0.7]])
    b = np.array([[0.2], [0.4]])
    for k in range(count):
        x[k + 1] = a @ x[k] + b @ u[k]
    return x, u


def main():
    x, u = trajectory(100, 100)
    model = fit_lti(x, u, sample_interval=0.1,
                    state_names=("position", "velocity"), state_units=("m", "m/s"),
                    input_names=("force",), input_units=("N",))
    holdout_x, holdout_u = trajectory(200, 40)
    check = evaluate_one_step(model, holdout_x, holdout_u)
    print(json.dumps({
        "status": "candidate_only",
        "candidate_digest": model.candidate_digest,
        "A": model.A.tolist(), "B": model.B.tolist(),
        "rank": model.diagnostics.rank,
        "singular_values": model.diagnostics.singular_values.tolist(),
        "degrees_of_freedom": model.diagnostics.degrees_of_freedom,
        "state_residual_sum_squares": model.diagnostics.state_residual_sum_squares.tolist(),
        "holdout_state_rmse": check.state_rmse.tolist(),
        "holdout_independence": "distinct deterministic synthetic seed; asserted by this fixture",
    }, indent=2))


if __name__ == "__main__":
    main()
