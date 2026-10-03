"""ExperimentalResult + admit_experimental_result: the bridge between an
executed campaign entry and new SCOUT evidence -- the first point in
this entire pipeline where the flow reverses direction. Every layer
since `materials.analysis` has been READ-ONLY over `EvidencePool`; this
module is the one place that WRITES to it, and it does so using nothing
but the existing, unmodified public admission API
(`evidence.admission.admit_observation`/`admit_claimed_relationship`,
`evidence.types.make_observation`/`make_claimed_relationship`). No new
evidence type, no parallel store, no substrate modification.

Before writing this module, the existing admission API was inspected end
to end (`evidence.types.Observation`/`Source`/`Document`/`Record`/
`Referent`/`ClaimedRelationship`, every `admit_*` gate in
`evidence.admission`, and -- critically -- how `materials.analysis.analyze`
and `retrieval.engine.DeterministicRetrievalEngine` actually decide an
Observation is "about" a Referent). The answer: an Observation only
becomes visible to `analyze()` when a `ClaimedRelationship` connects the
queried Referent to some other, already-admitted Referent, with that
relationship's `observation_id` set to the new Observation -- exactly
the `tested_during` pattern every workload fixture in this repository
has already used since Phase 30. This is not a new discovery; it is
confirmed directly by reading `retrieval/engine.py`'s
`_bounded_neighborhood`/`retrieve`: a relationship is only retrieved
when BOTH its endpoints are already-admitted Referents within the
traversal, and `analyze()`'s own query places no restriction on
relationship `type`, so `tested_during` is a realistic default, never a
structural requirement enforced by this module.

Two concepts, kept as separate as Phase 39-41 kept eligibility/selection
and specified/inherited parameters:

  ExperimentalResult -- an application-level description of what was
  actually obtained: which campaign/candidate produced it, which
  formulation/property it concerns, and the measured content (an open
  `Mapping[str, object]`, exactly `Observation.content`'s own shape --
  no new schema is invented beyond what the caller supplies). Building
  one touches `EvidencePool` not at all.

  admit_experimental_result -- the only thing that ever mutates the
  pool: constructs a genuine, new `Observation` from the result's
  content and a caller-provided `record_id` (the caller is responsible
  for having already admitted the Source/Document/Record chain this
  measurement was transcribed into -- this module reuses that existing
  mechanism rather than inventing a second one), admits it through the
  unmodified `admit_observation` gate, then connects it to the result's
  formulation via a `ClaimedRelationship` to the already-admitted
  process Referent (resolved by natural key, reusing
  `materials.analysis._resolve_referent` rather than duplicating that
  scan), admitted through the unmodified `admit_claimed_relationship`
  gate. Confidence is never invented here or defaulted: it is a
  required parameter to `admit_experimental_result`, exactly the same
  discipline `evidence.admission.admit_observation`'s own docstring
  establishes for every extraction.

No quality score, confidence score (beyond the one SCOUT's own
Observation type already requires to admit anything at all), probability,
utility, expected-information-gain, ranking, or automatic interpretation
is added anywhere in this module. `ExperimentalResult` represents what
was obtained, not what the system believes about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import List, Mapping, Tuple, Union

from evidence.admission import AdmissionError, admit_claimed_relationship, admit_observation
from evidence.identity import content_hash
from evidence.pool import EvidencePool
from evidence.types import ClaimedRelationship, Observation, Referent, make_claimed_relationship, make_observation
from materials.analysis import _resolve_referent
from materials.campaign import ExperimentalCampaign, ExperimentalCampaignEntry


@dataclass(frozen=True)
class ExperimentalResult:
    """What was actually obtained for one campaign entry -- content-
    addressed (`id`), never mutated after construction, and carries no
    interpretive field (no confidence/quality/probability). `content`
    must already include a `"property"` key equal to `property` --
    `make_experimental_result` enforces this rather than silently
    injecting it, so `content` always reflects exactly what the caller
    supplied, nothing added."""

    id: str
    campaign_id: str
    candidate_id: str
    formulation: Referent
    property: str
    process_natural_key: str
    content: Mapping[str, object]
    record_id: str
    extraction_method: str
    extracted_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "content", MappingProxyType(dict(self.content)))


def make_experimental_result(
    campaign: ExperimentalCampaign,
    entry: ExperimentalCampaignEntry,
    content: Mapping[str, object],
    record_id: str,
    extracted_at: str,
    extraction_method: str,
) -> ExperimentalResult:
    """The only supported way to construct an ExperimentalResult --
    mirrors every `make_*` factory in `evidence/types.py`: `id` is
    always derived from content, never supplied by the caller.
    `campaign`/`entry` are embedded by reference only for the fields
    that identify provenance (`campaign.id`, `entry.candidate_id`,
    `entry.formulation`, `entry.property`,
    `campaign.process_natural_key`) -- neither object itself is stored,
    so this result stays a small, self-contained value.

    `extraction_method` is REQUIRED, with no default. It previously
    defaulted to `"measurement:campaign_execution"`, which made this the
    only factory in production that converted a caller's SILENCE into a
    positive assertion that a measurement occurred in the external world
    (Phase 118/119; the exhaustive default sweep is locked in
    `tests/test_phase119_declared_vs_witnessed.py`). Every other default
    in this codebase either preserves uncertainty
    (`make_experiment_session(initial_state=EMPTY_MODEL_STATE)`), or
    describes what the function itself does (`ordering="sorted_by_id"`),
    or is presentation geometry. A caller must now state what happened.

    This does NOT establish that the declared event occurred. Phase 119
    demonstrates that a genuine measurement, a fabricated value, a
    simulation and a hand-typed number collapse to one identical
    `Observation` whenever the caller declares the same method. Requiring
    the declaration removes the architecture's own unsolicited claim; it
    does not, and cannot, supply a witness."""
    if not content:
        raise ValueError("ExperimentalResult.content must not be empty")
    if content.get("property") != entry.property:
        raise ValueError(
            f"content['property'] must equal the campaign entry's property {entry.property!r}, "
            f"got {content.get('property')!r} -- this module never injects or corrects it"
        )

    result_id = content_hash({
        "campaign_id": campaign.id,
        "candidate_id": entry.candidate_id,
        "formulation_id": entry.formulation.id,
        "property": entry.property,
        "content": dict(sorted(content.items())),
        "record_id": record_id,
        "extraction_method": extraction_method,
    })
    return ExperimentalResult(
        id=result_id, campaign_id=campaign.id, candidate_id=entry.candidate_id,
        formulation=entry.formulation, property=entry.property,
        process_natural_key=campaign.process_natural_key,
        content=content, record_id=record_id,
        extraction_method=extraction_method, extracted_at=extracted_at,
    )


def admit_experimental_result(
    pool: EvidencePool,
    result: ExperimentalResult,
    confidence: float,
    relationship_type: str = "tested_during",
) -> Union[Tuple[Observation, ClaimedRelationship], List[AdmissionError]]:
    """The only function in `materials/` that mutates `EvidencePool`.
    Resolves the process Referent BEFORE admitting anything (raises
    `KeyError` if `result.process_natural_key` is not already in the
    pool -- exactly the same failure mode
    `materials.analysis._resolve_referent` already has, reused here
    rather than reinvented), so a missing process Referent can never
    leave a newly-admitted Observation orphaned with no relationship
    connecting it to anything. `confidence` is required, never
    defaulted, matching `admit_observation`'s own established rule that
    a confidence value must actually be supplied, never silently
    assumed.

    Returns `(Observation, ClaimedRelationship)` on success, or the
    `AdmissionError` list from whichever admission gate rejected the
    input. `EvidencePool` has no delete/rollback primitive (append-only
    by its own design, `evidence/types.py`'s own docstring) -- a
    relationship-admission failure after a successful observation
    admission is not rolled back, but is also not reachable in normal
    use: `from_referent_id` (the result's own formulation) and
    `to_referent_id` (the process Referent) are both already confirmed
    to exist in the pool before the observation is ever admitted."""
    process_referent = _resolve_referent(pool, result.process_natural_key)

    observation = make_observation(
        record_ids=(result.record_id,), extraction_method=result.extraction_method,
        content=result.content, confidence=confidence, extracted_at=result.extracted_at,
    )
    admitted_observation = admit_observation(pool, observation)
    if isinstance(admitted_observation, list):
        return admitted_observation
    pool.put_observation(admitted_observation)

    relationship = make_claimed_relationship(
        from_referent_id=result.formulation.id, to_referent_id=process_referent.id,
        type=relationship_type, observation_id=admitted_observation.id, confidence=confidence,
    )
    admitted_relationship = admit_claimed_relationship(pool, relationship)
    if isinstance(admitted_relationship, list):
        return admitted_relationship
    pool.put_claimed_relationship(admitted_relationship)

    return admitted_observation, admitted_relationship
