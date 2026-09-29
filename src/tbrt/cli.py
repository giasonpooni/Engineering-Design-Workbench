"""Strict JSON/CLI transport for ClockSync; numerical authority remains clock.py."""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import asdict
from importlib import metadata, resources
import json
from pathlib import Path
import sys
from typing import Any

from .clock import AffineClockModel, ClockFrame, TimePoint, TimestampObservation, reconcile_time

MAX_INPUT_CHARACTERS = 1_048_576
EXAMPLES = ("offset", "drift", "correlated")


def _object(value: object, name: str, required: set[str], optional: set[str] | None = None) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(k, str) for k in value):
        raise ValueError(f"{name} must be an object with string keys")
    missing = required - value.keys()
    unknown = value.keys() - required - (optional or set())
    if missing:
        raise ValueError(f"{name}: missing fields: {', '.join(sorted(missing))}")
    if unknown:
        raise ValueError(f"{name}: unknown fields: {', '.join(sorted(unknown))}")
    return value


def _frame(value: object) -> ClockFrame:
    data = _object(value, "frame", {"clock_id", "time_scale"}, {"unit"})
    return ClockFrame(data["clock_id"], data["time_scale"], data.get("unit", "s"))


def _time_point(value: object) -> TimePoint | None:
    if value is None:
        return None
    data = _object(value, "time point", {"value", "frame"})
    return TimePoint(data["value"], _frame(data["frame"]))


def reconcile_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Reconcile one JSON-compatible request without coercing invalid values.

    Top-level source/reference frames bind both observation and model. An
    independent expected_reference may pin the destination. Unknown fields are
    refused rather than ignored. clock.py owns numeric and covariance checks.
    """
    data = _object(payload, "request", {"source_frame", "reference_frame", "observation", "model", "joint_covariance"}, {"expected_reference", "require_synchronization_evidence"})
    source = _frame(data["source_frame"])
    reference = _frame(data["reference_frame"])
    expected = _frame(data["expected_reference"]) if "expected_reference" in data else reference
    require_evidence = data.get("require_synchronization_evidence", False)
    if type(require_evidence) is not bool:
        raise ValueError("require_synchronization_evidence must be boolean")
    raw = _object(data["observation"], "observation", {"device_time", "evidence_id"}, {"received_at", "known_at"})
    observation = TimestampObservation(raw["device_time"], source, raw["evidence_id"], _time_point(raw.get("received_at")), _time_point(raw.get("known_at")))
    supplied = _object(data["model"], "model", {"model_id", "device_origin", "reference_origin", "skew", "offset", "valid_device_interval"}, {"synchronization_evidence_ids"})
    interval = supplied["valid_device_interval"]
    if not isinstance(interval, (list, tuple)) or len(interval) != 2:
        raise ValueError("valid_device_interval must be an array of two bounds")
    evidence = supplied.get("synchronization_evidence_ids", ())
    if not isinstance(evidence, (list, tuple)):
        raise ValueError("synchronization_evidence_ids must be an array of distinct strings")
    model = AffineClockModel(
        model_id=supplied["model_id"], source_frame=source, reference_frame=reference,
        device_origin=supplied["device_origin"], reference_origin=supplied["reference_origin"],
        skew=supplied["skew"], offset=supplied["offset"], valid_device_interval=tuple(interval),
        synchronization_evidence_ids=tuple(evidence),
    )
    # Do not cast to float here: the core must see (and reject) strings/bools.
    result = reconcile_time(observation, model, data["joint_covariance"], expected_reference=expected, require_synchronization_evidence=require_evidence)
    output = asdict(result)
    output.update(reference_origin=result.reference_origin, event_time=result.event_time, standard_uncertainty=result.standard_uncertainty)
    # Transport policy is retained separately from evidence and the numerical result.
    output["request_options"] = {"expected_reference": asdict(expected), "require_synchronization_evidence": require_evidence}
    return output


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _read_payload(path: str) -> Mapping[str, Any]:
    if path == "-":
        text = sys.stdin.read(MAX_INPUT_CHARACTERS + 1)
    else:
        with Path(path).open("r", encoding="utf-8") as stream:
            text = stream.read(MAX_INPUT_CHARACTERS + 1)
    if len(text) > MAX_INPUT_CHARACTERS:
        raise ValueError(f"input exceeds {MAX_INPUT_CHARACTERS} characters")
    return json.loads(text, object_pairs_hook=_unique_object, parse_constant=_reject_constant)


def _version() -> str:
    try:
        return metadata.version("notations-clocksync")
    except metadata.PackageNotFoundError:
        return "uninstalled-source-checkout"


def example_payload(name: str) -> dict[str, Any]:
    """Return a fresh, explicitly synthetic request shipped inside the wheel."""
    if name not in EXAMPLES:
        raise ValueError(f"unknown example: {name}")
    examples = json.loads(resources.files("tbrt").joinpath("examples.json").read_text(encoding="utf-8"))
    return examples[name]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clocksync", description="Apply a supplied affine clock map and propagate first-order timing uncertainty. Does not set or fit clocks.")
    parser.add_argument("input", nargs="?", help="JSON request file, or '-' for stdin")
    parser.add_argument("--example", choices=EXAMPLES, help="emit a synthetic request JSON (does not run reconciliation)")
    parser.add_argument("--version", action="version", version=f"ClockSync {_version()}")
    parser.add_argument("--compact", action="store_true", help="emit compact JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if (args.input is None) == (args.example is None):
        parser.error("provide exactly one input file, '-' or --example NAME")
    try:
        output = example_payload(args.example) if args.example is not None else reconcile_payload(_read_payload(args.input))
        # Serialize fully before writing; rejected input never emits partial JSON.
        text = json.dumps(output, indent=None if args.compact else 2, sort_keys=True, allow_nan=False, separators=(",", ":") if args.compact else None)
        sys.stdout.write(text + "\n")
        sys.stdout.flush()
    except BrokenPipeError:
        return 1
    except (ValueError, TypeError, KeyError, OSError, OverflowError, RecursionError) as exc:
        print(f"clocksync: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
