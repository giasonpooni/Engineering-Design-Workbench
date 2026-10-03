"""Spill taxonomy. Priority is fail-closed, not a score blend."""

from __future__ import annotations

from ywir.constitution import (
    EXPLORATION_DEPARTMENTS,
    GAUGE_DEPARTMENTS,
    GAUGE_SIMILARITY_CAP,
    YIELD_THRESHOLD,
)
from ywir.observation import Proposal
from ywir.store import CompositionStore


def classify(proposal: Proposal, store: CompositionStore, eta_hat: float) -> str | None:
    """Return a refuse code or None if the proposal may be admitted.

    None is not ACCEPT-world. It is only 'this kernel will emit ADMIT'.
    """
    if proposal.close:
        return "BUDGET_CLOSED"
    if proposal.request_evidence or proposal.plant_refuse:
        return "REQUEST_EVIDENCE"
    if proposal.compose_candidates:
        present = store.present(proposal.compose_candidates)
        if present:
            return "COMPOSE_INSTEAD"
    if proposal.eta_falling and proposal.confidence_rising:
        return "META_PRECISION_UNSTABLE"
    if proposal.department in GAUGE_DEPARTMENTS:
        return "GAUGE_SPILL"
    if (
        proposal.similarity_to_store >= GAUGE_SIMILARITY_CAP
        and proposal.expected_rank_delta <= 0
        and not proposal.expected_new_morphism
    ):
        return "GAUGE_SPILL"
    if (
        proposal.expected_rank_delta <= 0
        and not proposal.expected_new_morphism
        and proposal.department not in EXPLORATION_DEPARTMENTS
    ):
        return "RANK_FLAT"
    if eta_hat < YIELD_THRESHOLD and proposal.department not in EXPLORATION_DEPARTMENTS:
        return "YIELD_BELOW_THRESHOLD"
    return None
