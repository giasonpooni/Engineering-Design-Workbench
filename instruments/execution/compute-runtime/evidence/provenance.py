"""Provenance-ancestry traversal: a derived, read-only view over an
EvidencePool, exactly the same discipline `evidence/trust_graph.py`
already establishes for the Referent/ClaimedRelationship graph
(`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §G -- "graph = a derived
index over structured records, not the primary store"), applied here to
the *other* graph a pool already implicitly contains: the DerivedValue
dependency chain formed by `derived_from` (`evidence/types.py`).

That chain has been stored since Phase 17 but was never traversable --
nothing before this module could answer "what does this DerivedValue
ultimately rest on?" without manually walking `derived_from` by hand.
`ancestry_of` is that traversal, and nothing more: it does not attach a
DerivedValue to the Referent graph, does not feed retrieval or epistemic
classification, and does not change what a DerivedValue *is* -- see this
phase's own design specification for why those are separate, later
questions.

`ProvenanceAncestry` is a computed view, not a pool object: it has no
content-addressed `id`, is never stored in `EvidencePool`, and never
touches `fingerprint()`. Calling `ancestry_of` twice with the same
arguments always returns an equal (though not identical) result, the
same guarantee `build_trust_graph` already gives -- but there is no
identity to compare, because nothing here is evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Set, Tuple

from evidence.pool import EvidencePool
from evidence.types import DerivedValue


@dataclass(frozen=True)
class ProvenanceAncestry:
    root_derived_value_id: str
    observation_ids: Tuple[str, ...]
    derived_value_ids: Tuple[str, ...]


def ancestry_of(pool: EvidencePool, derived_value_id: str) -> ProvenanceAncestry:
    """Every Observation and DerivedValue a DerivedValue transitively
    depends on, via `derived_from` (`evidence/types.py::DerivedValue`).

    Raises `KeyError` if `derived_value_id` is not in the pool, or if
    traversal reaches a `derived_from` id that is neither a known
    Observation nor a known DerivedValue -- a properly admitted
    DerivedValue can never produce the latter case
    (`evidence/admission.py::admit_derived_value` already rejects a
    dangling reference before `put_derived_value` is ever called), so
    reaching it here means the pool was populated outside the admission
    gate; this function does not silently tolerate that, the same
    referential-integrity discipline admission itself enforces.

    `visited` doubles as cycle-safety for traversal (a genuine
    DerivedValue cycle cannot be constructed at all -- see
    `evidence/types.py::DerivedValue`'s docstring -- but this guards
    against malformed data regardless, without adding any new
    cycle-detection machinery). The root's own id seeds `visited` so it
    can never appear in the returned `derived_value_ids`, and iteration
    order never affects the result: both output tuples are id-sorted,
    not traversal-ordered.
    """
    root = pool.get_derived_value(derived_value_id)

    observation_ids: Set[str] = set()
    derived_value_ids: Set[str] = set()
    visited: Set[str] = {derived_value_id}
    frontier: List[DerivedValue] = [root]

    while frontier:
        current = frontier.pop()
        for ref_id in current.derived_from:
            if ref_id in visited:
                continue
            visited.add(ref_id)
            if pool.has_observation(ref_id):
                observation_ids.add(ref_id)
            elif pool.has_derived_value(ref_id):
                derived_value_ids.add(ref_id)
                frontier.append(pool.get_derived_value(ref_id))
            else:
                raise KeyError(
                    f"derived_from id {ref_id!r} (reached from DerivedValue "
                    f"{current.id!r}) is neither a known Observation nor a "
                    f"known DerivedValue"
                )

    return ProvenanceAncestry(
        root_derived_value_id=derived_value_id,
        observation_ids=tuple(sorted(observation_ids)),
        derived_value_ids=tuple(sorted(derived_value_ids)),
    )
