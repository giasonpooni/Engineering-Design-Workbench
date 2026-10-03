"""A bounded rational oracle for affine-exact reconciliation.

All arithmetic is exact over the supplied binary64 inputs until output encoding.
This is deliberately a small reference implementation, not a fast large-state
solver. Exact nullspaces are distinguished from nonzero values lost by ordinary
floating-point products, subtraction, or output conversion.
"""

from __future__ import annotations

import copy
from fractions import Fraction as F
import hashlib
import json
import math
import re

OPERATION_ID = "cbsr.affine-exact.v1"
MAX_DIMENSION = 16
MAX_CONDITION = F(10**12)
QMatrix = list[list[F]]


class ContractError(ValueError):
    """Malformed request; no scientific result can be issued."""


class _Refusal(Exception):
    pass


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_numbers(value: object) -> object:
    """Normalize accepted JSON numbers for mathematical replay equivalence."""
    if type(value) in (int, float):
        return float(value) if value else 0.0
    if isinstance(value, list):
        return [_normalized_numbers(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalized_numbers(item) for key, item in value.items()}
    return value


def _keys(value: object, required: set[str], optional: set[str], name: str) -> dict:
    if type(value) is not dict or set(value) - required - optional or required - set(value):
        raise ContractError(f"{name}: missing, unsupported, or invalid fields")
    return value


def _string(value: object, name: str) -> str:
    if type(value) is not str or not value.strip() or len(value) > 4096:
        raise ContractError(f"{name} must be a nonempty bounded string")
    return value


def _strings(value: object, name: str, length: int | None = None) -> list[str]:
    if type(value) is not list or not value or len(value) > 256:
        raise ContractError(f"{name} must be a nonempty bounded list")
    if length is not None and len(value) != length:
        raise ContractError(f"{name} has the wrong length")
    return [_string(item, name) for item in value]


def _number(value: object, name: str) -> F:
    # No bool, numpy scalar, numeric string, NaN, infinity, complex or implicit
    # conversion. Integers must be represented exactly in binary64.
    if type(value) not in (float, int):
        raise ContractError(f"{name} must be a real JSON number (not a boolean or string)")
    try:
        converted = float(value)
    except (OverflowError, ValueError) as exc:
        raise ContractError(f"{name} must be finite binary64") from exc
    if not math.isfinite(converted) or (type(value) is int and int(converted) != value):
        raise ContractError(f"{name} must be exactly representable finite binary64")
    return F(converted)


def _vector(value: object, name: str, size: int | None = None) -> list[F]:
    if type(value) is not list or not 1 <= len(value) <= MAX_DIMENSION:
        raise ContractError(f"{name} must have 1..{MAX_DIMENSION} entries")
    if size is not None and len(value) != size:
        raise ContractError(f"{name} has the wrong length")
    return [_number(item, name) for item in value]


def _matrix(value: object, name: str, rows: int | None, columns: int) -> QMatrix:
    if type(value) is not list or not 1 <= len(value) <= MAX_DIMENSION:
        raise ContractError(f"{name} must have 1..{MAX_DIMENSION} rows")
    if rows is not None and len(value) != rows:
        raise ContractError(f"{name} has the wrong row count")
    return [_vector(row, name, columns) for row in value]


def _transpose(matrix: QMatrix) -> QMatrix:
    return [list(column) for column in zip(*matrix)]


def _mul(left: QMatrix, right: QMatrix) -> QMatrix:
    return [[sum((a * b for a, b in zip(row, column)), F(0))
             for column in zip(*right)] for row in left]


def _mv(matrix: QMatrix, vector: list[F]) -> list[F]:
    return [sum((a * b for a, b in zip(row, vector)), F(0)) for row in matrix]


def _psd_pivots(matrix: QMatrix) -> list[int]:
    """Exact unpivoted LDL Schur test; zero pivots require a zero remainder row."""
    if matrix != _transpose(matrix):
        raise _Refusal("covariance_not_exactly_symmetric")
    work = [row[:] for row in matrix]
    pivots = []
    for k in range(len(work)):
        diagonal = work[k][k]
        if diagonal < 0:
            raise _Refusal("covariance_not_positive_semidefinite")
        if diagonal == 0:
            if any(work[k][j] != 0 for j in range(k + 1, len(work))):
                raise _Refusal("covariance_not_positive_semidefinite")
            continue
        pivots.append(k)
        for i in range(k + 1, len(work)):
            for j in range(i, len(work)):
                work[i][j] -= work[i][k] * work[k][j] / diagonal
                work[j][i] = work[i][j]
    return pivots


def _solve(matrix: QMatrix, rhs: QMatrix) -> QMatrix | None:
    """Exact rectangular solve; free variables zero; None iff inconsistent."""
    n = len(matrix[0])
    width = len(rhs[0])
    work = [row[:] + value[:] for row, value in zip(matrix, rhs)]
    pivot_rows = []
    next_row = 0
    for col in range(n):
        pivot = next((i for i in range(next_row, len(work)) if work[i][col]), None)
        if pivot is None:
            continue
        work[next_row], work[pivot] = work[pivot], work[next_row]
        factor = work[next_row][col]
        work[next_row] = [item / factor for item in work[next_row]]
        for i in range(len(work)):
            if i != next_row:
                factor = work[i][col]
                work[i] = [a - factor * b for a, b in zip(work[i], work[next_row])]
        pivot_rows.append((next_row, col))
        next_row += 1
    if any(not any(row[:n]) and any(row[n:]) for row in work):
        return None
    result = [[F(0) for _ in range(width)] for _ in range(n)]
    for row, col in pivot_rows:
        result[col] = work[row][n:]
    return result


def _condition(matrix: QMatrix, pivots: list[int]) -> F | None:
    if not pivots:
        return None
    independent = [[matrix[i][j] for j in pivots] for i in pivots]
    identity = [[F(int(i == j)) for j in pivots] for i in pivots]
    inverse = _solve(independent, identity)
    assert inverse is not None
    norm = lambda a: max(sum(abs(value) for value in row) for row in a)
    return norm(independent) * norm(inverse)


def _encode(value: F | list) -> float | list:
    if isinstance(value, list):
        return [_encode(item) for item in value]
    try:
        encoded = float(value)
    except OverflowError as exc:
        raise _Refusal("numerical_output_overflow") from exc
    if not math.isfinite(encoded):
        raise _Refusal("numerical_output_overflow")
    if value and encoded == 0:
        raise _Refusal("nonzero_numerical_output_underflow")
    return encoded


def _validated(request: object) -> tuple[dict, list[F], QMatrix, QMatrix, list[F], F]:
    request = _keys(request, {
        "state_id", "estimate", "covariance", "state_labels", "state_units", "frame_ref",
        "constraints", "crosscov_policy", "max_normalized_residual", "evidence_refs", "execution_id",
    }, {"source_result_id", "source_result_digest"}, "request")
    _string(request["state_id"], "state_id")
    _string(request["execution_id"], "execution_id")
    _string(request["frame_ref"], "frame_ref")
    _strings(request["evidence_refs"], "evidence_refs")
    x = _vector(request["estimate"], "estimate")
    labels = _strings(request["state_labels"], "state_labels", len(x))
    if len(set(labels)) != len(labels):
        raise ContractError("state_labels must be unique and ordered")
    _strings(request["state_units"], "state_units", len(x))
    P = _matrix(request["covariance"], "covariance", len(x), len(x))
    constraint = _keys(request["constraints"], {
        "constraint_id", "coefficients", "rhs", "row_units", "coefficient_policy",
    }, set(), "constraints")
    _string(constraint["constraint_id"], "constraint_id")
    protected_ids = {OPERATION_ID, request["state_id"], constraint["constraint_id"]}
    if len(protected_ids) != 3 or protected_ids.intersection(request["evidence_refs"]):
        raise ContractError("state, operation, constraint, and evidence identities must remain separate")
    if request["execution_id"] in protected_ids.union(request["evidence_refs"]):
        raise ContractError("execution identity must be separate from state, operation, constraint, and evidence")
    C = _matrix(constraint["coefficients"], "coefficients", None, len(x))
    d = _vector(constraint["rhs"], "rhs", len(C))
    _strings(constraint["row_units"], "row_units", len(C))
    _string(constraint["coefficient_policy"], "coefficient_policy")
    _string(request["crosscov_policy"], "crosscov_policy")
    threshold = _number(request["max_normalized_residual"], "max_normalized_residual")
    if threshold <= 0:
        raise ContractError("max_normalized_residual must be positive")
    if ("source_result_id" in request) != ("source_result_digest" in request):
        raise ContractError("source_result_id and source_result_digest must be supplied together")
    if "source_result_id" in request:
        _string(request["source_result_id"], "source_result_id")
        if request["source_result_id"] in protected_ids or request["source_result_id"] == request["execution_id"]:
            raise ContractError("source result identity must remain separate from execution, state, operation, and constraint")
        digest = request["source_result_digest"]
        if type(digest) is not str or not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", digest):
            raise ContractError("source_result_digest must be a SHA-256 digest")
    return copy.deepcopy(request), x, P, C, d, threshold


def reconcile_affine_exact(request: dict) -> dict:
    """Issue an accepted, held, or refused receipt for declared C x = d.

    Invalid JSON contracts raise ContractError. Scientifically unsupported or
    unrepresentable requests return refused receipts retaining the raw candidate.
    A supplied source digest is retained/bound, not externally authenticated.
    """
    request, x, P, C, d, threshold = _validated(request)
    request_digest = _digest(request)
    scientific = {
        "status": "refused", "reason": None,
        "candidate": {"estimate": request["estimate"], "covariance": request["covariance"]},
        "reconciled": None, "correction": None, "residual_pre": None, "residual_post": None,
        "residual_covariance_pre": None, "residual_covariance_post": None,
        "normalized_residual": None, "residual_rank": None,
        "condition_inf_independent_rows": None, "feasible": None,
        "rational_constraint_residual_zero": False,
        "output_constraint_residual_zero": False,
        "arithmetic": "exact-rational-over-binary64;nearest-output;no-repair",
        "claims": {"physical_validity": False, "fault_isolation": False,
                   "evidence_admission": False, "stability": False},
    }
    try:
        if request["constraints"]["coefficient_policy"] != "declared_exact":
            raise _Refusal("uncertain_or_undeclared_constraint_unsupported")
        if request["crosscov_policy"] not in ("declared", "declared_zero"):
            raise _Refusal("unknown_or_unsupported_crosscovariance")
        if request["crosscov_policy"] == "declared_zero" and any(
            P[i][j] for i in range(len(P)) for j in range(len(P)) if i != j
        ):
            raise _Refusal("declared_zero_contradicts_covariance")
        _psd_pivots(P)
        feasible = _solve(C, [[value] for value in d]) is not None
        scientific["feasible"] = feasible
        if not feasible:
            raise _Refusal("infeasible_constraint_declaration")
        residual = [a - b for a, b in zip(_mv(C, x), d)]
        CP = _mul(C, P)
        S = _mul(CP, _transpose(C))
        pivots = _psd_pivots(S)
        scientific["residual_rank"] = len(pivots)
        scientific["residual_pre"] = _encode(residual)
        scientific["residual_covariance_pre"] = _encode(S)
        condition = _condition(S, pivots)
        if condition is not None:
            scientific["condition_inf_independent_rows"] = _encode(condition)
            if condition > MAX_CONDITION:
                raise _Refusal("residual_system_ill_conditioned")
        solved = _solve(S, [[r] + row for r, row in zip(residual, CP)])
        if solved is None:
            raise _Refusal("constraint_conflicts_with_exact_covariance_nullspace")
        multipliers = [row[0] for row in solved]
        T = sum((a * b for a, b in zip(residual, multipliers)), F(0))
        scientific["normalized_residual"] = _encode(T)
        if T > threshold:
            scientific.update(status="held", reason="normalized_residual_exceeds_declared_threshold")
        else:
            cross = _transpose(CP)
            correction = [-value for value in _mv(cross, multipliers)]
            estimate = [a + b for a, b in zip(x, correction)]
            removed = _mul(cross, [row[1:] for row in solved])
            covariance = [[a - b for a, b in zip(row, reduction)]
                          for row, reduction in zip(P, removed)]
            exact_rank = len(_psd_pivots(covariance))
            assert _mv(C, estimate) == d
            encoded_x = _encode(estimate)
            encoded_P = _encode(covariance)
            # Rounding a singular PSD matrix can make it indefinite. Do not hide
            # that behind an eigenvalue tolerance or clipped diagonal.
            try:
                encoded_rank = len(_psd_pivots([[F(value) for value in row] for row in encoded_P]))
            except _Refusal as exc:
                raise _Refusal("rounded_output_covariance_not_psd") from exc
            if encoded_rank < exact_rank:
                raise _Refusal("rounded_output_covariance_lost_positive_direction")
            post = [a - b for a, b in zip(_mv(C, [F(value) for value in encoded_x]), d)]
            post_cov = _mul(_mul(C, [[F(value) for value in row] for row in encoded_P]), _transpose(C))
            scientific.update(
                status="accepted", reason="declared_affine_constraint_reconciled",
                reconciled={"estimate": encoded_x, "covariance": encoded_P},
                correction=_encode(correction), residual_post=_encode(post),
                residual_covariance_post=_encode(post_cov),
                rational_constraint_residual_zero=True,
                output_constraint_residual_zero=not any(post),
            )
    except _Refusal as exc:
        scientific.update(status="refused", reason=str(exc), reconciled=None, correction=None,
                          residual_post=None, residual_covariance_post=None,
                          rational_constraint_residual_zero=False)
    # Numerical equivalence deliberately excludes evidence/source/occurrence
    # identities, while the receipt content binds the complete retained request.
    mathematical_input = {key: value for key, value in request.items() if key not in {
        "state_id", "execution_id", "evidence_refs", "source_result_id", "source_result_digest",
    }}
    mathematical_input["constraints"] = {
        key: value for key, value in request["constraints"].items() if key != "constraint_id"
    }
    numerical_id = "sha256:" + _digest(_normalized_numbers({"operation_id": OPERATION_ID,
                                                            "input": mathematical_input, "output": scientific}))
    output_state_id = None
    if scientific["status"] == "accepted":
        output_state_id = "sha256:" + _digest({"parent_state_id": request["state_id"],
                                               "numerical_result_id": numerical_id})
    receipt = {
        "schema": "cbsr.affine-exact-result.v1", "operation_id": OPERATION_ID,
        "execution_id": request["execution_id"], "input_state_id": request["state_id"],
        "output_state_id": output_state_id, "constraint_id": request["constraints"]["constraint_id"],
        "request_digest": request_digest, "request": request,
        "evidence_refs": request["evidence_refs"], "numerical_result_id": numerical_id,
        "source_binding_verification": "caller_assertion_only",
        **scientific,
    }
    receipt["result_id"] = "sha256:" + _digest(receipt)
    return receipt
