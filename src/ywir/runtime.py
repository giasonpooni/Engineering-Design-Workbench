"""Admission runtime. Tokens are control. Structure is what glues."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
import json
import math
from threading import RLock
from uuid import uuid4

from ywir.constitution import (
    DEPARTMENTS,
    ETA_BLEND,
    MAX_BURST_TOKENS,
    MIN_TOKENS,
    PACKAGE_VERSION,
)
from ywir.departments import check_department
from ywir.errors import YwirRefuse
from ywir.observation import Proposal, Settlement
from ywir.receipts import YwirReceipt, from_verdict
from ywir.spill import classify
from ywir.store import CompositionStore, Morphism


GIT_PIN_UNSET = "in_development"


@dataclass
class HostState:
    loop: str
    budget: dict[str, int]
    eta_hat: float = 0.0
    base: str = "default"
    store: CompositionStore = field(default_factory=CompositionStore)
    closed: bool = False
    host_id: str = field(default_factory=lambda: _occurrence("host"), init=False)
    _reservations: dict[str, Reservation] = field(default_factory=dict, init=False, repr=False)
    _consumed: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _settlements: dict[str, SettlementRecord] = field(default_factory=dict, init=False, repr=False)
    _lock: object = field(default_factory=RLock, init=False, repr=False, compare=False)


def _occurrence(kind: str) -> str:
    return f"ywir:{kind}:{uuid4().hex}"


@dataclass(frozen=True)
class Reservation:
    """Process-local spending capability; a receipt or decision is not one."""

    reservation_id: str
    host_id: str
    loop: str
    base: str
    proposal_id: str
    decision_id: str
    department: str
    tokens: int


@dataclass(frozen=True)
class SettlementRecord:
    settlement_id: str
    reservation_id: str
    host_id: str
    loop: str
    base: str
    proposal_id: str
    decision_id: str
    department: str
    reserved_tokens: int
    tokens_spent: int
    outcome: Settlement


@dataclass(frozen=True)
class Verdict:
    status: str
    letter: str
    details: str
    refuse_code: str | None = None
    admitted: bool = False
    department: str | None = None
    tokens: int = 0
    compose_ids: tuple[str, ...] = ()
    host_id: str | None = None
    loop: str | None = None
    proposal_id: str | None = None
    decision_id: str | None = None

    def receipt(self, loop: str, git_pin: str = GIT_PIN_UNSET) -> YwirReceipt:
        if self.loop is not None and loop != self.loop:
            raise YwirRefuse("loop_mismatch", "receipt loop differs from its decision")
        return from_verdict(
            loop,
            self.status,
            self.letter,
            self.details,
            git_pin=git_pin,
            refuse_code=self.refuse_code,
            host_id=self.host_id,
            proposal_id=self.proposal_id,
            decision_id=self.decision_id,
        )


def _text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise YwirRefuse("invalid_text", f"{name} must be a non-empty string")


def _integer(value: object, name: str, *, nonnegative: bool = False) -> None:
    if type(value) is not int:
        raise YwirRefuse("invalid_integer", f"{name} must be an integer, not bool or float")
    if nonnegative and value < 0:
        raise YwirRefuse("negative_budget" if name.startswith("budget") else "negative_spend", name)
    _finite(value, name)


def _finite(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise YwirRefuse("invalid_number", f"{name} must be a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise YwirRefuse("invalid_number", f"{name} must be finite")


def _boolean(value: object, name: str) -> None:
    if type(value) is not bool:
        raise YwirRefuse("invalid_boolean", f"{name} must be a boolean")


def _similarity(value: object) -> None:
    _finite(value, "similarity_to_store")
    if not 0 <= value <= 1:
        raise YwirRefuse("invalid_similarity", "similarity must lie in [0, 1]")


def _validate_host(host: HostState) -> None:
    _text(host.loop, "loop")
    _text(host.base, "base")
    _finite(host.eta_hat, "eta_hat")
    _boolean(host.closed, "closed")
    if set(host.budget) != set(DEPARTMENTS):
        raise YwirRefuse("invalid_budget", "host budget must contain exactly the departments")
    for department, amount in host.budget.items():
        _integer(amount, f"budget.{department}", nonnegative=True)
        if _reserved(host, department) > amount:
            raise YwirRefuse("invalid_budget", "budget is below its outstanding reservations")


def _validate_proposal(proposal: Proposal) -> None:
    if not isinstance(proposal, Proposal):
        raise YwirRefuse("invalid_proposal", "expected Proposal")
    _text(proposal.loop, "loop")
    check_department(proposal.department)
    _integer(proposal.tokens, "tokens", nonnegative=True)
    _integer(proposal.expected_rank_delta, "expected_rank_delta")
    _similarity(proposal.similarity_to_store)
    for name in ("expected_new_morphism", "confidence_rising", "eta_falling", "request_evidence", "close"):
        _boolean(getattr(proposal, name), name)
    if type(proposal.compose_candidates) is not tuple:
        raise YwirRefuse("invalid_proposal", "compose_candidates must be an immutable tuple")
    for candidate in proposal.compose_candidates:
        _text(candidate, "compose_candidates")
    for name in ("plant_refuse", "reindex_base"):
        if getattr(proposal, name) is not None:
            _text(getattr(proposal, name), name)


def _proposal_id(proposal: Proposal) -> str:
    _validate_proposal(proposal)
    encoded = json.dumps(asdict(proposal), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return "ywir:proposal:" + sha256(b"ywir.proposal.v1\x00" + encoded).hexdigest()


def _reserved(host: HostState, department: str) -> int:
    return sum(item.tokens for item in host._reservations.values() if item.department == department)


def open_host(
    loop: str,
    budget: dict[str, int] | None = None,
    *,
    eta_hat: float = 0.0,
    base: str = "default",
) -> HostState:
    if not loop:
        raise YwirRefuse("missing_loop", "loop name is required")
    raw = dict(budget) if budget is not None else {d: 0 for d in DEPARTMENTS}
    for name, value in raw.items():
        check_department(name)
        _integer(value, f"budget.{name}", nonnegative=True)
    for name in DEPARTMENTS:
        raw.setdefault(name, 0)
    extra = [k for k in raw if k not in DEPARTMENTS]
    if extra:
        raise YwirRefuse("unknown_department", ",".join(extra))
    host = HostState(loop=loop, budget=raw, eta_hat=eta_hat, base=base)
    _validate_host(host)
    return host


def decide(host: HostState, proposal: Proposal) -> Verdict:
    """Advisory spend decision. Explicit close/reindex commands still mutate.

    ADMIT does not reserve tokens; use reserve before performing work.
    """
    with host._lock:
        _validate_host(host)
        proposal_id = _proposal_id(proposal)
        return replace(_decide(host, proposal), host_id=host.host_id, loop=host.loop,
                       proposal_id=proposal_id, decision_id=_occurrence("decision"))


def _decide(host: HostState, proposal: Proposal) -> Verdict:
    if proposal.loop != host.loop:
        raise YwirRefuse("loop_mismatch", f"{proposal.loop} != {host.loop}")
    check_department(proposal.department)
    if host.closed:
        return Verdict(
            status="closed",
            letter="CLOSE_BUDGET",
            details="host already closed",
            refuse_code="BUDGET_CLOSED",
        )
    if proposal.close:
        if host._reservations:
            raise YwirRefuse("pending_reservations", "settle or cancel before closing")
        host.closed = True
        return Verdict(
            status="closed",
            letter="CLOSE_BUDGET",
            details="caller closed the budget",
            refuse_code="BUDGET_CLOSED",
        )
    if proposal.reindex_base is not None:
        if host._reservations:
            raise YwirRefuse("pending_reservations", "settle or cancel before reindexing")
        host.base = proposal.reindex_base
        return Verdict(
            status="reindexed",
            letter="REINDEX",
            details=f"base={host.base}",
            department=proposal.department,
        )
    if proposal.tokens < MIN_TOKENS or proposal.tokens > MAX_BURST_TOKENS:
        raise YwirRefuse(
            "burst_out_of_range",
            f"tokens={proposal.tokens} not in [{MIN_TOKENS}, {MAX_BURST_TOKENS}]",
        )

    code = classify(proposal, host.store, host.eta_hat)
    if code == "REQUEST_EVIDENCE":
        return Verdict(
            status="evidence",
            letter="REQUEST_EVIDENCE",
            details=proposal.plant_refuse or "evidence required",
            refuse_code="REQUEST_EVIDENCE",
            department=proposal.department,
        )
    if code == "COMPOSE_INSTEAD":
        present = host.store.present(proposal.compose_candidates)
        return Verdict(
            status="composed",
            letter="COMPOSE",
            details="accepted morphism already answers",
            refuse_code="COMPOSE_INSTEAD",
            department=proposal.department,
            compose_ids=present,
        )
    if code is not None:
        return Verdict(
            status="refused",
            letter="REFUSE_SPILL",
            details=code,
            refuse_code=code,
            department=proposal.department,
            tokens=proposal.tokens,
        )

    remaining = host.budget[proposal.department] - _reserved(host, proposal.department)
    if remaining <= 0:
        return Verdict(
            status="refused",
            letter="REFUSE_SPILL",
            details=f"{proposal.department} budget closed",
            refuse_code="BUDGET_CLOSED",
            department=proposal.department,
        )
    if proposal.tokens > remaining:
        return Verdict(
            status="refused",
            letter="REFUSE_SPILL",
            details=f"{proposal.department} has {remaining}, asked {proposal.tokens}",
            refuse_code="DEPARTMENT_STARVED",
            department=proposal.department,
            tokens=proposal.tokens,
        )
    return Verdict(
        status="admitted",
        letter="ADMIT",
        details=f"admit {proposal.tokens} on {proposal.department}",
        admitted=True,
        department=proposal.department,
        tokens=proposal.tokens,
    )


def _validate_settlement(settlement: Settlement) -> None:
    if not isinstance(settlement, Settlement):
        raise YwirRefuse("invalid_settlement", "expected Settlement")
    _integer(settlement.tokens_spent, "tokens_spent", nonnegative=True)
    _integer(settlement.rank_delta, "rank_delta")
    _similarity(settlement.similarity_to_store)
    for name in ("glued", "confidence_rising", "eta_falling"):
        _boolean(getattr(settlement, name), name)
    for name in ("new_morphism_id", "new_morphism_type"):
        if getattr(settlement, name) is not None:
            _text(getattr(settlement, name), name)
    if settlement.new_morphism_type is not None and settlement.new_morphism_id is None:
        raise YwirRefuse("invalid_settlement", "morphism type requires morphism id")


def observed_yield(settlement: Settlement) -> float:
    _validate_settlement(settlement)
    structure = 0.0
    if settlement.rank_delta > 0:
        structure += float(settlement.rank_delta)
    if settlement.glued:
        structure += 1.0
    if settlement.new_morphism_id:
        structure += 1.0
    structure -= settlement.similarity_to_store
    if settlement.eta_falling and settlement.confidence_rising:
        structure -= 1.0
    spent = max(settlement.tokens_spent, 1)
    return structure / float(spent)


def reserve(host: HostState, proposal: Proposal) -> Reservation:
    """Atomically admit and hold a burst in this host's process-local state."""
    with host._lock:
        _validate_proposal(proposal)
        if proposal.close or proposal.reindex_base is not None:
            raise YwirRefuse("not_spend_proposal", "reserve accepts spending proposals only")
        decision = decide(host, proposal)
        if not decision.admitted:
            raise YwirRefuse(decision.refuse_code or "not_admitted", decision.details)
        reservation = Reservation(
            _occurrence("reservation"), host.host_id, host.loop, host.base,
            decision.proposal_id, decision.decision_id, proposal.department, proposal.tokens,
        )
        # Keep a separate immutable value, not the caller's object reference.
        host._reservations[reservation.reservation_id] = replace(reservation)
        return reservation


