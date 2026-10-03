"""Phase 111: adversarial falsification of the evidence-admission firewall.

VERDICT: FALSIFIED.

The invariant asserted at the end of Phase 110 --

    NO ARROW CROSSES UPWARD INTO EVIDENCE ... and that holds
    STRUCTURALLY, not by convention

-- is FALSE as stated. It was inferred from the fact that a `Prediction`
cannot BE an `Observation`, and generalised into a claim about all
computational-to-evidence paths. The generalisation does not hold.

THE COUNTEREXAMPLE (sec.15), constructed with existing primitives only,
no private access, no gate bypassed:

    slope = <an arbitrary Python function of three numbers>
    make_source(kind="lab_notebook", name="Analysis pipeline")   put_source
    make_document(raw_content=f"slope = {slope}",
                  retrieval_method="manual_entry")               admit_document  OK
    make_record(locator="table 1, row 3", raw_content=str(slope)) admit_record   OK
    make_observation(record_ids=(rec.id,),
                     extraction_method="regex:kv_v1", ...)       admit_observation OK
    make_claimed_relationship(type="tensile_strength_decreases_with",
                              observation_id=obs.id)             admit_claimed_relationship OK

Every gate accepted. `classify_epistemic_status` returns EXTRACTED --
"pulled from a Document/Record by a mechanical process". No such document
existed. The locator names a table that was never printed. The pool
fingerprint advanced.

WHY THE FIREWALL IS REFERENTIAL, NOT EPISTEMIC
-----------------------------------------------
Every AdmissionError code in `evidence/admission.py`, exhaustively:

    admit_document              EMPTY_CONTENT, UNKNOWN_SOURCE
    admit_record                EMPTY_CONTENT, UNKNOWN_DOCUMENT
    admit_observation           NO_RECORD_IDS, NO_EXTRACTION_METHOD,
                                EMPTY_CONTENT, UNKNOWN_RECORD
    admit_referent              EMPTY_NATURAL_KEY, EMPTY_KIND
    admit_claimed_relationship  EMPTY_TYPE, UNKNOWN_REFERENT, UNKNOWN_OBSERVATION
    admit_derived_value         NO_DERIVED_FROM, NO_METHOD, EMPTY_CONTENT, UNKNOWN_INPUT
    admit_derived_grounding     UNKNOWN_DERIVED_VALUE, NO_REFERENT_IDS, UNKNOWN_REFERENT

Sixteen codes. Every one is NON-EMPTINESS or REFERENTIAL INTEGRITY. Not
one asks whether anything outside the process warrants the object. And
`Source` -- the ROOT of the whole chain, the only object that names where
evidence came from -- has NO ADMISSION GATE AT ALL. There is no
`admit_source`. `kind` and `name` are free strings written by the caller.

WHAT PHASE 110 ACTUALLY OBSERVED, CORRECTLY
-------------------------------------------
`admit_observation` rejects a fitted coefficient carrying NO record ids,
and `admit_claimed_relationship` rejects a relationship citing no
observation. Both true, both verified again here. But those gates enforce
that a CITATION EXISTS -- never that the citation is truthful. Phase 110
read "a citation is required" as "an external warrant is required". Those
are different claims, and only the first is implemented.

The honest restatement, which this phase's locks pin down:

    Every object entering the pool must CITE a predecessor that is
    already in the pool. No gate verifies that any predecessor
    corresponds to anything outside the process.

sec.16 THE EXTERNAL-WARRANT TEST, APPLIED
-----------------------------------------
For the admitted counterexample, the question "what fact exists outside
the computation that warrants this being evidence?" has the answer NONE.
The valid answers (a measurement occurred, a document contains the
statement, an external source supplied the assertion, an experiment
produced the result) are all absent. The invalid answers are exactly what
carried it through: a function returned it, and another object cited it.
By this phase's own stated rule, that is FALSIFIED.

sec.13 THE TRUE BOUNDARY IS NARROWER THAN "EVIDENCE vs NON-EVIDENCE"
--------------------------------------------------------------------
The architecture distinguishes CITED from UNCITED. It does NOT
distinguish externally attributable from internally generated. The two
were conflated because in every path production actually exercises --
`scout.pipeline.run_scout`, `experiment.step.run_experiment_step`,
`materials.results.admit_experimental_result`, the workbench `observe`
functions -- the citation happens to be honest. That is a property of
those six callers, not of the gates.

sec.14 THE ADMISSION GRAPH (traced from the AST, not from names)
----------------------------------------------------------------
Six functions reach `put_*`/`admit_*`:

    scout/pipeline.py       run_scout                    (external documents)
    experiment/step.py      run_experiment_step          (a real measurement)
    materials/results.py    admit_experimental_result    (a real result)
    workbench/interaction.py observe                     (an operator's entry)
    workbench/investigation.py _observe                  (an operator's entry)
    workbench/interaction.py bootstrap_*_scenario        (a session Source/Document)

All six are honest. NONE of them is on the counterexample's path: the
attack calls the `evidence/` primitives directly, and they are public,
documented, and ungated at the root.

sec.8 CONFIDENCE IS A SELF-REPORT
---------------------------------
`confidence=0.05` and `confidence=1.0` produce THE SAME `Observation.id`
and both admit. Confidence is excluded from identity and range-checked
only. A caller may assert 1.0 for anything; nothing corroborates it.
Phase 105 found confidence reaches no decision above `evidence/`, which
is what keeps this harmless today -- it is contained, not verified.

sec.5/9 PREDICTION AND RANKING
------------------------------
Neither `Prediction` nor `PredictionAssessment` nor any ranking object
carries `record_ids`, so none can BE an Observation and no automatic path
exists. STRUCTURALLY BLOCKED as objects. But a caller may read
`prediction.predicted_value`, write it into a Record's `raw_content`, and
admit it -- the same manual route as the counterexample. The object
boundary holds; the value boundary does not.

sec.11 IDENTITY CONFERS NOTHING -- THIS ONE HOLDS
-------------------------------------------------
A `content_hash` of a computed object, minted as a `Referent`, is in the
pool and is still not evidence: a Referent is what a claim is ABOUT.
Immutable identity does not confer evidential status. It confers no
protection either.

sec.18 CLASSIFICATION OF EVERY PATH FOUND

  scout.pipeline external document -> Observation   ATTRIBUTED EXTERNAL STATEMENT
  experiment.step measurement -> Observation        ATTRIBUTED EXTERNAL STATEMENT
  admit_experimental_result -> Observation          ATTRIBUTED EXTERNAL STATEMENT
  workbench observe (operator entry) -> Observation ATTRIBUTED EXTERNAL STATEMENT
  Prediction object -> Observation                  STRUCTURALLY BLOCKED
  PredictionAssessment -> Observation               STRUCTURALLY BLOCKED
  ranking / utility object -> Observation           STRUCTURALLY BLOCKED
  DerivedValue -> ClaimedRelationship               STRUCTURALLY BLOCKED
        (a relationship cites an Observation id, and a DerivedValue id
         is not one; verified below)
  content_hash -> Referent -> pool                  REPRESENTATION ONLY
  computed value -> Record.raw_content -> Observation   LEAK DETECTED
  computed value -> Document.raw_content -> ...     LEAK DETECTED
  self-asserted confidence on any Observation       LEAK DETECTED

sec.17 THE CENTRAL INVARIANT, RE-STATED HONESTLY
------------------------------------------------
FALSIFIED as written. A computational derivation CAN become evidence
through composition with existing primitives, because the composition
that launders it -- writing the computed number into a Document and a
Record the caller also mints -- uses nothing but public constructors and
passes every gate.

What is TRUE, and is what the locks below protect:

  (a) No claim-shaped OBJECT (Prediction, assessment, ranking,
      DerivedValue) can enter the pool as itself.
  (b) Every admitted object cites a predecessor already in the pool.
  (c) Identity, confidence, ranking and derivation confer no evidential
      status on their own.
  (d) The six production admission paths are all externally warranted.

(a)-(d) are real and worth keeping. They are not the invariant Phase 110
claimed, and (d) is a fact about callers, not about gates.

CONSEQUENCE FOR PRODUCTION: none. Zero production changes in this phase.
This audit reports a gap; it does not repair one. Whether an
external-warrant check SHOULD exist is a separate question this phase was
not asked, and the honest note is that such a check may not be
implementable at all -- "a document really says this" is not decidable
from inside the process.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

import evidence.admission as admission
from evidence.admission import (
    admit_claimed_relationship,
    admit_document,
    admit_observation,
    admit_record,
)
from evidence.identity import content_hash
from evidence.pool import EvidencePool
from evidence.types import (
    make_claimed_relationship,
    make_document,
    make_observation,
    make_record,
    make_referent,
    make_source,
)
from materials.assessment import PredictionAssessment
from materials.model_state import Prediction
from retrieval.epistemic import EXTRACTED, classify_epistemic_status
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
PACKAGES = ("evidence", "retrieval", "materials", "experiment", "workbench", "scout")

TIMESTAMP = "2026-01-01T00:00:00Z"


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _arbitrary_computation() -> float:
    """No measurement occurred. No document says this. A function
    returned it."""
    xs = (25.0, 40.0, 100.0)
    ys = (90.0, 95.0, 60.0)
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)


# -- 15/16. THE COUNTEREXAMPLE ---------------------------------------------------------------------


def test_an_arbitrary_computation_reaches_the_pool_through_every_gate():
    """THE FALSIFICATION. Existing primitives only; nothing bypassed."""
    pool = EvidencePool()
    value = _arbitrary_computation()

    source = make_source(kind="lab_notebook", name="Analysis pipeline")
    pool.put_source(source)                       # no admit_source exists

    document = make_document(
        source_id=source.id, raw_content=f"slope = {value}",
        retrieval_method="manual_entry", retrieved_at=TIMESTAMP)
    assert admit_document(pool, document) is document
    pool.put_document(document)

    record = make_record(document_id=document.id, locator="table 1, row 3",
                         raw_content=str(value))
    assert admit_record(pool, record) is record
    pool.put_record(record)

    observation = make_observation(
        record_ids=(record.id,), extraction_method="regex:kv_v1",
        content={"property": "tensile_strength_slope", "value": value,
                 "unit": "MPa_per_C"},
        confidence=1.0, extracted_at=TIMESTAMP)
    assert admit_observation(pool, observation) is observation
    pool.put_observation(observation)

    material = make_referent(natural_key="formulation-a", kind="material")
    concept = make_referent(natural_key="temperature", kind="concept")
    pool.put_referent(material)
    pool.put_referent(concept)
    relationship = make_claimed_relationship(
        from_referent_id=material.id, to_referent_id=concept.id,
        type="tensile_strength_decreases_with", observation_id=observation.id,
        confidence=1.0)
    assert admit_claimed_relationship(pool, relationship) is relationship
    pool.put_claimed_relationship(relationship)

    assert pool.has_observation(observation.id)
    # ...and it is classified as pulled from a document by a mechanical process
    assert classify_epistemic_status(observation) == EXTRACTED


def test_the_root_of_the_evidence_chain_has_no_admission_gate():
    """`Source` names where evidence came from, and nothing checks it."""
    gates = {n for n in dir(admission) if n.startswith("admit_")}
    assert "admit_source" not in gates
    assert gates == {
        "admit_document", "admit_record", "admit_observation", "admit_referent",
        "admit_claimed_relationship", "admit_derived_value", "admit_derived_grounding",
    }


def test_every_admission_check_is_emptiness_or_referential_integrity():
    """Sixteen codes; not one asks about anything outside the process."""
    codes = {}
    tree = ast.parse(inspect.getsource(admission))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("admit_"):
            found = []
            for inner in ast.walk(node):
                if (isinstance(inner, ast.Call)
                        and getattr(inner.func, "id", None) == "AdmissionError"
                        and len(inner.args) > 1):
                    found.append(inner.args[1].value)
            codes[node.name] = sorted(set(found))

    assert codes == {
        "admit_document": ["EMPTY_CONTENT", "UNKNOWN_SOURCE"],
        "admit_record": ["EMPTY_CONTENT", "UNKNOWN_DOCUMENT"],
        "admit_observation": ["EMPTY_CONTENT", "NO_EXTRACTION_METHOD",
                              "NO_RECORD_IDS", "UNKNOWN_RECORD"],
        "admit_referent": ["EMPTY_KIND", "EMPTY_NATURAL_KEY"],
        "admit_claimed_relationship": ["EMPTY_TYPE", "UNKNOWN_OBSERVATION", "UNKNOWN_REFERENT"],
        "admit_derived_value": ["EMPTY_CONTENT", "NO_DERIVED_FROM", "NO_METHOD", "UNKNOWN_INPUT"],
        "admit_derived_grounding": ["NO_REFERENT_IDS", "UNKNOWN_DERIVED_VALUE", "UNKNOWN_REFERENT"],
    }
    everything = {c for cs in codes.values() for c in cs}
    for code in everything:
        assert code.startswith(("EMPTY_", "NO_", "UNKNOWN_")), code


def test_a_citation_being_required_is_not_an_external_warrant():
    """PHASE 110'S READING, CORRECTED. Both gates fire on a MISSING
    citation, and neither fires on a FABRICATED one."""
    pool = EvidencePool()
    uncited = make_observation(
        record_ids=(), extraction_method="fit:linear", content={"slope": -0.45},
        confidence=0.9, extracted_at=TIMESTAMP)
    errors = admit_observation(pool, uncited)
    assert isinstance(errors, list) and {e.code for e in errors} == {"NO_RECORD_IDS"}
    # The very same content, once a Record is minted for it, admits cleanly --
    # proven by the counterexample above. The gate counts citations.


# -- 14. the admission graph -----------------------------------------------------------------------


def test_only_six_production_functions_reach_the_pool():
    reaching = set()
    for package in PACKAGES:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text())
            for function in [n for n in ast.walk(tree)
                             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                for inner in ast.walk(function):
                    hit = (isinstance(inner, ast.Attribute) and inner.attr.startswith("put_")) or (
                        isinstance(inner, ast.Call)
                        and getattr(inner.func, "id", "").startswith("admit_"))
                    if hit:
                        reaching.add(function.name)
                        break
    assert reaching == {
        "run_scout", "run_experiment_step", "admit_experimental_result",
        "observe", "_observe", "bootstrap_default_scenario", "bootstrap_research_scenario",
    }, sorted(reaching)
    # All externally warranted -- a property of these callers, not of the gates.


# -- 5/9. object boundary holds; value boundary does not -------------------------------------------


@pytest.mark.parametrize("cls", [Prediction, PredictionAssessment])
def test_no_claim_shaped_object_can_be_an_observation(cls):
    fields = {f.name for f in dataclasses.fields(cls)}
    assert "record_ids" not in fields
    assert "extraction_method" not in fields


def test_a_predicted_value_can_still_be_written_into_a_record_by_hand():
    """The object boundary holds. The VALUE boundary does not."""
    pool = EvidencePool()
    source = make_source(kind="lab_notebook", name="s")
    pool.put_source(source)
    document = make_document(source_id=source.id, raw_content="x",
                             retrieval_method="m", retrieved_at=TIMESTAMP)
    pool.put_document(document)
    predicted_value = 91.0            # as if read off a Prediction
    record = make_record(document_id=document.id, locator="l",
                         raw_content=str(predicted_value))
    assert admit_record(pool, record) is record
    # Nothing distinguishes this Record from one transcribing a measurement.


# -- 8. confidence is a self-report -----------------------------------------------------------------


def test_confidence_is_excluded_from_identity_and_never_corroborated():
    low = make_observation(record_ids=("r",), extraction_method="model:guesser",
                           content={"value": 1.0}, confidence=0.05, extracted_at=TIMESTAMP)
    high = make_observation(record_ids=("r",), extraction_method="model:guesser",
                            content={"value": 1.0}, confidence=1.0, extracted_at=TIMESTAMP)
    assert low.id == high.id
    # Range-checked only; a caller may assert 1.0 for anything.


# -- 11. identity confers nothing -- this one HOLDS -------------------------------------------------


def test_immutable_identity_does_not_make_a_computed_object_evidence():
    pool = EvidencePool()
    computed = content_hash({"fitted_slope": _arbitrary_computation()})
    referent = make_referent(natural_key=computed, kind="concept")
    pool.put_referent(referent)
    assert pool.has_referent(referent.id)
    assert not pool.has_observation(referent.id)
    # A Referent is what a claim is ABOUT. Identity confers no evidential
    # status -- and no protection either.


def test_a_derived_value_id_is_not_an_observation_id():
    """So a DerivedValue cannot be laundered through a relationship."""
    pool = EvidencePool()
    relationship = make_claimed_relationship(
        from_referent_id="a", to_referent_id="b", type="t",
        observation_id="some-derived-value-id", confidence=1.0)
    errors = admit_claimed_relationship(pool, relationship)
    assert isinstance(errors, list)
    assert "UNKNOWN_OBSERVATION" in {e.code for e in errors}


# -- 18. nothing was added ---------------------------------------------------------------------------


def test_phase_111_added_no_warrant_machinery():
    forbidden = (
        "admit_source", "external_warrant", "attribution_check", "verify_source",
        "is_computed", "provenance_kind", "EvidenceFirewall",
    )
    hits = []
    for package in PACKAGES:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            text = path.read_text()
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert hits == [], hits
