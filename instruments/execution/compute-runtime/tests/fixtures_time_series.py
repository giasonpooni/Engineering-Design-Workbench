"""Deterministic synthetic material/process time-series fixture (Phase 12
§6). This is a TEST FIXTURE, not part of the architecture -- analogous
to scripts/generate_sample_scene.py, nothing in core/, morpho/, or
backends/ depends on it.

Represents 6 samples across 7 channels (time, temperature, pressure,
torque, viscosity, strain, stress) as indexed scalar canonical fields
(`<channel>_t<index>`), chained by explicit "precedes" edges per
channel -- the same sequence-representation convention
adapters/json_adapter.py uses for JSON arrays (see that module's
docstring for why: the flat CanonicalState.fields model has no
first-class sequence type, so ordering is represented via naming +
explicit graph edges, both already-existing mechanisms, rather than
inventing a new one). See docs/DATA_CAPABILITIES.md for the honest scope
of this representation.

Values are synthetic but shaped like a real process ramp: temperature
rises then plateaus, pressure tracks it, viscosity falls as temperature
rises (shear-thinning-like), strain and stress rise together and begin
to plateau (yield-like). "The exact values can be synthetic" (Phase 12
§6) -- nothing about the numbers is meaningful outside this fixture.
"""

from __future__ import annotations

from typing import Dict, Tuple

from core.canonical.delta import CandidateChange, CandidateDelta
from core.canonical.schema import EdgeSchema, FieldSchema, StateSchema
from core.canonical.validation import validate_candidate
from core.canonical.version import ProvenanceInfo, Version, create_genesis_version

CHANNELS: Dict[str, Tuple[float, ...]] = {
    "time_s": (0.0, 1.0, 2.0, 3.0, 4.0, 5.0),
    "temperature_C": (20.0, 60.0, 120.0, 170.0, 185.0, 185.0),
    "pressure_MPa": (1.0, 2.1, 3.4, 4.0, 4.2, 4.2),
    "torque_Nm": (5.0, 5.6, 6.1, 5.8, 5.2, 5.0),
    "viscosity_Pa_s": (2000.0, 1600.0, 1100.0, 900.0, 850.0, 840.0),
    "strain": (0.0, 0.02, 0.05, 0.09, 0.14, 0.20),
    "stress_MPa": (0.0, 1.2, 2.6, 3.8, 4.5, 4.6),
}

SCHEMA_VERSION = "time-series-1.0.0"


def build_time_series_schema() -> StateSchema:
    fields = {}
    for channel, samples in CHANNELS.items():
        for index, value in enumerate(samples):
            field_id = f"{channel}_t{index}"
            fields[field_id] = FieldSchema(id=field_id, type="scalar", default=value)
    edges = (EdgeSchema(type="precedes"),)
    return StateSchema(schema_version=SCHEMA_VERSION, fields=fields, edges=edges)


def build_time_series_version(timestamp: str = "2026-08-22T00:00:00Z") -> Version:
    """Builds the fixture via the same two mechanisms every other test
    fixture in this repository uses -- no direct construction of a
    Version anywhere here. Field values come from
    create_genesis_version's schema-default bootstrap path (§4); the
    "precedes" sequence-ordering edges are then attached through
    validate_candidate itself, exactly like any other accepted update
    (see core/canonical/test_canonical.py's edge-add tests for the same
    pattern) -- preserving "only validation.py can mint accepted
    versions" without needing a special case for fixtures."""
    schema = build_time_series_schema()
    genesis = create_genesis_version(schema, timestamp)

    changes = []
    for channel, samples in CHANNELS.items():
        for index in range(len(samples) - 1):
            from_id = f"{channel}_t{index}"
            to_id = f"{channel}_t{index + 1}"
            edge_index = len(changes)
            provenance = ProvenanceInfo(author="fixture", transaction_id="tx-time-series", source="fixture:time_series")
            changes.append(
                CandidateChange(
                    path=f"edges[{edge_index}]",
                    operation="add",
                    old_value=None,
                    new_value={
                        "id": f"{from_id}__precedes__{to_id}",
                        "from": from_id,
                        "to": to_id,
                        "type": "precedes",
                        "attributes": {},
                    },
                    provenance=provenance,
                )
            )

    candidate = CandidateDelta(
        version_from=genesis.id, transaction_id="tx-time-series", timestamp=timestamp, changes=tuple(changes)
    )
    result = validate_candidate(schema, genesis.state, candidate)
    if isinstance(result, list):
        raise RuntimeError(f"time-series fixture failed validation: {result}")
    return result
