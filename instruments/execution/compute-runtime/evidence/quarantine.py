"""Quarantine: fail-closed never means silent loss.

A rejected ingest candidate is RETAINED -- with the failing invariant
ids attached -- queryable, and repairable; repair re-enters through
normal ingest (there is no force path, no bypass flag, and nothing in
this module can write to an EvidencePool at all). The rejection rate
per invariant per run is a reported metric: a high rate is evidence
about invariant calibration or source quality, never permission to
bypass.

The scout pipeline already retains its AdmissionErrors on the run
result; this store gives that surface the §rejection_policy shape --
wrap the errors, keep the payload, count by invariant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Tuple


@dataclass(frozen=True)
class QuarantinedRecord:
    """One rejected candidate: the payload as submitted, and why."""

    payload: Mapping[str, object]
    failing_invariant_ids: Tuple[str, ...]
    source_ref: str

    def __post_init__(self):
        if not self.failing_invariant_ids:
            raise ValueError(
                "a quarantined record names the invariants that failed it"
            )


class Quarantine:
    """Append-only store of rejections for one ingest run. A plain
    class (like EvidencePool itself): the STORE appends, while every
    record it holds is frozen."""

    def __init__(self) -> None:
        self.records: List[QuarantinedRecord] = []

    def hold(self, payload: Mapping[str, object], failing: Tuple[str, ...],
             source_ref: str) -> QuarantinedRecord:
        record = QuarantinedRecord(dict(payload), tuple(failing), source_ref)
        self.records.append(record)
        return record

    def by_invariant(self) -> Dict[str, int]:
        """The metric: rejection count per failing invariant id."""
        counts: Dict[str, int] = {}
        for record in self.records:
            for invariant_id in record.failing_invariant_ids:
                counts[invariant_id] = counts.get(invariant_id, 0) + 1
        return counts

    def rejection_rate(self, attempted: int) -> float:
        if attempted <= 0:
            return 0.0
        return len(self.records) / attempted
