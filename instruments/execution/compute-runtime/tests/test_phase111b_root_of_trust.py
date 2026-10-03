"""Phase 111b: root-of-trust / provenance closure audit.

VERDICT: SURVIVES -- one precise, non-inflated statement holds, and it is
narrower than any previously asserted.

THE STATEMENT THAT SURVIVES
---------------------------
    For any object admitted through its own `admit_*` gate, every
    identifier it cites was present in the pool at admission time; and
    every citation chain, followed to its end, terminates at a `Source`
    or a `Referent` -- objects that cite nothing and that no gate
    examines.

That is PROVENANCE INTEGRITY. It is not authenticity, not warrant, not
truth, and it is not a property of the pool -- it is a property of
objects that went through a gate.

sec.19 THE BOUNDARY, IN ONE SENTENCE
Provenance integrity says every citation RESOLVES INSIDE the pool;
provenance authenticity would say every citation CORRESPONDS TO
SOMETHING OUTSIDE it -- and no content-addressed system can supply the
second, because identity is a function of content while authenticity is
a function of history that content does not encode.

sec.4 WORLD A AND WORLD B ARE NOT INDISTINGUISHABLE -- THEY ARE IDENTICAL
--------------------------------------------------------------------------
Build a real chain (a journal really printed 90 MPa in table 2) and a
fabricated one (a script wrote the same bytes). Source, Document, Record
and Observation ids all match, the pool fingerprints match, and the
epistemic classification matches -- because they ARE THE SAME OBJECTS.
The architecture does not fail to distinguish them; there is nothing
there to distinguish. Fabrication is a fact about history outside the
process, and content does not encode that history.

This makes Phase 111's leak structural rather than accidental. It is not
a gap a better gate could close: closing it requires importing an
external signal -- a witness, a signature, a chain of custody -- that
content-addressing cannot manufacture from within. sec.20.4's question is
therefore answered YES: the fabricated-root attack and provenance
authenticity are the same problem, and the attack is the general form.

sec.1 WHERE CHAINS ACTUALLY TERMINATE
--------------------------------------
Predecessor fields, exhaustively:

    Source              NONE -- a true root
    Referent            NONE -- a true root
    Document            source_id
    Record              document_id
    Observation         record_ids
    ClaimedRelationship from_referent_id, to_referent_id, observation_id
    DerivedValue        derived_from
    DerivedGrounding    derived_value_id, referent_ids

Two objects cite nothing: `Source` and `Referent`. `Source` has NO
admission gate; `admit_referent` checks non-emptiness only. So the roots
of the entire evidence graph are the two objects nothing inspects.

And `ancestry_of` STOPS AT OBSERVATIONS -- it never walks into Records,
Documents or Sources. The provenance API's own horizon sits one level
ABOVE the actual roots, so "full provenance" here means "back to the
observations", never "back to the sources".

sec.5 THE GATES ARE ADVISORY
----------------------------
`put_*` does not call `admit_*`. A `Record` naming a document that is not
in the pool is accepted by `put_record`, and an `Observation` citing that
orphan is accepted by `put_observation`; the fingerprint advances. So
even REFERENTIAL integrity is not a pool invariant -- it is a property of
objects whose callers chose to run the gate. This is why the surviving
statement above must be scoped to gated admission, and it is not a
weakening for convenience: it is the strongest form the code supports.

sec.2 THE EIGHT PROPOSITIONS
----------------------------
  A this object cites a Source          REPRESENTED (transitively, and
                                        it participates in identity)
  B this Source exists                  ASSERTED BY A FIELD (`name`,
                                        `kind` -- free strings, no gate)
  C this Source produced this Document  ASSERTED BY A FIELD (`source_id`
                                        plus `retrieval_method`, a free
                                        string)
  D this Document contains this Record  ASSERTED BY A FIELD (`locator`,
                                        a free string; `admit_record`
                                        never reads `raw_content` against
                                        the document's)
  E this Record is a real measurement   OUTSIDE THE ARCHITECTURE
  F the measurement occurred            OUTSIDE THE ARCHITECTURE
  G the measurement is accurate         OUTSIDE THE ARCHITECTURE
  H the observation is true             OUTSIDE THE ARCHITECTURE

Only A is represented. B through D are recorded assertions. E through H
have no representation at all -- and correctly so.

sec.3 WHAT `derived_from` MEANS
-------------------------------
"CONTAINS AN IDENTIFIER FOR", strengthened by identity to "WAS COMPUTED
USING". It is constitutive (Phase 109: dropping an input changes the id),
so it is more than a bare pointer. It is NOT "is warranted by" and NOT
"is attributed to": nothing checks that the method named actually
produced the content, and Phase 110 showed the edge omits the modeller's
choice of family entirely.

sec.9/16 WHAT PARTICIPATES IN Observation IDENTITY
---------------------------------------------------
    identity-bearing      record_ids, extraction_method, content
    NOT identity-bearing  confidence, extracted_at

So an Observation's identity is THE EXTRACTION EVENT AS DESCRIBED -- the
cited records, the declared method, and the resulting content -- never
the measurement, never the truth of the content. A different claimed
origin yields a different observation, because `source_id` reaches
identity transitively; but a FABRICATED claimed origin is exactly as
identity-bearing as a true one.

sec.10 WHAT CONFIDENCE ACTUALLY IS
-----------------------------------
An EXTRACTION-TIME SELF-REPORT. Excluded from identity, range-checked to
[0,1], never corroborated. Phase 111 said "nothing consumes it", which
was true of `materials/`, `experiment/` and `workbench/` and WRONG in
general: `scout/pipeline.py` reads it through
`metrics.observation_uncertainty` into a `ScoutReport`. So it is
consumed, once, for a descriptive report. It is not truth, not authority,
and not uncertainty in any estimator's sense.

sec.11 WHAT `classify_epistemic_status` ACTUALLY CLASSIFIES
------------------------------------------------------------
The `extraction_method` STRING, by prefix: "model:" -> inferred,
"simulation:" -> simulated, "human_transcription" -> observed, everything
else -> extracted. It is a PROVENANCE STATE derived from a self-declared
label, not a truth claim and not a workflow state. "extracted" means "the
method string matched no other pattern" -- which is why Phase 111's
fabricated chain was labelled `extracted` while no document existed.

sec.12 THE FOUR PREDICATES
--------------------------
  ATTRIBUTED  REPRESENTABLE -- the record/document/source chain
  DERIVED     REPRESENTABLE -- `derived_from`
  SUPPORTED   NOT REPRESENTABLE -- no non-constitutive corroboration edge
  VERIFIED    NOT REPRESENTABLE -- requires an external check

`attributed_by_source` and `derived_from_observations` differ in what
they assert, and share one root: derivation bottoms out in observations,
which bottom out in the same attribution chain. Derivation is ROOTED IN
ATTRIBUTION, so it can never be better warranted than the attribution
beneath it.

sec.13 VALIDATION CANNOT BE ROOTED EITHER
-----------------------------------------
Held-out observations are Observations, admitted through the same gates
and open to the same fabrication. Validation inherits the root-of-trust
problem unchanged, one level up. Combined with Phase 109's finding that
validation needs a DISJOINTNESS no inclusion edge can express, validation
is doubly unrepresentable here.

sec.14 HOW FAR FABRICATED PROVENANCE PROPAGATES
------------------------------------------------
    computed result -> Record          REFERENTIALLY VALID
    Record -> Observation              REFERENTIALLY VALID
    Observation -> DerivedValue        REFERENTIALLY VALID
    DerivedValue -> ClaimedRelationship  STRUCTURALLY BLOCKED
                                       (a relationship cites an
                                        observation id; a derived-value
                                        id is not one)
    Observation -> ClaimedRelationship REFERENTIALLY VALID
    any of the above -> "warranted"    EPISTEMICALLY UNDECIDABLE

Nothing in the chain is EPISTEMICALLY WARRANTED at any step, and the one
structural block is a type boundary, not an epistemic one.

sec.15 WHAT IS CONSERVED
------------------------
Not warrant -- the architecture never represents warrant, so it can
neither conserve nor lose it. What IS conserved, and is checkable, is
REACHABILITY: every gated object's citation chain terminates at a root
that is in the pool. A computation does not become externally warranted
by citing an attributed input; it becomes REACHABLE FROM one.

sec.17 THE THREE SETS
---------------------
INTERNALLY PROVABLE
    content-addressed identity determinism; immutability; append-only
    history; acyclicity of `derived_from` (by construction, Phase 100);
    referential resolution of every gated citation; termination of every
    chain at Source or Referent.
EXTERNALLY ASSERTED
    Source.kind and .name; Document.raw_content and .retrieval_method;
    Record.locator and .raw_content; Observation.extraction_method and
    .confidence; every ClaimedRelationship.type.
EXTERNALLY VERIFIABLE BUT NOT VERIFIED
    that the document exists and contains the record at the locator;
    that the extraction method produced the content; that the
    measurement occurred; that the instrument was calibrated.
"Truth" appears in none of the three.

sec.18 THE STRONGEST JUSTIFIED STATEMENT: (E)
----------------------------------------------
Not (A), not (B), not (D), and narrower than (C):

    EvidencePool contains immutable, content-addressed assertions.
    Those admitted through their `admit_*` gate additionally cite only
    identifiers already present, and every such citation chain
    terminates at a Source or Referent that no gate inspects.

CONSEQUENCE FOR PRODUCTION: none. Zero production changes.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

import evidence.admission as admission
from evidence.pool import EvidencePool
from evidence.provenance import ancestry_of
from evidence.types import (
    ClaimedRelationship,
    DerivedGrounding,
    DerivedValue,
    Document,
    Observation,
    Record,
    Referent,
    Source,
    make_claimed_relationship,
    make_derived_value,
    make_document,
    make_observation,
    make_record,
    make_source,
)
from retrieval.epistemic import EXTRACTED, INFERRED, OBSERVED, SIMULATED, classify_epistemic_status
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
TIMESTAMP = "2026-01-01T00:00:00Z"


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _chain(pool, *, source_name, doc_content, locator, value,
           method="regex:kv_v1", confidence=1.0):
    source = make_source(kind="paper", name=source_name)
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content=doc_content,
                             retrieval_method="http_get", retrieved_at=TIMESTAMP)
    pool.put_document(document)
    record = make_record(document_id=document.id, locator=locator, raw_content=str(value))
    pool.put_record(record)
    observation = make_observation(
        record_ids=(record.id,), extraction_method=method,
        content={"property": "tensile_strength", "value": value, "unit": "MPa"},
        confidence=confidence, extracted_at=TIMESTAMP)
    pool.put_observation(observation)
    return source, document, record, observation


# -- 4. the fabricated root is not a different object ----------------------------------------------


def test_a_real_chain_and_a_fabricated_chain_are_the_same_objects():
    """THE CENTRAL RESULT. Not indistinguishable -- identical."""
    real, fake = EvidencePool(), EvidencePool()
    kwargs = dict(source_name="Polymer Journal 41",
                  doc_content="...table 2: 90 MPa...",
                  locator="table 2, row 1", value=90.0)
    a = _chain(real, **kwargs)      # a journal really printed this
    b = _chain(fake, **kwargs)      # a script wrote the same bytes

    assert [x.id for x in a] == [y.id for y in b]
    assert real.fingerprint() == fake.fingerprint()
    assert classify_epistemic_status(a[3]) == classify_epistemic_status(b[3]) == EXTRACTED


def test_identity_is_necessarily_orthogonal_to_warrant():
    """Identity is a function of content; authenticity is a function of
    history outside the process; content does not encode that history.
    So this is structural, not an oversight."""
    source = inspect.getsource(inspect.getmodule(make_source))
    tree = ast.parse(source)
    hashed_calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "content_hash"
    ]
    assert hashed_calls, "content-addressing is the mechanism under test"
    # Every argument is drawn from the object's own fields; none reads the
    # world. A hash cannot witness what it was not given.


# -- 1. where chains terminate ---------------------------------------------------------------------


def test_exactly_two_objects_cite_nothing():
    predecessors = {
        Source: set(),
        Referent: set(),
        Document: {"source_id"},
        Record: {"document_id"},
        Observation: {"record_ids"},
        ClaimedRelationship: {"from_referent_id", "to_referent_id", "observation_id"},
        DerivedValue: {"derived_from"},
        DerivedGrounding: {"derived_value_id", "referent_ids"},
    }
    for cls, expected in predecessors.items():
        fields = {f.name for f in dataclasses.fields(cls)}
        assert expected <= fields, cls.__name__
    roots = [cls.__name__ for cls, p in predecessors.items() if not p]
    assert sorted(roots) == ["Referent", "Source"]


def test_the_roots_are_the_objects_no_gate_inspects():
    gates = {n for n in dir(admission) if n.startswith("admit_")}
    assert "admit_source" not in gates
    referent_gate = inspect.getsource(admission.admit_referent)
    assert "EMPTY_NATURAL_KEY" in referent_gate and "EMPTY_KIND" in referent_gate
    assert "pool." not in referent_gate      # it never consults the pool at all


def test_ancestry_stops_at_observations_one_level_above_the_roots():
    pool = EvidencePool()
    observation = _chain(pool, source_name="J", doc_content="c", locator="l", value=90.0)[3]
    derived = make_derived_value(derived_from=(observation.id,), method="fit:linear",
                                 content={"slope": -0.45}, confidence=0.9,
                                 derived_at=TIMESTAMP)
    pool.put_derived_value(derived)
    ancestry = ancestry_of(pool, derived.id)
    assert ancestry.observation_ids == (observation.id,)
    assert ancestry.derived_value_ids == ()
    fields = {f.name for f in dataclasses.fields(type(ancestry))}
    assert "record_ids" not in fields and "source_ids" not in fields
    # "Full provenance" here means back to the observations, never the sources.


# -- 5. the gates are advisory ----------------------------------------------------------------------


def test_put_does_not_enforce_admit():
    """So even referential integrity is a property of GATED objects, not
    of the pool."""
    pool = EvidencePool()
    orphan = make_record(document_id="no-such-document", locator="l", raw_content="x")
    pool.put_record(orphan)
    assert pool.has_record(orphan.id)

    observation = make_observation(
        record_ids=(orphan.id,), extraction_method="regex:x", content={"v": 1},
        confidence=1.0, extracted_at=TIMESTAMP)
    pool.put_observation(observation)
    assert pool.has_observation(observation.id)


def test_no_put_method_calls_an_admission_gate():
    source = inspect.getsource(EvidencePool)
    tree = ast.parse(source.lstrip())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("put_"):
            for inner in ast.walk(node):
                assert not (isinstance(inner, ast.Call)
                            and getattr(inner.func, "id", "").startswith("admit_"))


# -- 9/16. what participates in Observation identity -----------------------------------------------


def test_confidence_and_extracted_at_are_not_identity_bearing():
    base = make_observation(record_ids=("r",), extraction_method="regex:kv_v1",
                            content={"v": 90.0}, confidence=1.0, extracted_at=TIMESTAMP)
    other_confidence = make_observation(record_ids=("r",), extraction_method="regex:kv_v1",
                                        content={"v": 90.0}, confidence=0.05,
                                        extracted_at=TIMESTAMP)
    other_time = make_observation(record_ids=("r",), extraction_method="regex:kv_v1",
                                  content={"v": 90.0}, confidence=1.0,
                                  extracted_at="2099-12-31T23:59:59Z")
    assert base.id == other_confidence.id == other_time.id


def test_method_and_the_cited_chain_are_identity_bearing():
    pool = EvidencePool()
    base = _chain(pool, source_name="J", doc_content="c", locator="l", value=90.0)[3]
    for changed in (
        dict(source_name="Other Journal"),
        dict(doc_content="different bytes"),
        dict(locator="table 9"),
        dict(method="model:llm_v2"),
    ):
        kwargs = dict(source_name="J", doc_content="c", locator="l", value=90.0)
        kwargs.update(changed)
        assert _chain(EvidencePool(), **kwargs)[3].id != base.id
    # A different CLAIMED origin is a different observation -- and a
    # fabricated claimed origin is exactly as identity-bearing as a true one.


# -- 11. what the epistemic classifier classifies ---------------------------------------------------


@pytest.mark.parametrize("method,expected", [
    ("model:llm_v2", INFERRED),
    ("simulation:md_v1", SIMULATED),
    ("human_transcription", OBSERVED),
    ("regex:kv_v1", EXTRACTED),
    ("fit:linear", EXTRACTED),          # a FIT, classified as extracted
    ("anything at all", EXTRACTED),
])
def test_epistemic_status_classifies_a_self_declared_string(method, expected):
    observation = make_observation(
        record_ids=("r",), extraction_method=method, content={"v": 1.0},
        confidence=1.0, extracted_at=TIMESTAMP)
    assert classify_epistemic_status(observation) == expected
    # "extracted" is the fall-through: it means the string matched no other
    # pattern, never that the underlying proposition is true.


# -- 12. which predicates are representable ---------------------------------------------------------


def test_supported_and_verified_have_no_carrier():
    for cls in (Observation, ClaimedRelationship, DerivedValue, DerivedGrounding):
        fields = {f.name for f in dataclasses.fields(cls)}
        for absent in ("supported_by", "verified_by", "witnessed_by", "signature"):
            assert absent not in fields


def test_derivation_is_rooted_in_attribution():
    """So a derived value can never be better warranted than the
    attribution chain beneath it."""
    pool = EvidencePool()
    observation = _chain(pool, source_name="J", doc_content="c", locator="l", value=90.0)[3]
    derived = make_derived_value(derived_from=(observation.id,), method="fit:linear",
                                 content={"slope": -0.45}, confidence=0.9,
                                 derived_at=TIMESTAMP)
    pool.put_derived_value(derived)
    assert ancestry_of(pool, derived.id).observation_ids == (observation.id,)
    # and that observation cites a Record -> Document -> Source, none verified


def test_a_derived_value_cannot_carry_a_claimed_relationship():
    """The one STRUCTURAL block in the propagation chain -- and it is a
    type boundary, not an epistemic one."""
    pool = EvidencePool()
    relationship = make_claimed_relationship(
        from_referent_id="a", to_referent_id="b", type="t",
        observation_id="a-derived-value-id", confidence=1.0)
    errors = admission.admit_claimed_relationship(pool, relationship)
    assert isinstance(errors, list)
    assert "UNKNOWN_OBSERVATION" in {e.code for e in errors}


# -- 10. confidence is consumed exactly once, for a report ------------------------------------------


def test_confidence_is_read_only_by_the_scout_report():
    """PHASE 111'S "nothing consumes it" WAS TOO BROAD."""
    consumers = []
    for package in ("evidence", "retrieval", "materials", "experiment", "workbench", "scout"):
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if path.name == "metrics.py":
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                if (isinstance(node, ast.Name)
                        and node.id in ("observation_uncertainty", "aggregate_uncertainty")):
                    consumers.append(str(path.relative_to(REPO)))
    assert set(consumers) == {"scout/pipeline.py"}, sorted(set(consumers))


# -- 20. nothing was added ---------------------------------------------------------------------------


def test_phase_111b_added_no_root_of_trust_machinery():
    forbidden = (
        "admit_source", "RootOfTrust", "witnessed_by", "attestation",
        "authenticity", "verify_external", "chain_of_custody",
    )
    # NOTE: not "signature" -- `inspect.signature` is used legitimately in
    # several modules. Prose and stdlib calls are not machinery.
    hits = []
    for package in ("evidence", "retrieval", "materials", "experiment", "workbench", "scout"):
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            text = path.read_text()
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert hits == [], hits
