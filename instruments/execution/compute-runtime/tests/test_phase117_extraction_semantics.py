"""Phase 117: extraction semantics / measurement-computation boundary.

sec.15 FINAL PROPOSITION, AFTER ATTACK:

    `extraction_method` is A CALLER-DECLARED LABEL THAT IS
    IDENTITY-BEARING AND OTHERWISE ALMOST INERT. It is not provenance,
    not authenticity, not origin, and it does not distinguish
    measurement from computation. Its one behavioural effect raises the
    cost of one declaration and verifies nothing.

sec.1 THE COMPLETE CALL GRAPH
------------------------------
SIX construction sites, and every one PASSES A CALLER-SUPPLIED VALUE
THROUGH -- none derives it, none checks it:

    evidence/types.py:145      make_observation(extraction_method=...)
    materials/results.py:139   make_experimental_result(...)
    materials/results.py:173   from result.extraction_method
    experiment/step.py:172     from dispatched.extraction_method
    scout/extraction.py:90     from self.extraction_method
    scout/pipeline.py:147      from candidate.extraction_method

THREE consumers, and only one changes an outcome:

    evidence/admission.py:73   NON-EMPTINESS ONLY
    retrieval/epistemic.py:43  prefix dispatch -> a status string
    scout/pipeline.py:126      `startswith("model:")` and no confidence
                               -> REJECT (MISSING_MODEL_CONFIDENCE)

Nothing reads it in `materials/`, `experiment/` or `workbench/` beyond
passing it along. It affects no prediction, no candidate generation, no
comparability, no criterion evaluation, no retrieval scoring.

sec.2 IDENTITY-BEARING, BUT COARSER THAN IT LOOKS
--------------------------------------------------
Eleven method strings over one identical Record produce ELEVEN distinct
`Observation.id`s -- and only FOUR epistemic statuses. `Record.id`,
`Document.id` and `Source.id` are unchanged by all of them: the field
lives entirely at the Observation layer.

    model:...            -> inferred
    simulation:...       -> simulated
    human_transcription  -> observed
    EVERYTHING ELSE      -> extracted

So "measurement", "ocr", "manual", "regex", "unknown" AND "llm" all
classify as EXTRACTED -- "pulled from a Document/Record by a mechanical
process". An LLM is a GENERATOR, and an unprefixed `llm` is labelled an
extraction. The taxonomy is a prefix match with a fall-through, and the
fall-through is the strongest reading.

sec.4 THE FIELD DOES NOT IDENTIFY ORIGIN
-----------------------------------------
Of the five candidate meanings, it is the last:

    where the value came from        NO
    how the value was obtained       NO
    how it was serialized            NO
    how it was transformed           NO
    what the caller SAYS extracted it  YES

`measurement -> OCR -> observation` and
`arbitrary computation -> manual entry -> observation` are both a
caller writing a string. The field names the LAST HOP, and only as
declared.

sec.5 THE ONE MECHANISM, STATED PRECISELY
------------------------------------------
Every one of eleven method values admits identically; only the EMPTY
STRING is rejected (NO_EXTRACTION_METHOD). So the field is not an
epistemic firewall.

But it is not wholly inert, and flattening it to "descriptive metadata"
would be wrong. `scout/pipeline.py` enforces a COUPLING: declaring a
model obliges you to declare a confidence rather than let it default to
1.0. That rule RAISES the cost of one declaration and VERIFIES NOTHING
-- it does not check that a model was used, only that a model-claim
arrives with a number attached.

And it is PATH-SPECIFIC: `materials.results` and `experiment.step` never
apply it. Verified. That is the same "honest callers, not gates" pattern
Phase 111 found one layer down.

sec.8 A FABRICATED DECLARATION IS UNDETECTABLE IN PRINCIPLE
------------------------------------------------------------
    actual manual entry  declared "instrument:load_frame" -> extracted
    actual simulation    declared "human_transcription"   -> observed
    actual LLM output    declared "measurement:tensile"   -> extracted

Nothing in the system holds the first column. There is no field for what
ACTUALLY happened, so no mismatch is detectable -- not merely unchecked,
but unrepresentable. `extraction_method="OCR"` means exactly "the caller
says OCR", and nothing stronger.

sec.6 THE FOUR CASES CANNOT BE DISTINGUISHED WITHOUT THE STRING
----------------------------------------------------------------
    A instrument -> measured quantity
    B simulation -> computed quantity
    C fitted model -> estimated quantity
    D human assertion -> stated quantity

Strip `extraction_method` and all four are: a Record with raw content
under a locator in a Document from a Source, plus an Observation with
content and a confidence. IDENTICAL STRUCTURE. The distinction exists
nowhere else -- not on Record, not on Source, not on Document, not in
provenance, not in any operation object.

sec.7 WHERE THE TWO PIPELINES BECOME INDISTINGUISHABLE
--------------------------------------------------------
    physical event -> instrument -> raw data -> parser -> value -> Observation
    simulation     -> solver     -> output   -> parser -> value -> Observation

They become structurally identical AT THE RECORD. `Record(document_id,
locator, raw_content)` is the first object both pipelines can produce,
and from there forward every downstream object is the same type with the
same fields. THAT IS THE ACTUAL BOUNDARY, and it sits one layer BELOW
`extraction_method` -- which is why the field cannot police it.

sec.10 WHAT IS LOST
--------------------
Two Records built from a CSV and from a JSON, normalising to the same
locator and raw content, ARE THE SAME RECORD -- verified. Serialization
format, parser version, instrument settings, and the entire pipeline
above the Record are not represented. The METHOD survives (OCR and
manual give different Observation ids on one Record); everything
UPSTREAM of the Record does not.

That is INTENTIONAL CANONICALISATION at the Record layer and
UNREPRESENTED EXECUTION HISTORY above it -- the same split Phase 116b's
identity-invariance table found: identity tracks the record, never the
execution.

sec.11/sec.12 RELATION TO THE PRIOR RESULTS
---------------------------------------------
World A and World B (Phase 111b) can be made to differ in
`extraction_method` -- and a fabricator simply declares the honest
string. The field adds a distinguishable label, never a distinguishing
FACT. CONTENT IDENTITY CANNOT ESTABLISH AUTHENTICITY, unchanged.

The chain `execution identity -> extraction identity -> observation
identity` is NOT represented: the first term does not exist (Phase 115),
the second is a declared string, and only the third is real. The
converse -- same observation identity from different execution histories
-- is trivially constructible, since nothing upstream of the Record is
recorded.

sec.13 CARRIERS, ALL REJECTED
-------------------------------
  Extraction         would unify a parser invocation with a
                     transcription with a solver read. Cannot
                     distinguish generation from extraction, which is
                     the one distinction it is named for.
  Measurement        would assert an interaction with the world that the
                     architecture cannot witness (Phase 111b).
  Acquisition        `RawDocument`/`DispatchedMeasurement` already fill
                     this shape and are deliberately PRE-IDENTITY;
                     giving acquisition an identity would make an
                     unwitnessed act into a citable object.
  Transformation     would need to be identity-bearing to be useful and
                     would then put parser versions into evidence
                     identity -- re-parsing one document would orphan
                     every prior observation of it.
  ObservationOrigin  origin is precisely what is not representable.
  ProvenanceEvent    Phase 109: four membership semantics, two
                     contradictory.
  MeasurementRecord  fuses the Record layer (where the pipelines merge)
                     with a measurement claim (which they do not share).

sec.15 THREE COUNTEREXAMPLES TO THE SURVIVING PROPOSITION'S STRONGEST
RIVAL -- "extraction_method is provenance":

  1 It names the LAST HOP only. `simulation -> parser -> observation`
    declares the parser or the simulation at the caller's discretion,
    and both are equally admissible.
  2 It is unverifiable and unfalsifiable: nothing holds what actually
    happened, so no declaration can be wrong (sec.8).
  3 Real provenance is CONSTITUTIVE (Phase 109: dropping a
    `derived_from` input changes the id because the object IS a function
    of it). Changing `extraction_method` changes the id WITHOUT changing
    what the observation is a function of -- the content and the cited
    record are untouched. It is identity-bearing without being
    constitutive, which no provenance relation is.

CONSEQUENCE FOR PRODUCTION: none. Zero production changes.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from evidence.admission import admit_observation
from evidence.pool import EvidencePool
from evidence.types import (
    Document,
    Observation,
    Record,
    Source,
    make_document,
    make_observation,
    make_record,
    make_source,
)
from retrieval.epistemic import EXTRACTED, INFERRED, OBSERVED, SIMULATED, classify_epistemic_status
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("evidence", "retrieval", "materials", "experiment", "workbench", "scout")
TIMESTAMP = "2026-01-01T00:00:00Z"

METHODS = ("measurement", "simulation", "ocr", "manual", "regex", "llm", "unknown",
           "model:gpt", "simulation:md_v1", "human_transcription", "regex:kv_v1")


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


@pytest.fixture
def anchored():
    pool = EvidencePool()
    source = make_source(kind="paper", name="J")
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content="90",
                             retrieval_method="m", retrieved_at=TIMESTAMP)
    pool.put_document(document)
    record = make_record(document_id=document.id, locator="l", raw_content="90")
    pool.put_record(record)
    return pool, source, document, record


def _observation(record_id, method, value=90.0):
    return make_observation(
        record_ids=(record_id,), extraction_method=method,
        content={"property": "tensile_strength", "value": value},
        confidence=1.0, extracted_at=TIMESTAMP)


# -- 1. the call graph -------------------------------------------------------------------------------


def test_every_construction_site_passes_a_caller_supplied_value_through():
    sites = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.keyword) and node.arg == "extraction_method":
                    sites.append(f"{path.relative_to(REPO)}")
    assert sorted(set(sites)) == [
        "evidence/types.py", "experiment/step.py", "materials/results.py",
        "scout/extraction.py", "scout/pipeline.py",
        "scout/property_extraction.py",
        "workbench/interaction.py", "workbench/investigation.py",
    ]
    # None derives the value; each forwards what it was given. The two
    # workbench sites joined this list when the `make_experimental_result`
    # default was removed -- they now STATE the claim the constructor
    # used to invent for them.
    #
    # `scout/property_extraction.py` joined it when the chemistry vertical
    # was wired to acquisition. It is the SAME SHAPE as
    # `scout/extraction.py` and admitted on that ground, not waived: it
    # declares its own method as a class constant
    # (`regex:property_v1`, never `model:`) and forwards that constant
    # unchanged. It derives nothing, infers nothing from content, and
    # takes no caller value to override. A second rule-based extractor is
    # not a new kind of site; a site that COMPUTED a method from what it
    # read would be, and this list is what would catch it.


def test_only_three_modules_consume_it_at_all():
    consumers = set()
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if (isinstance(node, ast.Attribute) and node.attr == "extraction_method"
                        and not isinstance(getattr(node, "ctx", None), ast.Store)):
                    consumers.add(str(path.relative_to(REPO)))
    assert consumers == {
        "evidence/admission.py", "retrieval/epistemic.py",
        "scout/pipeline.py", "scout/extraction.py",
        "scout/property_extraction.py",
        "experiment/step.py", "materials/results.py",
    }
    # ...and of those, only admission, epistemic and scout/pipeline READ the
    # value for anything other than forwarding it.


def test_no_prediction_or_comparability_path_reads_it():
    for module_name in ("materials.model_state", "materials.analysis",
                        "materials.decision", "materials.candidates"):
        source = inspect.getsource(__import__(module_name, fromlist=["_"]))
        assert "extraction_method" not in source or "resolve_model_state_key" in source
        # `materials/results.py` forwards it; nothing computes with it.


# -- 2. identity-bearing, and coarser than it looks ---------------------------------------------------


def test_eleven_methods_give_eleven_ids_and_four_statuses(anchored):
    _, _, _, record = anchored
    observations = {m: _observation(record.id, m) for m in METHODS}
    assert len({o.id for o in observations.values()}) == 11
    assert {classify_epistemic_status(o) for o in observations.values()} == {
        EXTRACTED, INFERRED, SIMULATED, OBSERVED}


def test_the_method_changes_nothing_below_the_observation(anchored):
    _, source, document, record = anchored
    before = (source.id, document.id, record.id)
    for method in METHODS:
        _observation(record.id, method)
    assert (source.id, document.id, record.id) == before


def test_an_unprefixed_generator_is_classified_as_an_extraction(anchored):
    """`llm` is a GENERATOR and falls through to EXTRACTED -- "pulled from
    a Document/Record by a mechanical process"."""
    _, _, _, record = anchored
    assert classify_epistemic_status(_observation(record.id, "llm")) == EXTRACTED
    assert classify_epistemic_status(_observation(record.id, "measurement")) == EXTRACTED
    assert classify_epistemic_status(_observation(record.id, "unknown")) == EXTRACTED
    # A generator, an instrument and an admission of ignorance: one status.


