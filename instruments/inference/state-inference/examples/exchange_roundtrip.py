# SPDX-License-Identifier: MPL-2.0
"""Emit an estimate for the synthetic position fixture using the pinned checker."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from geometric_state_inference import LinearObservation, StatePrior, update
from geometric_state_inference.exchange import import_observation_batch, export_result_artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validator-repo", required=True, type=Path)
    args = parser.parse_args()
    artifact = json.loads((Path(__file__).parent / "exchange/observation.json").read_text())
    frame = artifact["covariance"]["frame"]
    imported = import_observation_batch(
        artifact, epoch="2026-09-20T12:00:00Z", variables=("east", "north"),
        units=("m", "m"), frame=frame, validator_repo=args.validator_repo,
    )
    # Full prior and H are retained here for reproducible model interpretation.
    prior = StatePrior(0, [0, 0], [[1, 0], [0, 1]], frame["id"], ("m", "m"),
                       "example:synthetic-position-prior")
    model = LinearObservation([[1, 0], [0, 1]], "example:direct-position.v1")
    estimate = update(prior, imported.observation, model)
    result = export_result_artifact(
        estimate, source=imported, variables=("east", "north"), frame=frame,
        execution_ref="example:local-python-execution:" + uuid4().hex,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        applicability="Synthetic fixture only; no physical measurement or calibration claim",
        validator_repo=args.validator_repo,
    )
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
