"""External data adapter boundary.

NOT part of docs/ARCHITECTURE_SPEC.md's original 23 sections -- this
package did not exist in the frozen specification this repository
otherwise implements exactly. It was added on explicit request in this
session (Phase 10) and is flagged here, and in that session's report,
rather than silently presented as if it had always been part of the
frozen contract. See the session report for the reasoning.

It is additive only. It introduces one new, OPTIONAL producer of the
CandidateDelta shape that already existed in core/canonical/delta.py. It
does not modify validate_candidate, CanonicalState, StateSchema, or any
existing invariant -- it just gives an external-data source the same
"produce a candidate, then go through the one door" shape that
backends/simulation/interface.py and backends/neural/interface.py
already established for simulation and neural candidates:

    External Data
        |
        v
    Adapter.normalize()        <-- INTERFACE SHAPE ONLY, no implementation
        |
        v
    CandidateDelta               (existing shape, core/canonical/delta.py)
        |
        v
    validate_candidate()           <-- existing, unchanged, sole entry point
        |
        v
    Version | ValidationError[]

Do NOT implement a real adapter (CSV, sensor telemetry, knowledge-graph
importer, ML output, etc.) here -- only the interface shape, per this
session's "do not overbuild" instruction. Do NOT introduce an ontology or
a universal schema: ExternalRecord below deliberately says nothing about
the *meaning* of the payload it carries -- that is entirely deferred to
whatever StateSchema (§6) is active for a given domain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol, Tuple

from core.canonical.delta import CandidateChange, CandidateDelta
from core.canonical.version import VersionId


@dataclass(frozen=True)
class ExternalRecord:
    """The one generic shape every adapter receives. Deliberately opaque
    about payload meaning: `raw` is whatever the source format is (a CSV
    row, a sensor reading, a JSON blob, a knowledge-graph triple) --
    interpreting it is the adapter's job, not this dataclass's."""

    raw: Any
    source: str
    format_hint: Optional[str] = None


class Adapter(Protocol):
    """Normalizes one ExternalRecord into the CandidateChange shape
    validate_candidate already accepts. An adapter never constructs a
    CanonicalState, Version, or EdgeRecord directly -- it only produces
    candidate changes, which still have to pass through validate_candidate
    like every other candidate source (simulation, neural, manual edit)."""

    def normalize(self, record: ExternalRecord) -> Tuple[CandidateChange, ...]: ...


def build_candidate_delta(
    adapter: Adapter,
    record: ExternalRecord,
    version_from: Optional[VersionId],
    transaction_id: str,
    timestamp: str,
) -> CandidateDelta:
    """Pure composition helper: wraps an adapter's normalized changes
    into the existing CandidateDelta shape. Does not call
    validate_candidate itself -- that step is the caller's
    responsibility, exactly as it is for runtime/feedback_loop.py's
    simulation/neural candidates."""
    changes = adapter.normalize(record)
    return CandidateDelta(
        version_from=version_from, transaction_id=transaction_id, timestamp=timestamp, changes=changes
    )