# -- 5. the one mechanism ------------------------------------------------------------------------------


@pytest.mark.parametrize("method", METHODS)
def test_every_method_value_admits_identically(anchored, method):
    pool, _, _, record = anchored
    assert admit_observation(pool, _observation(record.id, method)) is not None
    assert not isinstance(admit_observation(pool, _observation(record.id, method)), list)


def test_only_the_empty_string_is_rejected(anchored):
    pool, _, _, record = anchored
    errors = admit_observation(pool, _observation(record.id, ""))
    assert isinstance(errors, list)
    assert {e.code for e in errors} == {"NO_EXTRACTION_METHOD"}


def test_the_model_confidence_coupling_exists_and_is_path_specific():
    """The ONE place the value changes an outcome -- and it applies to the
    scout ingestion path only."""
    import experiment.step
    import materials.results
    import scout.pipeline

    scout_source = inspect.getsource(scout.pipeline)
    assert 'startswith("model:")' in scout_source
    assert "MISSING_MODEL_CONFIDENCE" in scout_source
    for module in (materials.results, experiment.step):
        assert 'startswith("model:")' not in inspect.getsource(module)


def test_the_coupling_verifies_nothing_it_only_raises_a_cost():
    """It does not check that a model was used; it requires that a
    model-claim arrive with a confidence rather than a default 1.0."""
    text = " ".join((REPO / "scout" / "pipeline.py").read_text().split())
    # the message is split across two f-string literals in source
    assert "names a model" in text and "supplied no confidence" in text
    # (the comment wraps, so the `#` marker sits between "never" and "coerced")
    assert "coerced into looking like a verbatim transcription" in text
    admission = " ".join((REPO / "evidence" / "admission.py").read_text().split())
    assert "masquerading as a verbatim" in admission


