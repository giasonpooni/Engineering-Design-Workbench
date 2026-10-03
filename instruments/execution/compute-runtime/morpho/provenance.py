"""Morpho provenance model (§10).

Every canonical-sourced Morpho construct carries `source="canonical"`,
`confidence=None`, and `origin_version` equal to the exact Version.id
frozen for that compilation. Every derived/inferred construct must carry
a ProvenanceRecord naming its producing subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ProvenanceRecord:
    source: str
    origin_version: str
    compiler_version: str
    transaction_id: Optional[str] = None
    confidence: Optional[float] = None
    timestamp: Optional[str] = None


def canonical_provenance(
    origin_version: str,
    compiler_version: str,
    transaction_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> ProvenanceRecord:
    return ProvenanceRecord(
        source="canonical",
        origin_version=origin_version,
        compiler_version=compiler_version,
        transaction_id=transaction_id,
        confidence=None,
        timestamp=timestamp,
    )


def derived_provenance(
    source: str,
    origin_version: str,
    compiler_version: str,
    confidence: Optional[float] = None,
    transaction_id: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> ProvenanceRecord:
    if source == "canonical":
        raise ValueError('derived_provenance() cannot be called with source="canonical"')
    return ProvenanceRecord(
        source=source,
        origin_version=origin_version,
        compiler_version=compiler_version,
        transaction_id=transaction_id,
        confidence=confidence,
        timestamp=timestamp,
    )