def _pending(host: HostState, reservation: Reservation | None) -> Reservation:
    if not isinstance(reservation, Reservation):
        raise YwirRefuse("reservation_required", "call reserve before settling; ADMIT is advisory")
    if reservation.host_id != host.host_id or reservation.loop != host.loop:
        raise YwirRefuse("reservation_host_mismatch", "reservation belongs to a different host or loop")
    if reservation.base != host.base:
        raise YwirRefuse("reservation_base_mismatch", "host base changed after reservation")
    if reservation.reservation_id in host._consumed:
        raise YwirRefuse("reservation_consumed", "reservation already settled or cancelled")
    retained = host._reservations.get(reservation.reservation_id)
    if retained is None or retained != reservation:
        raise YwirRefuse("unknown_reservation", "reservation is not the retained pending capability")
    return retained


def cancel(host: HostState, reservation: Reservation) -> None:
    """Release a pending hold without spending; this capability is consumed."""
    with host._lock:
        _validate_host(host)
        retained = _pending(host, reservation)
        host._consumed[retained.reservation_id] = "cancelled"
        del host._reservations[retained.reservation_id]


def settle(
    host: HostState, proposal: Proposal, settlement: Settlement, *,
    reservation: Reservation | None = None,
) -> SettlementRecord:
    """Consume one pending reservation. Replays are refused, not recharged.

    All validation and store preparation precede mutation. Atomicity covers
    these API calls sharing one HostState, not direct field mutation, process
    crashes, persistence, distributed execution, or external token providers.
    """
    with host._lock:
        _validate_host(host)
        proposal_id = _proposal_id(proposal)
        _validate_settlement(settlement)
        retained = _pending(host, reservation)
        if proposal.loop != host.loop:
            raise YwirRefuse("loop_mismatch", "proposal belongs to a different loop")
        if proposal_id != retained.proposal_id:
            raise YwirRefuse("reservation_proposal_mismatch", "proposal changed after admission")
        if host.closed:
            raise YwirRefuse("budget_closed", "cannot settle a closed host")
        if settlement.tokens_spent > retained.tokens:
            raise YwirRefuse("overspend", "settlement exceeds this reservation's admitted cap")
        if not settlement.glued:
            raise YwirRefuse("H1_NO_GLUE", "settlement did not restrict")
        next_eta = (1.0 - ETA_BLEND) * host.eta_hat + ETA_BLEND * observed_yield(settlement)
        _finite(next_eta, "updated eta_hat")
        staged_store = host.store
        if settlement.new_morphism_id:
            if settlement.new_morphism_id in host.store:
                raise YwirRefuse("morphism_conflict", "morphism identity is already accepted")
            staged_store = deepcopy(host.store)
            staged_store.accept(Morphism(
                morphism_id=settlement.new_morphism_id,
                type_name=settlement.new_morphism_type or "undeclared",
                department=retained.department, loop=host.loop,
            ))
        record = SettlementRecord(
            _occurrence("settlement"), retained.reservation_id, host.host_id, host.loop, retained.base,
            proposal_id, retained.decision_id, retained.department, retained.tokens, settlement.tokens_spent,
            replace(settlement),
        )
        host.budget[retained.department] -= settlement.tokens_spent
        host.eta_hat = next_eta
        host.store = staged_store
        host._settlements[record.settlement_id] = replace(record, outcome=replace(record.outcome))
        host._consumed[retained.reservation_id] = "settled"
        del host._reservations[retained.reservation_id]
        return record


def snapshot(host: HostState) -> dict[str, object]:
    """Observational snapshot, not a reconstructible admission capability."""
    with host._lock:
        _validate_host(host)
        reserved = {department: _reserved(host, department) for department in DEPARTMENTS}
        return {
            "instrument": "ywir",
            "package_version": PACKAGE_VERSION,
            "loop": host.loop,
            "base": host.base,
            "closed": host.closed,
            "eta_hat": host.eta_hat,
            "budget": dict(host.budget),
            "store": list(host.store.ids()),
            "host_id": host.host_id,
            "reserved": reserved,
            "available": {department: host.budget[department] - reserved[department] for department in DEPARTMENTS},
            "pending_reservations": len(host._reservations),
            "settlement_count": len(host._settlements),
            "authority_scope": "process_local_observation_only",
        }
