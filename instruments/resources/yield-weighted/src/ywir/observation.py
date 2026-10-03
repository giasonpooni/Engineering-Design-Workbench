"""Declared observations. YWIR does not embed text or run a judge."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Proposal:
    """Request to spend, compose, query a plant, or close."""

    loop: str
    department: str
    tokens: int
    expected_rank_delta: int = 0
    expected_new_morphism: bool = False
    compose_candidates: tuple[str, ...] = ()
    similarity_to_store: float = 0.0
    plant_refuse: str | None = None
    confidence_rising: bool = False
    eta_falling: bool = False
    request_evidence: bool = False
    close: bool = False
    reindex_base: str | None = None


@dataclass(frozen=True)
class Settlement:
    """What the caller measured after an admitted burst."""

    tokens_spent: int
    rank_delta: int
    glued: bool
    new_morphism_id: str | None = None
    new_morphism_type: str | None = None
    similarity_to_store: float = 0.0
    confidence_rising: bool = False
    eta_falling: bool = False
