"""Simulation backend seam (§16). INTERFACE SHAPES ONLY.

Do not implement a physics engine, a GPU simulator, or any dynamics logic
here (§23). This module exists so that a future simulation backend has a
fixed contract to build against: it consumes a frozen ProjectedState /
Morpho IR and produces a CandidateNextState, which must then pass through
core.canonical.validation.validate_candidate (via runtime/feedback_loop.py)
like any other candidate. No function in this module returns a
CanonicalState or Version.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

# Re-exported for callers that only need the simulation seam -- see
# core/canonical/delta.py for why CandidateNextState lives there rather
# than being defined in this file (§2: backends must not import each
# other, and both this module and backends/neural/interface.py need it).
from core.canonical.delta import CandidateNextState  # noqa: F401
from core.canonical.schema import FieldValue


class DynamicsSpec(Protocol):
    """Describes how a system evolves. Sourced from canonical state or a
    schema-declared config -- never authored ad hoc by a backend."""

    def describe(self) -> Mapping[str, FieldValue]: ...


@dataclass(frozen=True)
class Action:
    id: str
    payload: Mapping[str, FieldValue]
