"""Numerical validators for the v1 instrument-exchange boundary.

The exchange keeps four identities separate:

* observation batches name preserved evidence;
* execution requests/results name computations;
* result artifacts name interpreted numerical output;
* verification artifacts name checks over a referenced subject.

Covariance validation establishes that a declared matrix is numerically
eligible to be consumed as a covariance.  It does not establish sensor
calibration, model adequacy, measurement truth, or independence of a
verification process.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re
from typing import Mapping, Sequence


OBSERVATION_SCHEMA = "notation.instrument.observation-batch.v1"
RESULT_SCHEMA = "notation.instrument.result-artifact.v1"
VERIFICATION_SCHEMA = "notation.instrument.verification-artifact.v1"

MATRIX_STATUSES = frozenset({"reported", "estimated", "propagated"})
EMPTY_STATUSES = frozenset({"unknown", "not_applicable"})
FRAME_SEMANTICS = frozenset(
    {
        "geodetic",
        "intrinsic_physical",
        "tangent",
        "feature_space",
        "arbitrary_model_space",
    }
)


class ContractError(ValueError):
    """The artifact is structurally or numerically ineligible."""


@dataclass(frozen=True)
class CovarianceValidation:
    dimension: int
    # Missing covariance has no numerical rank; it is not a zero matrix.
    effective_rank: int | None
    symmetry_tolerance: float
    psd_tolerance: float


def _record(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{name} must be an object")
    return value


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{name} must be a non-empty string")
    return value


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{name} must be numeric")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ContractError(f"{name} must be finite") from exc
    if not math.isfinite(number):
        raise ContractError(f"{name} must be finite")
    return number


def _tolerance(value: object, name: str) -> float:
    tolerance = _finite(value, name)
    if not 0.0 <= tolerance < 1.0:
        raise ContractError(f"{name} must be a relative tolerance in [0, 1)")
    return tolerance


def _instant(value: object, name: str) -> str:
    text = _text(value, name)
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z",
        text,
    ):
        raise ContractError(f"{name} must be an explicit UTC instant with date and time")
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise ContractError(f"{name} must be ISO-8601") from exc
    return text


def _texts(
    value: object,
    name: str,
    *,
    allow_empty: bool = False,
    allow_duplicates: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ContractError(f"{name} must be an ordered array")
    result = tuple(_text(item, f"{name}[]") for item in value)
    if not allow_empty and not result:
        raise ContractError(f"{name} must not be empty")
    if not allow_duplicates and len(set(result)) != len(result):
        raise ContractError(f"{name} must not contain duplicates")
    return result


def _validate_frame(value: object, dimension: int) -> None:
    frame = _record(value, "covariance.frame")
    _text(frame.get("id"), "covariance.frame.id")
    semantics = _text(frame.get("semantics"), "covariance.frame.semantics")
    if semantics not in FRAME_SEMANTICS:
        raise ContractError("covariance.frame.semantics is unsupported")

    basis = frame.get("basis")
    if semantics == "tangent" and basis is None:
        raise ContractError("a tangent covariance requires an ordered basis")
    if basis is not None and len(_texts(basis, "covariance.frame.basis")) != dimension:
        raise ContractError("covariance.frame.basis must follow variable order")

    point = frame.get("evaluation_point")
    if semantics == "tangent" and point is None:
        raise ContractError("a tangent covariance requires an evaluation_point")
    if point is not None:
        if not isinstance(point, (list, tuple)) or not point:
            raise ContractError("covariance.frame.evaluation_point must be a numeric array")
        for index, entry in enumerate(point):
            _finite(entry, f"covariance.frame.evaluation_point[{index}]")


def _symmetric_eigenvalues(matrix: tuple[tuple[float, ...], ...]) -> tuple[float, ...]:
    """Cyclic Jacobi spectrum of a normalized symmetric matrix.

    Normalization happens before arithmetic to avoid overflow. Orthogonal
    rotations avoid dividing by a small covariance pivot, which can make an
    unpivoted LDL check reject a valid rank-deficient matrix. Failure to
    converge is an error, never a successful numerical validation.
    """
    n = len(matrix)
    work = [list(row) for row in matrix]
    for _ in range(64):
        largest = max((abs(work[p][q]) for p in range(n) for q in range(p + 1, n)), default=0.0)
        if largest == 0.0:
            return tuple(work[p][p] for p in range(n))
        for p in range(n):
            for q in range(p + 1, n):
                off_diagonal = work[p][q]
                if off_diagonal == 0.0:
                    continue
                delta = (work[q][q] - work[p][p]) * 0.5
                denominator = delta + math.copysign(math.hypot(delta, off_diagonal), delta)
                tangent = off_diagonal / denominator
                cosine = 1.0 / math.hypot(1.0, tangent)
                sine = tangent * cosine
                work[p][p] -= tangent * off_diagonal
                work[q][q] += tangent * off_diagonal
                work[p][q] = work[q][p] = 0.0
                for k in range(n):
                    if k == p or k == q:
                        continue
                    left, right = work[k][p], work[k][q]
                    work[k][p] = work[p][k] = cosine * left - sine * right
                    work[k][q] = work[q][k] = sine * left + cosine * right
        # Gershgorin's row bound controls the remaining spectral error.
        residual = max(math.fsum(abs(work[p][q]) for q in range(n) if p != q) for p in range(n))
        scale = max(1.0, max(abs(work[p][p]) for p in range(n)))
        if residual <= math.ulp(scale):
            return tuple(work[p][p] for p in range(n))
    raise ContractError("covariance eigenspectrum did not converge")


def validate_covariance(
    value: object,
    *,
    expected_variables: Sequence[str] | None = None,
    expected_units: Sequence[str] | None = None,
    symmetry_tolerance: float = 1e-12,
    psd_tolerance: float = 1e-12,
) -> CovarianceValidation:
    """Validate covariance eligibility in dimensionless correlation coordinates.

    Positive diagonal rescaling preserves eligibility and effective rank up
    to floating-point roundoff. Rank is numerical at the declared tolerance,
    not a mathematical proof. Both stored triangles must be eligible; rank
    is the smaller of their ranks when roundoff straddles the threshold.
    Missing covariance returns ``effective_rank=None`` (validator API 0.2).
    """
    symmetry_tolerance = _tolerance(symmetry_tolerance, "symmetry_tolerance")
    psd_tolerance = _tolerance(psd_tolerance, "psd_tolerance")
    covariance = _record(value, "covariance")
    status = _text(covariance.get("status"), "covariance.status")
    if status not in MATRIX_STATUSES | EMPTY_STATUSES:
        raise ContractError("covariance.status is unsupported")

    variables = _texts(covariance.get("variables"), "covariance.variables")
    units = _texts(
        covariance.get("units"), "covariance.units", allow_duplicates=True
    )
    if len(units) != len(variables):
        raise ContractError("covariance.units must follow variable order")
    if expected_variables is not None and tuple(expected_variables) != variables:
        raise ContractError("covariance.variables does not match component order")
    if expected_units is not None and tuple(expected_units) != units:
        raise ContractError("covariance.units does not match component units")

    _validate_frame(covariance.get("frame"), len(variables))
    _texts(covariance.get("source_refs"), "covariance.source_refs", allow_empty=True)
    _texts(covariance.get("calibration_refs"), "covariance.calibration_refs", allow_empty=True)
    _text(covariance.get("method"), "covariance.method")

    raw_matrix = covariance.get("matrix")
    if status in EMPTY_STATUSES:
        if raw_matrix is not None:
            raise ContractError(f"covariance.matrix must be absent when status is {status}")
        return CovarianceValidation(len(variables), None, symmetry_tolerance, psd_tolerance)
    if not isinstance(raw_matrix, (list, tuple)) or len(raw_matrix) != len(variables):
        raise ContractError("covariance.matrix must be square and match variable order")

    rows: list[tuple[float, ...]] = []
    for row_index, raw_row in enumerate(raw_matrix):
        if not isinstance(raw_row, (list, tuple)) or len(raw_row) != len(variables):
            raise ContractError("covariance.matrix must be rectangular and square")
        rows.append(tuple(
            _finite(entry, f"covariance.matrix[{row_index}][{column_index}]")
            for column_index, entry in enumerate(raw_row)
        ))
    matrix = tuple(rows)

    diagonal = [matrix[index][index] for index in range(len(matrix))]
    if any(variance < 0.0 for variance in diagonal):
        raise ContractError("covariance.matrix has a negative variance")
    for index, variance in enumerate(diagonal):
        if variance == 0.0 and any(
            matrix[index][other] != 0.0 or matrix[other][index] != 0.0
            for other in range(len(matrix))
        ):
            raise ContractError("a zero variance requires an exactly zero covariance row and column")
    active = [index for index, variance in enumerate(diagonal) if variance > 0.0]
    roots = [math.sqrt(diagonal[index]) for index in active]
    normalized = []
    for row, source_row in enumerate(active):
        normalized_row = []
        for column, source_column in enumerate(active):
            # Divide by the larger root first. Forming the variance product
            # or dividing by a tiny root first can overflow for mixed units.
            value = matrix[source_row][source_column] / max(roots[row], roots[column])
            value /= min(roots[row], roots[column])
            if not math.isfinite(value):
                raise ContractError("covariance.matrix has nonfinite normalized correlation")
            normalized_row.append(value)
        normalized.append(normalized_row)
    for row in range(len(active)):
        for column in range(row):
            if abs(normalized[row][column] - normalized[column][row]) > symmetry_tolerance:
                raise ContractError("covariance.matrix is not symmetric")

    # Check both stored triangles, never average or repair the claim. The
    # pairwise bound also prevents huge invalid correlations overflowing the
    # eigensolver. It is necessary for PSD in correlation coordinates.
    if any(abs(value) > 1.0 + psd_tolerance for row in normalized for value in row):
        raise ContractError("covariance.matrix is not positive-semidefinite")
    ranks = []
    for upper in (False, True):
        symmetric = tuple(tuple(
            normalized[min(row, column)][max(row, column)] if upper else
            normalized[max(row, column)][min(row, column)]
            for column in range(len(active))
        ) for row in range(len(active)))
        spectrum = _symmetric_eigenvalues(symmetric)
        if any(eigenvalue < -psd_tolerance for eigenvalue in spectrum):
            raise ContractError("covariance.matrix is not positive-semidefinite")
        ranks.append(sum(eigenvalue > psd_tolerance for eigenvalue in spectrum))
    effective_rank = min(ranks)
    return CovarianceValidation(
        dimension=len(matrix),
        effective_rank=effective_rank,
        symmetry_tolerance=symmetry_tolerance,
        psd_tolerance=psd_tolerance,
    )


def _components(value: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ContractError("components must be a non-empty ordered array")
    variables: list[str] = []
    units: list[str] = []
    for index, item in enumerate(value):
        component = _record(item, f"components[{index}]")
        variables.append(_text(component.get("name"), f"components[{index}].name"))
        units.append(_text(component.get("unit"), f"components[{index}].unit"))
        _finite(component.get("value"), f"components[{index}].value")
    if len(set(variables)) != len(variables):
        raise ContractError("component names must be unique and ordered")
    return tuple(variables), tuple(units)


def _validate_calibration_references(artifact: Mapping[str, object]) -> None:
    outer_refs = _texts(artifact.get("calibration_refs"), "calibration_refs", allow_empty=True)
    covariance = _record(artifact.get("covariance"), "covariance")
    covariance_refs = _texts(
        covariance.get("calibration_refs"), "covariance.calibration_refs", allow_empty=True
    )
    if not set(covariance_refs) <= set(outer_refs):
        raise ContractError("covariance.calibration_refs must be retained in artifact calibration_refs")


def validate_observation_batch(value: object) -> CovarianceValidation:
    artifact = _record(value, "observation batch")
    if artifact.get("schema") != OBSERVATION_SCHEMA:
        raise ContractError("unsupported observation batch schema")
    batch_id = _text(artifact.get("batch_id"), "batch_id")
    _instant(artifact.get("observed_at"), "observed_at")
    _instant(artifact.get("received_at"), "received_at")
    _text(artifact.get("clock_basis"), "clock_basis")
    source_refs = _texts(artifact.get("source_artifact_refs"), "source_artifact_refs")
    if batch_id in source_refs:
        raise ContractError("batch_id must differ from its source artifact references")
    _validate_calibration_references(artifact)
    variables, units = _components(artifact.get("components"))
    return validate_covariance(
        artifact.get("covariance"),
        expected_variables=variables,
        expected_units=units,
    )


def validate_result_artifact(value: object) -> CovarianceValidation:
    artifact = _record(value, "result artifact")
    if artifact.get("schema") != RESULT_SCHEMA:
        raise ContractError("unsupported result artifact schema")
    result_id = _text(artifact.get("result_id"), "result_id")
    execution_ref = _text(artifact.get("execution_ref"), "execution_ref")
    input_refs = _texts(artifact.get("input_refs"), "input_refs")
    if result_id == execution_ref or result_id in input_refs:
        raise ContractError("result_id must differ from execution and input references")
    _texts(artifact.get("model_refs"), "model_refs", allow_empty=True)
    _validate_calibration_references(artifact)
    _text(artifact.get("applicability"), "applicability")
    _instant(artifact.get("created_at"), "created_at")
    variables, units = _components(artifact.get("components"))
    return validate_covariance(
        artifact.get("covariance"),
        expected_variables=variables,
        expected_units=units,
    )


def validate_verification_artifact(value: object) -> None:
    artifact = _record(value, "verification artifact")
    if artifact.get("schema") != VERIFICATION_SCHEMA:
        raise ContractError("unsupported verification artifact schema")
    verification_id = _text(artifact.get("verification_id"), "verification_id")
    subject_ref = _text(artifact.get("subject_ref"), "subject_ref")
    if verification_id == subject_ref:
        raise ContractError("verification_id must differ from subject_ref")
    _text(artifact.get("verifier_ref"), "verifier_ref")
    _instant(artifact.get("created_at"), "created_at")
    outcome = _text(artifact.get("outcome"), "outcome")
    if outcome not in {"passed", "failed", "indeterminate"}:
        raise ContractError("verification outcome is unsupported")
    checks = artifact.get("checks")
    if not isinstance(checks, (list, tuple)) or not checks:
        raise ContractError("verification checks must be non-empty")
    check_outcomes: list[str] = []
    for index, item in enumerate(checks):
        check = _record(item, f"checks[{index}]")
        _text(check.get("name"), f"checks[{index}].name")
        check_outcome = _text(check.get("outcome"), f"checks[{index}].outcome")
        if check_outcome not in {"passed", "failed", "indeterminate"}:
            raise ContractError("check outcome is unsupported")
        _text(check.get("basis"), f"checks[{index}].basis")
        check_outcomes.append(check_outcome)

    expected = "failed" if "failed" in check_outcomes else (
        "indeterminate" if "indeterminate" in check_outcomes else "passed"
    )
    if outcome != expected:
        raise ContractError("verification outcome does not summarize its checks")

    independent = artifact.get("independent")
    if not isinstance(independent, bool):
        raise ContractError("independent must be explicit")
    external_ref = artifact.get("external_verifier_ref")
    if independent:
        _text(external_ref, "external_verifier_ref")
    elif external_ref is not None:
        raise ContractError("external_verifier_ref contradicts independent=false")
    _texts(artifact.get("limitations"), "limitations", allow_empty=True)