# -- 6/7. the two pipelines merge at the Record --------------------------------------------------------


def test_stripping_the_method_makes_all_four_cases_structurally_identical():
    """Instrument, simulation, fitted model and human assertion."""
    observation_fields = {f.name for f in dataclasses.fields(Observation)}
    record_fields = {f.name for f in dataclasses.fields(Record)}
    document_fields = {f.name for f in dataclasses.fields(Document)}
    source_fields = {f.name for f in dataclasses.fields(Source)}
    everything = observation_fields | record_fields | document_fields | source_fields
    distinguishing = everything - {"extraction_method"}
    for absent in ("instrument", "simulated", "measured", "generated", "origin", "modality"):
        assert absent not in distinguishing


def test_the_record_is_where_the_pipelines_become_indistinguishable():
    """A CSV path and a JSON path that normalise identically produce the
    SAME Record. Serialization format is represented nowhere."""
    document = make_document(source_id="s", raw_content="x",
                             retrieval_method="m", retrieved_at=TIMESTAMP)
    from_csv = make_record(document_id=document.id, locator="row 1", raw_content="90.0")
    from_json = make_record(document_id=document.id, locator="row 1", raw_content="90.0")
    assert from_csv.id == from_json.id
    assert {f.name for f in dataclasses.fields(Record)} == {
        "id", "document_id", "locator", "raw_content"}


