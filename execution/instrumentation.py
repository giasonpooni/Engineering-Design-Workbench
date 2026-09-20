"""Instrument-result exchange adapters for checked STE executions.

The adapter binds interpreted numerical output to STE's recomputed
computation identity.  It does not turn a computation into a witnessed
physical measurement, and it does not turn an internal check into an
independent verification.  Covariance claims retain variable order, units,
frame, evaluation point, method, source references, and calibration
references for downstream SET validation.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Mapping, Sequence

from execution.engine import ExecutionResult


RESULT_SCHEMA = "notation.instrument.result-artifact.v1"
VERIFICATION_SCHEMA = "notation.instrument.verification-artifact.v1"
MATRIX_STATUSES = frozenset({"reported", "estimated", "propagated"})
EMPTY_STATUSES = frozenset({"unknown", "not_applicable"})


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _finite(value: object, name: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    if not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    return value


def _refs(values: Sequence[str], name: str, *, allow_empty: bool = False) -> list[str]:
    result = [_text(value, f"{name}[]") for value in values]
    if not allow_empty and not result:
        raise ValueError(f"{name} must not be empty")
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _identity(payload: Mapping[str, object], namespace: str) -> str:
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(namespace.encode("utf-8") + b"\x00" + canonical).hexdigest()


def result_artifact_v1(
    result: ExecutionResult,
    *,
    components: Sequence[Mapping[str, object]],
    covariance_status: str,
    covariance: Sequence[Sequence[float]] | None,
    frame: Mapping[str, object],
    covariance_method: str,
    covariance_source_refs: Sequence[str],
    input_refs: Sequence[str],
    model_refs: Sequence[str] = (),
    calibration_refs: Sequence[str] = (),
    applicability: str,
    created_at: str,
) -> dict[str, object]:
    """Project one completed execution into a versioned result artifact.

    The result identity excludes engine occurrence because repetition is
    operational history, while a byte-identical computation interpreted
    under identical metadata is the same result claim.
    """
    if result.status != "completed" or result.output is None:
        raise ValueError("only a completed execution can produce a result artifact")
    if result.computation_identity is None or result.output_identity is None:
        raise ValueError("completed execution is missing checked identities")
    if not components:
        raise ValueError("components must not be empty")

    names: list[str] = []
    units: list[str] = []
    wire_components: list[dict[str, object]] = []
    for index, component in enumerate(components):
        name = _text(component.get("name"), f"components[{index}].name")
        unit = _text(component.get("unit"), f"components[{index}].unit")
        value = _finite(component.get("value"), f"components[{index}].value")
        names.append(name)
        units.append(unit)
        wire_components.append({"name": name, "value": value, "unit": unit})
    if len(set(names)) != len(names):
        raise ValueError("component names must be unique and ordered")

    if covariance_status in MATRIX_STATUSES:
        if covariance is None or len(covariance) != len(names):
            raise ValueError("matrix covariance must match the component outer dimension")
        matrix: object = [list(row) for row in covariance]
    elif covariance_status in EMPTY_STATUSES:
        if covariance is not None:
            raise ValueError(f"covariance must be absent when status is {covariance_status}")
        matrix = None
    else:
        raise ValueError("unsupported covariance_status")

    wire_frame = dict(frame)
    wire_frame["id"] = _text(frame.get("id"), "frame.id")
    wire_frame["semantics"] = _text(frame.get("semantics"), "frame.semantics")
    calibration = _refs(calibration_refs, "calibration_refs", allow_empty=True)
    payload: dict[str, object] = {
        "schema": RESULT_SCHEMA,
        "execution_ref": "computation:" + result.computation_identity,
        "execution_output_ref": "output:" + result.output_identity,
        "specification_ref": "specification:" + result.specification_identity,
        "input_refs": _refs(input_refs, "input_refs"),
        "model_refs": _refs(model_refs, "model_refs", allow_empty=True),
        "calibration_refs": calibration,
        "components": wire_components,
        "covariance": {
            "status": covariance_status,
            "variables": names,
            "units": units,
            "matrix": matrix,
            "frame": wire_frame,
            "method": _text(covariance_method, "covariance_method"),
            "source_refs": _refs(
                covariance_source_refs, "covariance_source_refs", allow_empty=True
            ),
            "calibration_refs": list(calibration),
            "numerical_status": "unchecked",
        },
        "applicability": _text(applicability, "applicability"),
        "created_at": _text(created_at, "created_at"),
        "epistemic_class": "computed_result",
    }
    return {**payload, "result_id": _identity(payload, RESULT_SCHEMA)}


def verification_artifact_v1(
    *,
    subject_ref: str,
    verifier_ref: str,
    checks: Sequence[Mapping[str, str]],
    created_at: str,
    independent: bool = False,
    external_verifier_ref: str | None = None,
    limitations: Sequence[str] = (),
) -> dict[str, object]:
    """Create a verification artifact whose summary is derived from checks."""
    if not checks:
        raise ValueError("checks must not be empty")
    wire_checks: list[dict[str, str]] = []
    outcomes: list[str] = []
    for index, check in enumerate(checks):
        outcome = _text(check.get("outcome"), f"checks[{index}].outcome")
        if outcome not in {"passed", "failed", "indeterminate"}:
            raise ValueError("unsupported check outcome")
        outcomes.append(outcome)
        wire_checks.append(
            {
                "name": _text(check.get("name"), f"checks[{index}].name"),
                "outcome": outcome,
                "basis": _text(check.get("basis"), f"checks[{index}].basis"),
            }
        )
    outcome = "failed" if "failed" in outcomes else (
        "indeterminate" if "indeterminate" in outcomes else "passed"
    )
    if independent and external_verifier_ref is None:
        raise ValueError("independent verification requires external_verifier_ref")
    if not independent and external_verifier_ref is not None:
        raise ValueError("external_verifier_ref contradicts independent=false")

    payload: dict[str, object] = {
        "schema": VERIFICATION_SCHEMA,
        "subject_ref": _text(subject_ref, "subject_ref"),
        "verifier_ref": _text(verifier_ref, "verifier_ref"),
        "created_at": _text(created_at, "created_at"),
        "checks": wire_checks,
        "outcome": outcome,
        "independent": independent,
        "limitations": _refs(limitations, "limitations", allow_empty=True),
    }
    if external_verifier_ref is not None:
        payload["external_verifier_ref"] = _text(
            external_verifier_ref, "external_verifier_ref"
        )
    return {**payload, "verification_id": _identity(payload, VERIFICATION_SCHEMA)}

