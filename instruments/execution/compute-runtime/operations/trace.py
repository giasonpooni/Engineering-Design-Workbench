"""OperationTrace: an append-only record of what THIS SOFTWARE PROCESS DID.

THE SECOND LEDGER, AND WHY IT CANNOT BE THE FIRST
--------------------------------------------------
    EVIDENCE STATE     answers "what evidence exists?"
                       identity = f(content); order-invariant; a repeat is
                       a NO-OP; reproducible across runs, hosts and times
    OPERATION TRACE    answers "what did this process do?"
                       identity = f(occasion); order IS content; a repeat
                       is a SECOND EVENT; irreproducible by nature

Phase 122 established that these identity rules CONTRADICT: evidence
requires two identical occasions to collapse, an operation trace requires
them to remain two. No single object satisfies both, which is why this is
a separate module with its own identity scheme and no import of
`evidence.identity`.

WHAT THIS MODULE DOES NOT DO
-----------------------------
It records occurrences. It does NOT define when two occurrences are "the
same operation". Phase 123 found operation identity UNDERDETERMINED: of
ten cases, eight had no purpose-independent answer, and the axis sets
required by five plausible purposes have an EMPTY intersection and are
not nested. So no equivalence relation is imposed here. Retries,
repetitions, replicas and duplicates are all recorded as DISTINCT
OCCURRENCES, and deciding which are "the same" is left to whatever
consumer eventually asks -- because the purpose selects the axes, and the
axes fix the relation.

This module is the instrument from which that relation can later be
derived. It is not the relation.

OCCURRENCE IDENTITY
-------------------
A PROCESS-LOCAL MONOTONIC SEQUENCE NUMBER, and deliberately nothing else.

  NOT content-addressed -- that would collapse exactly the multiplicity
      this ledger exists to preserve.
  NOT a UUID -- this codebase admits no random identity anywhere, and one
      is not needed: the sequence is already unique within the process,
      which is the only scope this ledger claims.
  NOT a timestamp -- two occurrences can share a clock reading, and a
      clock is a recorded FACT here, never an identity.

The consequence is stated plainly: AN OCCURRENCE ID IS MEANINGFUL ONLY
WITHIN ONE `OperationTrace`. Two traces both have an occurrence 0. This
ledger makes no cross-process claim, and inventing one would require
choosing exactly the equivalence relation Phase 123 found underdetermined.

OBSERVED, NEVER CLAIMED
-----------------------
Every field records something THIS PROCESS CAN SEE: that a call was made,
that it returned, that it raised, what the exception's type was, what the
caller passed as a correlation token. Nothing here asserts anything about
the external world.

    "the dispatcher was called"   is recordable
    "the physical experiment occurred"  is NOT, and no field can hold it

    "the solver returned"         is recordable
    "the simulation was correct"  is NOT

That boundary is structural, not conventional: this module imports
nothing from `evidence/`, holds no `extraction_method`, no confidence, no
content, and cannot reach an `EvidencePool`. It stores an `output_ref` --
a reference a caller supplies -- never an output value, so it can never
become a second place where results live.

Phases 111/111b/119 stand unchanged: recording that a call happened is
not a witness that anything real happened, and this ledger does not
pretend otherwise. What it adds is narrower and genuinely new -- Phase
121 found that "never invoked" and "invoked and crashed" were BYTE-
IDENTICAL, and Phase 122 found six of eight execution facts
UNRECOVERABLE. Those are internal operational facts, and internal
operational facts are exactly what a process can honestly observe.

LIFECYCLE
---------
An explicit state machine, not nullable fields:

    INVOKED ──┬── STARTED ──┬── SUCCEEDED ──── REJECTED
              │             ├── FAILED
              │             └── TERMINATED
              └── NEVER_STARTED

REJECTED is reachable only from SUCCEEDED: it means the operation
returned a value and a DOWNSTREAM ADMISSION BOUNDARY refused it. That is
Phase 121's world C' -- previously visible only as an unenumerable,
unreliable orphan Record -- and it is the one case this instrument turns
from an accident into an observation.

Terminal states record no successor. An illegal transition raises rather
than being silently absorbed, so a caller cannot quietly produce a
history that never happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Callable, Dict, List, Mapping, Optional, Tuple

# -- lifecycle vocabulary (module constants + ALL_*, the convention
#    `materials/decision.py` already establishes -- not an Enum) --------------

INVOKED = "INVOKED"
NEVER_STARTED = "NEVER_STARTED"
STARTED = "STARTED"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
TERMINATED = "TERMINATED"
REJECTED = "REJECTED"

ALL_LIFECYCLE_STATES = (
    INVOKED, NEVER_STARTED, STARTED, SUCCEEDED, FAILED, TERMINATED, REJECTED,
)

#: The one place the state machine is written down. A state absent from a
#: successor tuple is unreachable from that state, and a state with an
#: empty tuple is terminal.
LEGAL_TRANSITIONS: Mapping[str, Tuple[str, ...]] = MappingProxyType({
    INVOKED: (STARTED, NEVER_STARTED),
    STARTED: (SUCCEEDED, FAILED, TERMINATED),
    SUCCEEDED: (REJECTED,),
    NEVER_STARTED: (),
    FAILED: (),
    TERMINATED: (),
    REJECTED: (),
})

TERMINAL_STATES = tuple(s for s, successors in LEGAL_TRANSITIONS.items() if not successors)


def _utc_now_iso() -> str:
    """An honest record of when this process ran, never a placeholder --
    the same discipline `workbench.interaction` already applies. Note the
    contrast with `evidence/`: there every time-shaped field is
    caller-supplied and EXCLUDED from identity, because including it
    would destroy reproducibility (Phase 122). Here a clock reading is a
    recorded fact about an occasion, which is what this ledger is for."""
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class OperationOccurrence:
    """One observed invocation. `occurrence` is a process-local sequence
    number -- see this module's docstring for why it is not a hash, not a
    UUID and not a timestamp.

    `parent` and `retry_of` are recorded ONLY when a caller supplies them.
    Nothing is inferred: a retry that the instrumentation cannot observe
    is simply two unrelated occurrences, which is the honest record."""

    occurrence: int
    operation: str
    invoked_at: str
    correlation: Optional[str] = None
    parent: Optional[int] = None
    retry_of: Optional[int] = None
    input_ref: Optional[str] = None


@dataclass(frozen=True)
class LifecycleTransition:
    """One observed lifecycle change. State is expressed as a sequence of
    these, never as a mutable field on the occurrence -- so the history
    is append-only in the same sense the evidence pool is, and for the
    same reason: a record that can be edited is not a record."""

    occurrence: int
    from_state: Optional[str]
    to_state: str
    at: str
    output_ref: Optional[str] = None
    failure_type: Optional[str] = None
    failure_code: Optional[str] = None
    detail: Optional[str] = None


class OperationTrace:
    """Append-only, in-process, single-writer -- the same shape as
    `EvidencePool`, with the opposite identity rule.

    NOTHING IS EVER DEDUPLICATED. Two invocations with identical
    arguments are two occurrences, by construction. That is the whole
    point (Phase 123 sec.2)."""

    def __init__(self, clock: Callable[[], str] = _utc_now_iso) -> None:
        self._clock = clock
        self._occurrences: List[OperationOccurrence] = []
        self._transitions: List[LifecycleTransition] = []
        self._state: Dict[int, str] = {}

    # -- recording ----------------------------------------------------------

    def invoke(
        self,
        operation: str,
        *,
        correlation: Optional[str] = None,
        parent: Optional[int] = None,
        retry_of: Optional[int] = None,
        input_ref: Optional[str] = None,
    ) -> int:
        """Record that a call was made. Returns the occurrence id.

        Identical arguments always produce a NEW occurrence."""
        if not operation:
            raise ValueError("OperationTrace.invoke requires a non-empty operation name")
        for label, referenced in (("parent", parent), ("retry_of", retry_of)):
            if referenced is not None and referenced not in self._state:
                raise ValueError(
                    f"{label}={referenced!r} is not an occurrence in this trace -- "
                    f"this ledger records only what it observed, and never invents a lineage"
                )

        occurrence = len(self._occurrences)
        now = self._clock()
        self._occurrences.append(OperationOccurrence(
            occurrence=occurrence, operation=operation, invoked_at=now,
            correlation=correlation, parent=parent, retry_of=retry_of,
            input_ref=input_ref,
        ))
        self._record(occurrence, None, INVOKED, now)
        return occurrence

    def started(self, occurrence: int) -> None:
        self._transition(occurrence, STARTED)

    def never_started(self, occurrence: int, *, detail: Optional[str] = None) -> None:
        self._transition(occurrence, NEVER_STARTED, detail=detail)

    def succeeded(self, occurrence: int, *, output_ref: Optional[str] = None) -> None:
        self._transition(occurrence, SUCCEEDED, output_ref=output_ref)

    def failed(
        self,
        occurrence: int,
        *,
        failure_type: Optional[str] = None,
        failure_code: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        self._transition(occurrence, FAILED, failure_type=failure_type,
                         failure_code=failure_code, detail=detail)

    def terminated(self, occurrence: int, *, detail: Optional[str] = None) -> None:
        self._transition(occurrence, TERMINATED, detail=detail)

    def rejected(
        self,
        occurrence: int,
        *,
        failure_code: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        """A downstream admission boundary refused the returned value.
        Reachable only from SUCCEEDED -- the operation produced something
        and something else declined it."""
        self._transition(occurrence, REJECTED, failure_code=failure_code, detail=detail)

    # -- reading ------------------------------------------------------------

    def occurrences(self) -> Tuple[OperationOccurrence, ...]:
        return tuple(self._occurrences)

    def transitions(self) -> Tuple[LifecycleTransition, ...]:
        return tuple(self._transitions)

    def transitions_of(self, occurrence: int) -> Tuple[LifecycleTransition, ...]:
        self._require(occurrence)
        return tuple(t for t in self._transitions if t.occurrence == occurrence)

    def state_of(self, occurrence: int) -> str:
        self._require(occurrence)
        return self._state[occurrence]

    def occurrences_in_state(self, state: str) -> Tuple[OperationOccurrence, ...]:
        if state not in ALL_LIFECYCLE_STATES:
            raise ValueError(f"unknown lifecycle state {state!r}; expected one of {ALL_LIFECYCLE_STATES}")
        return tuple(o for o in self._occurrences if self._state[o.occurrence] == state)

    # -- internals ----------------------------------------------------------

    def _require(self, occurrence: int) -> None:
        if occurrence not in self._state:
            raise KeyError(f"occurrence {occurrence!r} is not in this trace")

    def _transition(self, occurrence: int, to_state: str, **facts: Optional[str]) -> None:
        self._require(occurrence)
        current = self._state[occurrence]
        if to_state not in LEGAL_TRANSITIONS[current]:
            raise ValueError(
                f"illegal lifecycle transition {current} -> {to_state} for occurrence "
                f"{occurrence}; legal successors are {LEGAL_TRANSITIONS[current] or '(terminal)'}"
            )
        self._record(occurrence, current, to_state, self._clock(), **facts)

    def _record(
        self, occurrence: int, from_state: Optional[str], to_state: str, at: str,
        **facts: Optional[str],
    ) -> None:
        self._transitions.append(LifecycleTransition(
            occurrence=occurrence, from_state=from_state, to_state=to_state, at=at,
            **facts,
        ))
        self._state[occurrence] = to_state
