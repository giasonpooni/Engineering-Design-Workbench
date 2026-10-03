"""Admission gate: the one door into the EvidencePool.

Same shape as `core/canonical/validation.py::validate_candidate`
(schema-shaped errors list, atomic accept/reject) applied one layer
upstream and to a much looser object domain -- pool objects are allowed
to be uncertain and conflicting (§E), so this gate checks *structural*
validity and the one rule §K makes non-negotiable, never "is this true."

Nothing here ever mutates `core.canonical` state or calls
`validate_candidate`; this module has no import from
`core.canonical.validation` or `core.canonical.version` at all -- see
`tests/test_scout_boundaries.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Union

from evidence.pool import EvidencePool
from evidence.types import ClaimedRelationship, DerivedGrounding, DerivedValue, Document, Observation, Record, Referent


@dataclass(frozen=True)
class AdmissionError:
    object_type: str
    code: str
    message: str


def admit_document(pool: EvidencePool, document: Document) -> Union[Document, List[AdmissionError]]:
    errors: List[AdmissionError] = []
    if not document.raw_content:
        errors.append(AdmissionError("Document", "EMPTY_CONTENT", "Document.raw_content is empty"))
    if not pool.has_source(document.source_id):
        errors.append(
            AdmissionError("Document", "UNKNOWN_SOURCE", f"source_id {document.source_id!r} not in pool")
        )
    return errors if errors else document


def admit_record(pool: EvidencePool, record: Record) -> Union[Record, List[AdmissionError]]:
    errors: List[AdmissionError] = []
    if not record.raw_content:
        errors.append(AdmissionError("Record", "EMPTY_CONTENT", "Record.raw_content is empty"))
    if not pool.has_document(record.document_id):
        errors.append(
            AdmissionError(
                "Record", "UNKNOWN_DOCUMENT", f"Record.document_id {record.document_id!r} not in pool"
            )
        )
    return errors if errors else record


def admit_observation(pool: EvidencePool, observation: Observation) -> Union[Observation, List[AdmissionError]]:
    """The one rule this phase treats as non-negotiable
    (`docs/PHASE_14_DATA_POOL_ARCHITECTURE.md` §K): a model-attributed
    extraction must carry a confidence that was actually supplied by the
    extractor, never a silently-defaulted 1.0 masquerading as a verbatim
    transcription. `Observation.confidence` is a required, non-Optional
    field by the time it reaches this gate (§types.py) -- so the check
    that matters happens earlier, at `scout.pipeline`'s
    `ExtractionCandidate -> Observation` boundary (see that module's
    docstring); this gate re-asserts the range and reference-integrity
    side of the same rule."""

    errors: List[AdmissionError] = []
    if not observation.record_ids:
        errors.append(AdmissionError("Observation", "NO_RECORD_IDS", "Observation must reference at least one Record"))
    for rid in observation.record_ids:
        if not pool.has_record(rid):
            errors.append(AdmissionError("Observation", "UNKNOWN_RECORD", f"record_id {rid!r} not in pool"))
    if not observation.extraction_method:
        errors.append(AdmissionError("Observation", "NO_EXTRACTION_METHOD", "extraction_method is required"))
    if not observation.content:
        errors.append(AdmissionError("Observation", "EMPTY_CONTENT", "Observation.content is empty"))
    return errors if errors else observation


def admit_referent(pool: EvidencePool, referent: Referent) -> Union[Referent, List[AdmissionError]]:
    errors: List[AdmissionError] = []
    if not referent.natural_key:
        errors.append(AdmissionError("Referent", "EMPTY_NATURAL_KEY", "Referent.natural_key is empty"))
    if not referent.kind:
        errors.append(AdmissionError("Referent", "EMPTY_KIND", "Referent.kind is empty"))
    return errors if errors else referent


def admit_claimed_relationship(
    pool: EvidencePool, relationship: ClaimedRelationship
) -> Union[ClaimedRelationship, List[AdmissionError]]:
    errors: List[AdmissionError] = []
    if not relationship.type:
        errors.append(AdmissionError("ClaimedRelationship", "EMPTY_TYPE", "ClaimedRelationship.type is empty"))
    if not pool.has_referent(relationship.from_referent_id):
        errors.append(
            AdmissionError(
                "ClaimedRelationship",
                "UNKNOWN_REFERENT",
                f"from_referent_id {relationship.from_referent_id!r} not in pool",
            )
        )
    if not pool.has_referent(relationship.to_referent_id):
        errors.append(
            AdmissionError(
                "ClaimedRelationship",
                "UNKNOWN_REFERENT",
                f"to_referent_id {relationship.to_referent_id!r} not in pool",
            )
        )
    if not pool.has_observation(relationship.observation_id):
        errors.append(
            AdmissionError(
                "ClaimedRelationship",
                "UNKNOWN_OBSERVATION",
                f"observation_id {relationship.observation_id!r} not in pool",
            )
        )
    return errors if errors else relationship


def admit_derived_value(pool: EvidencePool, derived_value: DerivedValue) -> Union[DerivedValue, List[AdmissionError]]:
    """Referential integrity is checked HERE, not in `make_derived_value`
    -- the same split already established by
    `admit_claimed_relationship`/`make_claimed_relationship`: a
    `DerivedValue` may be constructed whose `derived_from` ids are not
    (yet) in the pool, but it cannot be admitted until every one of them
    is either a known `Observation` or a known `DerivedValue`. This gate
    rejects a *dangling* reference -- an id that was never admitted at
    all. A true derivation cycle (A referencing B, B referencing A) is
    impossible for a separate, stronger reason that has nothing to do
    with this gate: see `evidence/types.py::DerivedValue`'s docstring for
    why content-addressed identity alone already rules it out."""

    errors: List[AdmissionError] = []
    if not derived_value.derived_from:
        errors.append(
            AdmissionError("DerivedValue", "NO_DERIVED_FROM", "DerivedValue must reference at least one input")
        )
    for did in derived_value.derived_from:
        if not (pool.has_observation(did) or pool.has_derived_value(did)):
            errors.append(
                AdmissionError(
                    "DerivedValue",
                    "UNKNOWN_INPUT",
                    f"derived_from id {did!r} is neither a known Observation nor a known DerivedValue",
                )
            )
    if not derived_value.method:
        errors.append(AdmissionError("DerivedValue", "NO_METHOD", "method is required"))
    if not derived_value.content:
        errors.append(AdmissionError("DerivedValue", "EMPTY_CONTENT", "DerivedValue.content is empty"))
    return errors if errors else derived_value


def admit_derived_grounding(
    pool: EvidencePool, grounding: DerivedGrounding
) -> Union[DerivedGrounding, List[AdmissionError]]:
    """Referential integrity only, same split every other admit_* gate
    already establishes: does the referenced DerivedValue exist, does
    every referenced Referent exist, is there at least one. Nothing here
    judges whether the grounding is *correct* -- that is not this gate's
    job for any evidence type."""

    errors: List[AdmissionError] = []
    if not pool.has_derived_value(grounding.derived_value_id):
        errors.append(
            AdmissionError(
                "DerivedGrounding",
                "UNKNOWN_DERIVED_VALUE",
                f"derived_value_id {grounding.derived_value_id!r} not in pool",
            )
        )
    if not grounding.referent_ids:
        errors.append(
            AdmissionError("DerivedGrounding", "NO_REFERENT_IDS", "DerivedGrounding must reference at least one Referent")
        )
    for rid in grounding.referent_ids:
        if not pool.has_referent(rid):
            errors.append(AdmissionError("DerivedGrounding", "UNKNOWN_REFERENT", f"referent_id {rid!r} not in pool"))
    return errors if errors else grounding
