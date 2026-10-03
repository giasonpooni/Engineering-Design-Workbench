"""Neural / estimation seam (§17). INTERFACE SHAPES ONLY.

Do not implement Kalman filtering, Bayesian inference, or any neural
model here (§23). Neural systems may consume canonical state (read-only,
via ProjectedState) and may produce predictions, candidates, or inferred
relationships -- but the only function capable of minting a new Version
from any of it is core.canonical.validation.validate_candidate, reached
via runtime/feedback_loop.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from core.canonical.delta import CandidateNextState
from core.canonical.version import ProvenanceInfo
from core.projection.project import ProjectedState


@dataclass(frozen=True)
class Observation:
    raw: Any
    source: str
    timestamp: str


@dataclass(frozen=True)
class StructuredObservation:
    fields: dict
    provenance: ProvenanceInfo


@dataclass(frozen=True)
class BeliefState:
    candidate: CandidateNextState  # same shape as simulation's; validated identically
    confidence: float


class Estimator(Protocol):
    """Consumes structured observations plus optionally the current
    projected state; produces a belief/candidate -- never a Version
    directly."""

    def estimate(self, obs: StructuredObservation, current: ProjectedState) -> BeliefState: ...
