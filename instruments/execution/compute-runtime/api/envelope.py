"""The response envelope: a response is grounded, or it says it is not.

THE INVARIANT, AS STATED: every API response either includes a canonical
reference and proof root, or explicitly says it is an operational
observation with its limitations.

WHY IT IS A TYPE AND NOT A CONVENTION. A convention is satisfied by
whoever remembers it, and the response that forgets is
indistinguishable from the response that had nothing to say. This
project has now met that shape four times -- an unreached gate reading
as a clean rate, a dropped field looking like a field that never
existed, a silence read as cleanliness, a register stale about itself --
and the fix each time was to make the absent case a STATED case rather
than a missing one.

So there is no third construction. An envelope carries exactly one
grounding, both arms are refused at construction if malformed, and a
response that is neither cannot be built at all.

WHAT THIS DOES NOT DO. It does not authenticate, authorise, or bind a
tenant -- none of those concepts exists in this tree yet, and an
envelope carrying a `tenant_id` field nothing enforces would be the
most dangerous object here: it would read as isolated while isolating
nothing. The plane is declared and its MUTATION POSTURE is enforced;
who may call it is not this module's claim to make.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping, Optional, Tuple, Union

# -- the four planes, and the one property this module can enforce ------
#
# Each plane is declared with whether it may MUTATE. That is not access
# control -- it is the shape of the plane, and it is checkable here
# because it is a property of the response rather than of the caller.
TENANT_READ = "tenant_read"
VERIFICATION = "verification"
GOVERNANCE = "governance"
INTERNAL_OPERATOR = "internal_operator"

#: plane -> may a response from it report a mutation?
PLANES: Mapping[str, bool] = MappingProxyType({
    TENANT_READ: False,
    VERIFICATION: False,
    GOVERNANCE: False,
    INTERNAL_OPERATOR: True,
})

#: The rule the plane table exists to carry: NEVER PUBLIC CANONICAL
#: CRUD. Three planes are read-only by construction, and the fourth is
#: the only one that may say it changed anything.
MUTATING_PLANES = tuple(name for name, mutates in PLANES.items() if mutates)


class EnvelopeError(ValueError):
    """A response that is neither grounded nor honestly ungrounded."""


@dataclass(frozen=True)
class CanonicalReference:
    """A response the reader can navigate back to evidence.

    BOTH FIELDS OR NEITHER. A reference without a proof root names
    something whose position in the graph cannot be checked, which is a
    citation rather than a warrant -- and a citation that cannot be
    resolved is the shape a fabricated one takes.
    """

    reference: str
    proof_root: str

    def __post_init__(self) -> None:
        if not self.reference:
            raise EnvelopeError("a canonical reference with no reference")
        if not self.proof_root:
            raise EnvelopeError(
                f"reference {self.reference!r} carries no proof root: a "
                f"reference whose position cannot be checked is a citation, "
                f"not a warrant")


@dataclass(frozen=True)
class OperationalObservation:
    """A response that is NOT a claim about canonical state, saying so.

    `limitations` is non-empty BY CONSTRUCTION. An observation whose
    limitations are empty is a canonical claim wearing a disclaimer, and
    it is the exact failure this arm exists to prevent: the arm is here
    so that ungrounded answers are STATED, not so that they are
    permitted quietly.
    """

    observed: str
    limitations: Tuple[str, ...]
    not_canonical_because: str

    def __post_init__(self) -> None:
        if not self.observed:
            raise EnvelopeError("an observation that does not say what it observed")
        if not self.limitations:
            raise EnvelopeError(
                "an operational observation with no limitations is a canonical "
                "claim wearing a disclaimer")
        if not self.not_canonical_because:
            raise EnvelopeError(
                "an observation must say WHY it is not canonical -- otherwise a "
                "reader cannot tell a deliberate observation from a lost proof")


Grounding = Union[CanonicalReference, OperationalObservation]


@dataclass(frozen=True)
class Envelope:
    """Exactly one grounding. There is no third construction."""

    plane: str
    payload: Mapping[str, object]
    grounding: Grounding
    #: The engine that produced it. A version label is a compatibility
    #: statement and many builds share one; the digest says WHICH build,
    #: which is what makes a stored answer checkable later against the
    #: engine it came from.
    engine_digest: str = ""
    reports_mutation: bool = False

    def __post_init__(self) -> None:
        if self.plane not in PLANES:
            raise EnvelopeError(
                f"unknown plane {self.plane!r}; declared: {sorted(PLANES)}")
        if not isinstance(self.grounding, (CanonicalReference, OperationalObservation)):
            raise EnvelopeError(
                "a response is grounded or it says it is not -- there is no "
                "third construction")
        if self.reports_mutation and not PLANES[self.plane]:
            raise EnvelopeError(
                f"plane {self.plane!r} is read-only and this response reports a "
                f"mutation. Never public canonical CRUD: only "
                f"{MUTATING_PLANES} may say it changed anything")
        if not self.engine_digest:
            raise EnvelopeError(
                "a response with no engine digest cannot be checked later "
                "against the build that produced it")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    @property
    def is_grounded(self) -> bool:
        return isinstance(self.grounding, CanonicalReference)


def grounded(plane: str, payload: Mapping[str, object], reference: str,
             proof_root: str, engine_digest: str,
             reports_mutation: bool = False) -> Envelope:
    return Envelope(plane=plane, payload=payload, engine_digest=engine_digest,
                    reports_mutation=reports_mutation,
                    grounding=CanonicalReference(reference=reference,
                                                 proof_root=proof_root))


def observed(plane: str, payload: Mapping[str, object], observed_what: str,
             limitations: Tuple[str, ...], because: str,
             engine_digest: str, reports_mutation: bool = False) -> Envelope:
    return Envelope(plane=plane, payload=payload, engine_digest=engine_digest,
                    reports_mutation=reports_mutation,
                    grounding=OperationalObservation(
                        observed=observed_what, limitations=tuple(limitations),
                        not_canonical_because=because))
