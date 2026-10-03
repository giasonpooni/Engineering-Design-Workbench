"""A real adapter: tabular CSV data -> CandidateChange (Phase 12).

Implements the `Adapter` protocol from `adapters/interface.py`, on the
same canonical boundary as `adapters/json_adapter.py` -- both normalize
into whole-field `add` CandidateChanges with the same
{"id","type","value","unit"} shape, and both use the same `__` joiner
convention for disambiguating multiple records sharing one
CanonicalState (see `adapters/json_adapter.py`'s module docstring for
why `__` and not `.`). This is what "CSV and JSON must converge on the
same canonical boundary" (Phase 12 §3) means concretely: there is one
normalization target, not two.

`CSVAdapter.normalize()` handles exactly ONE row, emitting BARE
(unprefixed) field ids -- e.g. row {"temperature_C": "180", ...} becomes
field id "temperature_C". This is what makes a single CSV row directly
comparable to a single JSON record for convergence (Phase 12 §7): same
row, same field ids, same values.

A CSV *file* normally has multiple rows describing multiple independent
samples (see the module-level example: P001/P002/P003). Collapsing all
of them into ONE CanonicalState under bare field ids would silently
overwrite one sample's "temperature_C" with the next row's value --
losing information, not "converging." `build_candidate_from_rows()`
below is the multi-row path: it disambiguates by prefixing every field
with the row's own identifying column value (same `__` joiner), so
P001/P002/P003 become "P001__temperature_C", "P002__temperature_C", etc.
-- "a clearly defined collection of canonical records" (Phase 12 §3),
still inside the one existing flat CanonicalState.fields model, not a
second semantic model.
"""

from __future__ import annotations

import csv
import io
from typing import Dict, List, Tuple

from adapters.interface import ExternalRecord
from core.canonical.delta import CandidateChange
from core.canonical.schema import FieldType
from core.canonical.version import ProvenanceInfo


def _coerce(raw_value: str):
    """CSV cells are always strings; recover the likely scalar/bool/
    string type. Deterministic, no locale/heuristic guessing beyond
    plain int/float parsing."""
    if raw_value in ("true", "True", "TRUE"):
        return True
    if raw_value in ("false", "False", "FALSE"):
        return False
    try:
        return int(raw_value)
    except ValueError:
        pass
    try:
        return float(raw_value)
    except ValueError:
        pass
    return raw_value


def _infer_type(value) -> FieldType:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "scalar"
    return "string"


def parse_csv_rows(csv_text: str, source: str) -> Tuple[ExternalRecord, ...]:
    """Pure parsing utility: CSV text -> one ExternalRecord per row, each
    already type-coerced. `source` identifies the file/stream; each
    record's own `source` also carries its row number so provenance
    stays traceable back to the exact row (Phase 12 §4)."""
    reader = csv.DictReader(io.StringIO(csv_text))
    records = []
    for row_number, row in enumerate(reader):
        coerced = {key: _coerce(value) for key, value in row.items()}
        records.append(ExternalRecord(raw=coerced, source=f"{source}:row{row_number}", format_hint="csv"))
    return tuple(records)


class CSVAdapter:
    """Adapter protocol implementation for a single already-parsed CSV
    row (see `parse_csv_rows` to get one from raw CSV text)."""

    def normalize(self, record: ExternalRecord) -> Tuple[CandidateChange, ...]:
        row: Dict = record.raw
        changes = []
        for field_id, value in row.items():
            provenance = ProvenanceInfo(
                author="csv_adapter", transaction_id=f"ingest:{record.source}", source=f"csv_adapter:{record.source}"
            )
            changes.append(
                CandidateChange(
                    path=f"fields.{field_id}",
                    operation="add",
                    old_value=None,
                    new_value={"id": field_id, "type": _infer_type(value), "value": value, "unit": None},
                    provenance=provenance,
                )
            )
        return tuple(changes)


def build_candidate_from_rows(
    rows: Tuple[ExternalRecord, ...], id_column: str
) -> Tuple[CandidateChange, ...]:
    """Multi-row path: disambiguate every row's fields by prefixing with
    that row's own `id_column` value, using the same `__` joiner
    `adapters/json_adapter.py` uses for nested paths -- one convention,
    reused, not a second one invented for CSV."""
    changes: List[CandidateChange] = []
    for record in rows:
        row: Dict = record.raw
        if id_column not in row:
            raise KeyError(f"row from {record.source!r} has no {id_column!r} column")
        row_id = row[id_column]
        for field_id, value in row.items():
            prefixed_id = f"{row_id}__{field_id}"
            provenance = ProvenanceInfo(
                author="csv_adapter",
                transaction_id=f"ingest:{record.source}",
                source=f"csv_adapter:{record.source}",
            )
            changes.append(
                CandidateChange(
                    path=f"fields.{prefixed_id}",
                    operation="add",
                    old_value=None,
                    new_value={"id": prefixed_id, "type": _infer_type(value), "value": value, "unit": None},
                    provenance=provenance,
                )
            )
    return tuple(changes)
