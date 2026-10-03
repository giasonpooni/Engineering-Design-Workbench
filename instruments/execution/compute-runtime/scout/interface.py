"""SCOUT's stage interfaces (`docs/SCOUT_ARCHITECTURE.md` §6).

Every stage is a Protocol so the LLM/model sits behind exactly one of
them (`Extractor`) and is fully replaceable -- `scout.pipeline` depends
on these shapes, never on a concrete model provider. Everything else in
SCOUT (source acquisition wiring, normalization into `evidence.types`
objects, admission, network-state emission) is deterministic and has no
model dependency at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Protocol, Tuple

from evidence.types import Record


@dataclass(frozen=True)
class RawDocument:
    """What a SourceAdapter hands back -- pre-identity, pre-pool. Turned
    into an `evidence.types.Document` (which computes its own
    content-addressed id) by `scout.pipeline`, never by the adapter
    itself: an adapter's job is acquisition, not identity assignment."""

    source_name: str
    source_kind: str  # "paper" | "patent" | "github_repo" | "documentation" | ...
    content: str
    locator: str
    retrieval_method: str
    retrieved_at: str  # ISO-8601 UTC, caller-supplied -- never wall-clock


class SourceAdapter(Protocol):
    """Source acquisition (§1's pipeline). Implementations in this
    codebase are fixture-based only (`scout/adapters.py`) -- no live
    network access, so tests stay deterministic
    (`docs/SCOUT_ARCHITECTURE.md` §7). Nothing about this Protocol
    assumes that; a future adapter reading real papers/patents/repos
    would implement the same shape."""

    def fetch(self) -> Tuple[RawDocument, ...]: ...


@dataclass(frozen=True)
class ExtractedEntity:
    label: str
    kind: str


@dataclass(frozen=True)
class ExtractedRelation:
    from_label: str
    to_label: str
    type: str


@dataclass(frozen=True)
class ExtractionCandidate:
    """One candidate observation, pre-admission. `confidence` is
    Optional here -- and MUST be supplied (non-None) whenever
    `extraction_method` names a model (`"model:..."`); a deterministic
    extractor may leave it as the extractor's own fixed constant. This
    is enforced by `scout.pipeline.run_scout`, which raises rather than
    silently defaulting a missing model confidence to 1.0
    (`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §K)."""

    content: Mapping[str, object]
    entities: Tuple[ExtractedEntity, ...]
    relations: Tuple[ExtractedRelation, ...]
    extraction_method: str
    confidence: Optional[float]


class Extractor(Protocol):
    """Entity/relation/observation extraction (§1, §6). The ONE stage a
    future Mistral-based (or any other model) implementation plugs into.
    `scout/extraction.py`'s `DeterministicExtractor` is the only
    implementation in this codebase -- rule-based, no model, confidence
    fixed at 1.0 (verbatim transcription, per
    `docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §B's Observation table)."""

    def extract(self, record: Record) -> Tuple[ExtractionCandidate, ...]: ...
