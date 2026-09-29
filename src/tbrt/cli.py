"""ClockSync command-line boundary for bounded affine clock reconciliation."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any, Mapping

import numpy as np

from .clock import (
    AffineClockModel,
    ClockFrame,
    TimePoint,
    TimestampObservation,
    reconcile_time,
)


def _frame(data: Mapping[str, Any]) -> ClockFrame:
    return ClockFrame(
        clock_id=data["clock_id"],
        time_scale=data["time_scale"],
        unit=data.get("unit", "s"),
    )


def _time_point(data: Mapping[str, Any] | None) -> TimePoint | None:
    if data is None:
        return None
    return TimePoint(value=data["value"], frame=_frame(data["frame"]))


def reconcile_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Run one ClockSync reconciliation from a JSON-compatible mapping."""

    source_frame = _frame(payload["source_frame"])
    reference_frame = _frame(payload["reference_frame"])

    observation_data = payload["observation"]
    observation = TimestampObservation(
        device_time=observation_data["device_time"],
        frame=source_frame,
        evidence_id=observation_data["evidence_id"],
        received_at=_time_point(observation_data.get("received_at")),
        known_at=_time_point(observation_data.get("known_at")),
    )

    model_data = payload["model"]
    model = AffineClockModel(
        model_id=model_data["model_id"],
        source_frame=source_frame,
        reference_frame=reference_frame,
        device_origin=model_data["device_origin"],
        reference_origin=model_data["reference_origin"],
        skew=model_data["skew"],
        offset=model_data["offset"],
        valid_device_interval=tuple(model_data["valid_device_interval"]),
        synchronization_evidence_ids=tuple(
            model_data.get("synchronization_evidence_ids", ())
        ),
    )

    covariance = np.asarray(payload["joint_covariance"], dtype=float)
    result = reconcile_time(
        observation,
        model,
        covariance,
        expected_reference=reference_frame,
        require_synchronization_evidence=bool(
            payload.get("require_synchronization_evidence", False)
        ),
    )

    output = asdict(result)
    output["reference_origin"] = result.reference_origin
    output["event_time"] = result.event_time
    output["standard_uncertainty"] = result.standard_uncertainty
    return output


def _read_payload(path: str) -> Mapping[str, Any]:
    if path == "-":
        return json.load(sys.stdin)
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clocksync",
        description=(
            "Map a device timestamp into a declared reference clock with "
            "first-order uncertainty propagation."
        ),
    )
    parser.add_argument(
        "input",
        help="JSON input file, or '-' to read JSON from stdin.",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Emit compact JSON instead of indented JSON.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        output = reconcile_payload(_read_payload(args.input))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"clocksync: {exc}", file=sys.stderr)
        return 2

    json.dump(
        output,
        sys.stdout,
        indent=None if args.compact else 2,
        sort_keys=True,
        allow_nan=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