# -- 8. fabricated declarations are unrepresentable ------------------------------------------------------


@pytest.mark.parametrize("declared,status", [
    ("instrument:load_frame", EXTRACTED),      # actually a manual entry
    ("human_transcription", OBSERVED),         # actually a simulation
    ("measurement:tensile_test", EXTRACTED),   # actually LLM output
])
def test_a_false_declaration_classifies_exactly_as_a_true_one(declared, status):
    observation = make_observation(
        record_ids=("r",), extraction_method=declared, content={"v": 90.0},
        confidence=1.0, extracted_at=TIMESTAMP)
    assert classify_epistemic_status(observation) == status


def test_no_field_anywhere_records_what_actually_happened():
    forbidden = {"actual_method", "verified_method", "witnessed", "attested_by",
                 "instrument_id", "acquisition_mode"}
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ClassDef):
                    for stmt in node.body:
                        if (isinstance(stmt, ast.AnnAssign)
                                and isinstance(stmt.target, ast.Name)
                                and stmt.target.id in forbidden):
                            hits.append(f"{path.relative_to(REPO)}: {stmt.target.id}")
    assert hits == [], hits


# -- 15. identity-bearing without being constitutive ------------------------------------------------------


def test_the_method_is_identity_bearing_without_being_constitutive(anchored):
    """COUNTEREXAMPLE 3 to "extraction_method is provenance". A real
    provenance relation is constitutive: dropping a `derived_from` input
    changes the id BECAUSE the object is a function of it. Changing the
    method changes the id while the content and the cited record -- what
    the observation actually is a function of -- are untouched."""
    _, _, _, record = anchored
    a = _observation(record.id, "ocr")
    b = _observation(record.id, "manual")
    assert a.id != b.id
    assert a.content == b.content
    assert a.record_ids == b.record_ids


