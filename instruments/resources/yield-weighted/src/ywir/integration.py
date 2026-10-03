"""Deterministic advisory admission for a retained observation-design selection.

This adapter evaluates a declared inference-token budget in a disposable host.
It never reserves, settles, restores a host, or authorizes a physical observation.
CIW retains the request and supplies execution and verification occurrences.
"""

from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Any

from ywir.constitution import DEPARTMENTS, DOES_NOT_CLAIM, PACKAGE_VERSION
from ywir.errors import YwirRefuse
from ywir.observation import Proposal
from ywir.receipts import support_code_for
from ywir.runtime import decide, open_host


TOKEN_ADMISSION_OPERATION = "ywir.observation-design-token-admission.v1"
TOKEN_REQUEST_SCHEMA = "ywir.observation-design-token-request.v1"
TOKEN_RESULT_SCHEMA = "ywir.observation-design-token-result.v1"

_REQUEST_FIELDS = {
    "schema", "selection_content_id", "selected_candidate_id", "budget_unit",
    "department", "token_budget", "requested_tokens", "yield_claim", "eta_hat",
    "similarity_to_store",
}


def _canonical(payload: Any) -> bytes:
    try:
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise YwirRefuse("invalid_exchange", "expected finite UTF-8 JSON data") from error


def _content_id(namespace: str, payload: dict[str, Any]) -> str:
    return namespace + ":" + sha256(namespace.encode() + b"\x00" + _canonical(payload)).hexdigest()


def _fields(payload: Any, expected: set[str], name: str) -> None:
    if type(payload) is not dict or set(payload) != expected:
        raise YwirRefuse("invalid_request", f"{name} must contain exactly {sorted(expected)}")


def _text(value: Any, name: str) -> None:
    if type(value) is not str or not value.strip():
        raise YwirRefuse("invalid_request", f"{name} must be nonempty text")


def _integer(value: Any, name: str, *, nonnegative: bool = False) -> None:
    if type(value) is not int or (nonnegative and value < 0):
        raise YwirRefuse("invalid_request", f"{name} must be {'nonnegative ' if nonnegative else ''}integer")


def _finite(value: Any, name: str) -> None:
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise YwirRefuse("invalid_request", f"{name} must be a finite number")


def _validate_request(payload: Any) -> None:
    _fields(payload, _REQUEST_FIELDS, "request")
    if payload["schema"] != TOKEN_REQUEST_SCHEMA:
        raise YwirRefuse("unsupported_schema", "unsupported token-admission request schema")
    for name in ("selection_content_id", "selected_candidate_id"):
        _text(payload[name], name)
    if payload["budget_unit"] != "inference_token":
        raise YwirRefuse("unsupported_budget_unit", "YWIR accepts only inference_token")
    if payload["department"] not in DEPARTMENTS:
        raise YwirRefuse("unknown_department", "department must name a YWIR department")
    for name in ("token_budget", "requested_tokens"):
        _integer(payload[name], name, nonnegative=True)
        _finite(payload[name], name)
    claim = payload["yield_claim"]
    _fields(claim, {"expected_rank_delta", "expected_new_morphism"}, "yield_claim")
    _integer(claim["expected_rank_delta"], "expected_rank_delta")
    _finite(claim["expected_rank_delta"], "expected_rank_delta")
    if type(claim["expected_new_morphism"]) is not bool:
        raise YwirRefuse("invalid_request", "expected_new_morphism must be a boolean")
    for name in ("eta_hat", "similarity_to_store"):
        _finite(payload[name], name)
    _canonical(payload)


def evaluate_token_admission(payload: dict[str, Any]) -> dict[str, Any]:
    """Return deterministic advice bound to a caller-retained EDSPT selection.

    The caller must verify the selection content identity and selected candidate
    against its retained EDSPT result. YWIR does not import or recompute EDSPT.
    ``yield_claim`` is caller-declared token-yield evidence; expected measurement
    uncertainty reduction is never converted into a rank or morphism claim.
    """
    _validate_request(payload)
    request_id = _content_id("ywir:token-request", payload)
    # Every call evaluates an isolated declared context. These runtime occurrence
    # IDs are deliberately not exported as execution evidence or capabilities.
    host = open_host(
        request_id, {payload["department"]: payload["token_budget"]},
        eta_hat=payload["eta_hat"], base="observation-design-advisory",
    )
    proposal = Proposal(
        loop=request_id,
        department=payload["department"],
        tokens=payload["requested_tokens"],
        expected_rank_delta=payload["yield_claim"]["expected_rank_delta"],
        expected_new_morphism=payload["yield_claim"]["expected_new_morphism"],
        similarity_to_store=payload["similarity_to_store"],
    )
    verdict = decide(host, proposal)
    result = {
        "schema": TOKEN_RESULT_SCHEMA,
        "operation_id": TOKEN_ADMISSION_OPERATION,
        "package_version": PACKAGE_VERSION,
        "request_content_id": request_id,
        "proposal_content_id": verdict.proposal_id,
        "selection_content_id": payload["selection_content_id"],
        "selected_candidate_id": payload["selected_candidate_id"],
        "budget_unit": "inference_token",
        "authority_scope": "advisory_only",
        "department": payload["department"],
        "token_budget": payload["token_budget"],
        "requested_tokens": payload["requested_tokens"],
        "status": verdict.status,
        "admitted": verdict.admitted,
        "letter": verdict.letter,
        "support_code": support_code_for(verdict.status, verdict.refuse_code),
        "details": verdict.details,
        "advisory_token_cap": verdict.tokens if verdict.admitted else 0,
        "does_not_claim": list(DOES_NOT_CLAIM),
    }
    result["result_content_id"] = _content_id("ywir:token-admission", result)
    return result


def replay_token_admission(
    payload: dict[str, Any], retained: dict[str, Any],
) -> dict[str, Any]:
    """Recompute and compare the complete advisory result; return fresh advice.

    This does not replay a spend or revive a reservation. The caller records a
    fresh execution and verification identity around this deterministic result.
    """
    expected = evaluate_token_admission(payload)
    if type(retained) is not dict or _canonical(retained) != _canonical(expected):
        raise YwirRefuse("replay_mismatch", "retained token advice differs from exact reevaluation")
    return expected
