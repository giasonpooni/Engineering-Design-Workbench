"""FEP-facing signal: an INTERFACE, not an implementation of the Free
Energy Principle.

This module exists to give a future network-dynamics layer a stable
shape to consume -- it does not implement active inference, expected
free energy, or any variational objective. Three explicitly different
confidence levels are mixed together here and MUST NOT be conflated
(the instruction this module follows literally):

  ESTABLISHED IMPLEMENTATION -- `uncertainty` and `novelty` are pure
      functions of data this repository actually stores and computes
      (`evidence/metrics.py`), covered by tests.

  PROPOSED EXTENSION -- `relevance` and `investigation_cost` are
      caller-supplied numbers with NO scoring model implemented here;
      `priority` is a documented, clearly-labeled placeholder
      combination of the other fields, offered as one reasonable way to
      rank findings, not a validated formula.

  RESEARCH HYPOTHESIS -- `expected_information_gain` has no estimator
      anywhere in this codebase. It is always `None`. Its presence in
      this dataclass is the interface commitment ("a future estimator
      will fill this in"), not a claim that one exists.

See `docs/SCOUT_ARCHITECTURE.md` §5 for the full separation and the
non-implementation rationale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FEPSignal:
    observation_id: str

    # ESTABLISHED -- computed from evidence/metrics.py, deterministic.
    uncertainty: float
    novelty: float

    # PROPOSED EXTENSION -- caller-supplied, no scoring model implemented here.
    relevance: Optional[float] = None
    investigation_cost: Optional[float] = None

    # RESEARCH HYPOTHESIS -- no estimator exists; always None in this codebase.
    expected_information_gain: Optional[float] = None

    # PROPOSED EXTENSION -- only computed when relevance and
    # investigation_cost are both supplied; otherwise left None rather
    # than silently defaulting inputs that were never provided.
    priority: Optional[float] = None


def compute_fep_signal(
    observation_id: str,
    uncertainty: float,
    novelty: float,
    relevance: Optional[float] = None,
    investigation_cost: Optional[float] = None,
) -> FEPSignal:
    """Pure, deterministic assembly of an FEPSignal. `priority`, if
    computable, is `(uncertainty * novelty * relevance) / investigation_cost`
    -- a documented PLACEHOLDER combination (information-value-like
    numerator over cost), not a derivation from any stated objective
    function. Left `None` whenever an input needed to compute it is
    missing, rather than substituting a default that would make an
    unsupported number look supported."""
    priority = None
    if relevance is not None and investigation_cost is not None and investigation_cost > 0:
        priority = (uncertainty * novelty * relevance) / investigation_cost

    return FEPSignal(
        observation_id=observation_id,
        uncertainty=uncertainty,
        novelty=novelty,
        relevance=relevance,
        investigation_cost=investigation_cost,
        expected_information_gain=None,
        priority=priority,
    )