def test_no_default_asserts_a_claim_any_more():
    """WHEN THIS AUDIT RAN, `DispatchedMeasurement.extraction_method`
    defaulted to "measurement:campaign_execution" -- flagged here as the
    one place the architecture defaulted to a claim rather than to
    unknown, and provisionally called defensible. Phase 120 falsified the
    defence: the only construction of the type anywhere is a scripted
    fixture, so the default never once labelled a measurement. Both that
    default and `make_experimental_result`'s are now REQUIRED."""
    import inspect

    from experiment.interface import DispatchedMeasurement
    from materials.results import make_experimental_result

    field = [f for f in dataclasses.fields(DispatchedMeasurement)
             if f.name == "extraction_method"][0]
    assert field.default is dataclasses.MISSING
    assert inspect.signature(make_experimental_result).parameters[
        "extraction_method"].default is inspect.Parameter.empty


# -- 13/16. nothing was added ------------------------------------------------------------------------------


def test_phase_117_added_no_extraction_machinery():
    forbidden = {
        "Extraction", "Measurement", "Acquisition", "Transformation",
        "ObservationOrigin", "ProvenanceEvent", "MeasurementRecord",
    }
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                # EXACT class names: `ExtractionCandidate` merely starts with one
                if isinstance(node, ast.ClassDef) and node.name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {node.name}")
    assert hits == [], hits


def test_the_existing_acquisition_shape_is_deliberately_pre_identity():
    """`ExtractionCandidate` is scout's acquisition object, parallel to
    `RawDocument` and `DispatchedMeasurement`. All three carry an
    extraction_method and NO id -- acquisition's job is acquisition, not
    identity assignment. That is why an `Acquisition` carrier would be a
    regression: giving an unwitnessed act an identity makes it citable."""
    from scout.interface import ExtractionCandidate
    fields = {f.name for f in dataclasses.fields(ExtractionCandidate)}
    assert "extraction_method" in fields
    assert "id" not in fields


def test_the_vocabulary_is_uncontrolled():
    """No enum, no allowlist, no validation. Any non-empty string."""
    annotations = {f.name: str(f.type) for f in dataclasses.fields(Observation)}
    assert annotations["extraction_method"] == "str"
    source = inspect.getsource(Observation)
    assert "extraction_method" in source
    assert "Enum" not in source and "Literal" not in source
