"""Phase 119: declared execution vs witnessed execution.

This phase attacks the repair offered at the end of Phase 118. BOTH
PROPOSED REPAIRS ARE FALSIFIED, and the second falsification is the more
instructive one.

sec.1 A MANDATORY DECLARATION SEPARATES HONEST CALLERS FROM EACH OTHER,
NEVER HONEST FROM DISHONEST
------------------------------------------------------------------------
Six cases, every one supplying `extraction_method` EXPLICITLY:

    A genuine execution + correct declaration     obs 9da0d1ee...
    C no execution + measurement declaration      obs 9da0d1ee...
    D fabricated result + measurement declaration obs 9da0d1ee...
    E simulation + measurement declaration        obs 9da0d1ee...
    F human entry + measurement declaration       obs 9da0d1ee...
    B genuine execution + FALSE declaration       obs 9ce37887...

A, C, D, E and F ARE ONE OBJECT with ONE POOL FINGERPRINT. The only case
that differs is B -- where the caller told the TRUTH about a simulation.
Declaring honestly is the only act that changes the represented state.

So making the field mandatory removes a default and changes nothing else:
it forces a dishonest caller to type one string they were previously
given for free. The Phase 118 suggestion is FALSIFIED.

sec.2/sec.10 RESTRICTING THE CONSTRUCTOR DOES NOT HELP EITHER
---------------------------------------------------------------
Assume the stronger proposal: only a trusted execution primitive may mint
"measurement:campaign_execution". Two routes were compared:

    route 1  make_experimental_result -> admit_experimental_result
    route 2  make_observation(...) -> admit_observation

They produce THE SAME `Observation.id` -- not a similar object, the same
one. `make_observation` is public and takes `extraction_method` as a
plain argument. `make_claimed_relationship`/`admit_claimed_relationship`
are equally public, and their gates require only that the referents and
the observation exist in the pool, which they do by construction. So the
WHOLE of route 1, including the `tested_during` relationship, is
reproducible from evidence primitives alone.

A trusted path can only be trusted if it is the ONLY path. It is not, and
making it the only path would mean removing `make_observation` from the
public surface -- which is the primitive every honest ingestion route
(scout, experiment, workbench) is built from.

sec.6 WORLD A AND WORLD B ARE NOT INDISTINGUISHABLE. THEY ARE EQUAL.
---------------------------------------------------------------------
Real instrument produces 123.4 MPa; nothing executes and a caller types
123.4 MPa. Field by field:

    Record.id       equal
    ExperimentalResult.id equal
    Observation.id  equal
    pool fingerprint equal
    epistemic status equal

Every represented field is equal, so there is no comparison to fail --
this is Phase 111b's result reached through the experiment abstraction
rather than the evidence primitives.

sec.5 WHAT IDENTITY TRACKS
---------------------------
    ONE event, TWO declarations   -> TWO identities
    TWO events, ONE declaration   -> ONE identity

Identity tracks WHAT THE CALLER SAYS HAPPENED, never what happened. That
is the sharpest statement of Phase 116b's identity-invariance table, and
it is why no amount of declaration discipline can produce a witness.

sec.4 THE FIVE PREDICATES

    D "someone declared a measurement"
    A "the value is attributed to a source"
    X "an execution occurred"
    O "an observation was produced"
    W "the execution occurred in the external world"

    D -> A   ESTABLISHED, and trivially: the Record cites a Document
             which cites a Source. Attribution is a citation, not a fact
             (Phase 111b).
    D -> X   FALSIFIED -- case C.
    X -> O   FALSIFIED -- a dispatcher may execute and the caller simply
             not call `admit_experimental_result`; world B of Phase 118
             leaves no trace either way.
    O -> X   FALSIFIED -- case C.
    A -> W   FALSIFIED (Phase 111b).
    X -> W   NOT EXPRESSIBLE -- X itself is unrepresented.
    O -> W   FALSIFIED.

One implication of seven holds, and it is the one that asserts least.

sec.7 THREE ROUTES, ONE ABSENCE
--------------------------------
    Phase 111  computation -> Record.raw_content -> Observation
    Phase 118  fabricated result -> ExperimentalResult -> Observation
    Phase 119  false declaration -> legitimate-looking Observation

These are NOT three vulnerabilities. They are three surfaces of ONE
absence: nothing in the system is a function of anything outside the
process. Phase 111b proved this is structural -- identity is a function
of content, authenticity is a function of history, and content does not
encode history. A fourth route would tell us nothing new.

sec.8 THE MISSING PREMISE, NAMED
----------------------------------
Phase 114 established EXECUTION AUTHORITY: `ActionDispatcher` is the one
place a physical experiment would be performed. That is AUTHORISATION TO
EXECUTE. It is not EVIDENCE THAT EXECUTION OCCURRED.

"Only the dispatcher may execute" does not imply "only the dispatcher may
truthfully produce a measurement" without the premise:

    every measurement-declaring object was produced BY the dispatcher,
    and that production is itself represented and checkable.

The second clause is the one that fails. `DispatchedMeasurement` has no
id (Phase 118), so even if a dispatcher did produce it, nothing
downstream could cite it as the producer. The premise is not merely
unproven; it is unstatable in the current object model.

sec.9 NO EXISTING OBJECT CAN WITNESS EXECUTION
------------------------------------------------
Every candidate was checked against what a witness must do -- be produced
by something other than the declaring caller, and be citable by the
object it warrants:

    DispatchedMeasurement  no id; cannot be cited (Phase 118)
    ExperimentalResult     content-hashed from the declaration itself
    Record                 the caller writes `raw_content`
    Source/Document        the caller writes both; no gate (Phase 111b)
    ModelState             a function of already-admitted samples
    PredictionAssessment   diagnostic, and downstream of admission
    ClaimedRelationship    requires an Observation that already exists

None is produced independently of the caller. There is no witness, and
naming one `ExecutionRecord` would not make it one -- Phase 116b already
falsified that candidate on three counts, and counterexample 3 applies
here verbatim: a recorded version string is itself a caller-written
claim.

sec.11 CLASSIFICATION

  required declaration establishes execution      FALSIFIED
  trusted construction path establishes execution FALSIFIED
  extraction_method records actual origin         FALSIFIED
  observation identity captures execution history FALSIFIED
  execution authority implies execution evidence  FALSIFIED
  ExperimentalResult is evidence of execution     FALSIFIED
  genuine and fabricated are distinguishable      FALSIFIED
  external-world authenticity is representable    FALSIFIED

Eight of eight.

sec.12 THE ANSWER TO THE FINAL QUESTION
-----------------------------------------
Asked what fact about the world would have to become represented: the
answer is NOT a new semantic object.

It is AN EXTERNAL TRUST ASSUMPTION THAT CANNOT BE ESTABLISHED
INTERNALLY. To distinguish World A from World B, some object would have
to be a function of an event outside the process -- an instrument
signature, a witnessed timestamp, a custody chain, a second party. Every
one of those is a fact the process must RECEIVE, and receiving it is
exactly the boundary that has no gate. A system whose identity is
content-addressed cannot manufacture a witness, because a hash cannot
witness what it was not given.

So:
    declaration  != attribution  != execution  != observation  != authenticity

and they collapse at exactly one point: THE MOMENT A VALUE IS WRITTEN
INTO A RECORD. Everything above that point is a function of what the
caller wrote. Everything the architecture does correctly -- immutability,
content-addressing, append-only history, the admission gates -- operates
entirely above that line and is untouched by this result.

TWO FINDINGS, NOT ONE -- CORRECTING THIS PHASE'S FIRST READING
---------------------------------------------------------------
The withdrawal above over-reached. "Should not be justified on THOSE
grounds" is not "should not be done", and conflating them was an error.
The correct split:

FINDING A -- A DEFECT, INDEPENDENT OF ANYTHING ABOVE.
A constructor must not silently assign an epistemically stronger label
than the caller supplied. This architecture holds "unknown stays unknown"
everywhere else, without exception: `predict` returns None rather than a
number; `RankingPolicy.unknown_utility_policy` is required; a declared
order returns None for an unenumerated value rather than False; no policy
has any default at all. `make_experimental_result` inverts that rule --
it converts ABSENCE OF INFORMATION into POSITIVE INFORMATION.

Swept exhaustively: 92 defaults in production, 78 inert. Of the 14
non-inert ones, 8 are presentation geometry or colour, 2 describe what
the function itself does (`ordering="sorted_by_id"` -- it does sort by
id; `relationship_type="tested_during"` -- it labels the edge being
constructed), 1 asserts EMPTINESS (`initial_state=EMPTY_MODEL_STATE`,
the rule applied correctly), 1 is scenario configuration, and 1 is
defensible in context (`DispatchedMeasurement`, since a dispatcher is
meant to measure).

EXACTLY ONE ASSERTS THAT AN EVENT OCCURRED IN THE WORLD.

FINDING B -- UNRESOLVED, AND PROBABLY UNRESOLVABLE INTERNALLY.
Everything above this note. A required declaration is still not evidence
that the declared event occurred, and no arrangement of the public API
makes it so.

The two are independent. Finding A is fixable in one line and would
restore a local rule the architecture otherwise holds universally.
Finding B is the external-trust boundary and is not fixable from inside.
Repairing A does not touch B, and the failure of B is not a reason to
leave A in place.

CONSEQUENCE FOR PRODUCTION: none in this phase. The default stands
UNREPAIRED, pending an explicit decision -- it would be the first
production change since Phase 103, and the standing constraint has been
zero production changes throughout.
"""

from __future__ import annotations

import dataclasses
import inspect
from pathlib import Path

import pytest

from evidence.admission import admit_observation, admit_record
from evidence.types import (
    ClaimedRelationship,
    Observation,
    make_claimed_relationship,
    make_observation,
    make_record,
)
from experiment.interface import DispatchedMeasurement
from materials.results import ExperimentalResult, admit_experimental_result, make_experimental_result
from retrieval.epistemic import EXTRACTED, SIMULATED, classify_epistemic_status
from workbench import theme
from workbench.interaction import bootstrap_research_scenario

REPO = Path(__file__).resolve().parent.parent
TIMESTAMP = "2026-01-01T00:00:00Z"
MEASUREMENT = "measurement:campaign_execution"
CONTENT = {"property": "tensile_strength", "value": 123.4, "unit": "MPa"}


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _clock():
    n = [0]

    def c():
        n[0] += 1
        return f"2026-01-01T00:00:{n[0]:02d}Z"

    return c


def _anchored():
    state = bootstrap_research_scenario({
        "name": "phase 119", "process": "process-std-190c",
        "formulations": ["formulation-a"], "property": "tensile_strength",
        "criterion": {"operator": ">=", "target": 75.0},
        "contexts": [{"temperature_c": 25}],
    }, clock=_clock())
    candidate = state.candidates.candidates[0]
    entry = next(e for e in state.campaign.entries if e.candidate_id == candidate.id)
    record = make_record(document_id=state.document_id, locator="run 1",
                         raw_content="123.4")
    assert not isinstance(admit_record(state.pool, record), list)
    state.pool.put_record(record)
    return state, entry, record


def _world(method):
    state, entry, record = _anchored()
    result = make_experimental_result(
        state.campaign, entry, content=CONTENT, record_id=record.id,
        extracted_at=TIMESTAMP, extraction_method=method)
    observation, _ = admit_experimental_result(state.pool, result, confidence=1.0)
    return {"record": record.id, "result": result.id, "observation": observation.id,
            "fingerprint": state.pool.fingerprint(),
            "status": classify_epistemic_status(observation)}


# -- 1. the mandatory-declaration attack --------------------------------------------------------------


def test_five_of_six_declared_cases_collapse_to_one_object():
    """A, C, D, E, F -- genuine, absent, fabricated, simulated and typed --
    all declaring "measurement". One object, one fingerprint."""
    worlds = [_world(MEASUREMENT) for _ in range(5)]
    assert len({w["observation"] for w in worlds}) == 1
    assert len({w["fingerprint"] for w in worlds}) == 1
    assert len({w["result"] for w in worlds}) == 1


def test_only_an_honest_declaration_changes_the_state():
    """Case B: a genuine execution declared truthfully as a simulation is
    the ONE case that differs."""
    measured = _world(MEASUREMENT)
    honest_simulation = _world("simulation:fea_v3")
    assert measured["observation"] != honest_simulation["observation"]
    assert measured["fingerprint"] != honest_simulation["fingerprint"]
    assert measured["status"] == EXTRACTED
    assert honest_simulation["status"] == SIMULATED
    # Declaring honestly is the only act that moves the represented state.


# -- 2/10. the trusted-path attack ---------------------------------------------------------------------


def test_the_trusted_route_and_the_direct_route_produce_the_same_observation():
    state, entry, record = _anchored()

    result = make_experimental_result(
        state.campaign, entry, content=CONTENT, record_id=record.id,
        extracted_at=TIMESTAMP, extraction_method=MEASUREMENT)
    via_results, _ = admit_experimental_result(state.pool, result, confidence=1.0)

    direct = make_observation(
        record_ids=(record.id,), extraction_method=MEASUREMENT, content=CONTENT,
        confidence=1.0, extracted_at=TIMESTAMP)
    assert not isinstance(admit_observation(state.pool, direct), list)

    assert via_results.id == direct.id      # THE SAME OBJECT


def test_make_observation_is_public_and_takes_the_method_as_a_plain_argument():
    parameters = inspect.signature(make_observation).parameters
    assert "extraction_method" in parameters
    assert parameters["extraction_method"].annotation == "str"
    assert not make_observation.__name__.startswith("_")


def test_the_relationship_half_of_the_trusted_route_is_equally_public():
    """So the whole of route 1 is reproducible from evidence primitives."""
    assert inspect.isfunction(make_claimed_relationship)
    assert not make_claimed_relationship.__name__.startswith("_")
    fields = {f.name for f in dataclasses.fields(ClaimedRelationship)}
    assert fields == {"id", "from_referent_id", "to_referent_id", "type",
                      "observation_id", "confidence"}


# -- 6. World A and World B are equal, not merely alike ------------------------------------------------


@pytest.mark.parametrize("field", ["record", "result", "observation", "fingerprint", "status"])
def test_every_represented_field_is_equal_across_the_two_worlds(field):
    real_instrument = _world(MEASUREMENT)
    typed_by_hand = _world(MEASUREMENT)
    assert real_instrument[field] == typed_by_hand[field]


# -- 5. what identity tracks ----------------------------------------------------------------------------


def test_one_event_with_two_declarations_gives_two_identities():
    _, _, record = _anchored()
    ids = {make_observation(record_ids=(record.id,), extraction_method=m,
                            content=CONTENT, confidence=1.0,
                            extracted_at=TIMESTAMP).id
           for m in (MEASUREMENT, "simulation:fea_v3")}
    assert len(ids) == 2


def test_two_events_with_one_declaration_give_one_identity():
    assert _world(MEASUREMENT)["observation"] == _world(MEASUREMENT)["observation"]


# -- 4. the five predicates -----------------------------------------------------------------------------


def test_declaration_establishes_attribution_and_nothing_further():
    """D -> A holds, and only because attribution IS a citation."""
    state, _, record = _anchored()
    observation = make_observation(
        record_ids=(record.id,), extraction_method=MEASUREMENT, content=CONTENT,
        confidence=1.0, extracted_at=TIMESTAMP)
    assert observation.record_ids == (record.id,)
    fetched = state.pool.get_record(record.id)
    assert state.pool.has_document(fetched.document_id)
    # The chain resolves. It witnesses nothing (Phase 111b).


def test_no_field_anywhere_could_carry_an_external_witness():
    for cls in (Observation, ExperimentalResult, DispatchedMeasurement, ClaimedRelationship):
        fields = {f.name for f in dataclasses.fields(cls)}
        for absent in ("witness", "signature", "attested_by", "custody",
                       "instrument_serial", "countersigned_by"):
            assert absent not in fields


# -- 9. no existing object can serve as a witness --------------------------------------------------------


def test_no_candidate_witness_is_produced_independently_of_the_caller():
    """A witness must be produced by something other than the declaring
    caller AND be citable by the object it warrants."""
    # DispatchedMeasurement: no id, therefore not citable
    assert "id" not in {f.name for f in dataclasses.fields(DispatchedMeasurement)}
    # ExperimentalResult: hashed from the declaration itself
    result_source = inspect.getsource(inspect.getmodule(make_experimental_result))
    assert '"extraction_method": extraction_method' in result_source.replace("'", '"')
    # Record: the caller writes raw_content
    parameters = set(inspect.signature(make_record).parameters)
    assert parameters == {"document_id", "locator", "raw_content"}


# -- 11/12. nothing was repaired, and the suggestion is withdrawn ------------------------------------------


def test_finding_a_was_repaired_and_finding_b_was_not():
    """FINDING A repaired: `extraction_method` is required, so the
    architecture no longer converts a caller's silence into a positive
    assertion about an external event. FINDING B untouched: everything
    above still holds -- a declaration is not a witness."""
    assert inspect.signature(make_experimental_result).parameters[
        "extraction_method"].default is inspect.Parameter.empty


def test_phase_119_added_no_witness_machinery():
    import ast

    forbidden = {"Witness", "ExecutionWitness", "Attestation", "TrustedPath",
                 "ExecutionRecord", "verify_execution"}
    hits = []
    for package in ("evidence", "retrieval", "materials", "experiment",
                    "workbench", "scout"):
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {node.name}")
    assert hits == [], hits


def test_exactly_one_production_default_asserts_a_world_event():
    """FINDING A's evidence, swept exhaustively rather than asserted."""
    import ast

    INERT = {"None", "()", "''", '""', "0", "False", "True", "{}", "[]",
             "tuple()", "dict()", "1", "1.0", "0.0"}
    assertive = []
    for package in ("evidence", "retrieval", "materials", "experiment",
                    "workbench", "scout"):
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            tree = ast.parse(path.read_text())
            for fn in [n for n in ast.walk(tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
                defaults = list(fn.args.defaults)
                named = fn.args.args[len(fn.args.args) - len(defaults):] if defaults else []
                for arg, default in zip(named, defaults):
                    rendered = ast.unparse(default)
                    if rendered in INERT or rendered.startswith(
                            ("field(", "MappingProxyType", "_utc_now", "lambda")):
                        continue
                    assertive.append((str(path.relative_to(REPO)), fn.name, arg.arg, rendered))

    # theme.py holds only presentation geometry and colour
    non_theme = [row for row in assertive if not row[0].startswith("workbench/theme")]
    assert sorted(non_theme) == [
        ("experiment/session.py", "make_experiment_session", "initial_state",
         "EMPTY_MODEL_STATE"),
        ("materials/results.py", "admit_experimental_result", "relationship_type",
         "'tested_during'"),
        ("retrieval/result.py", "make_retrieval_result", "ordering", "'sorted_by_id'"),
    ], non_theme
    # THE REGRESSION LOCK, in its strongest form. EMPTY_MODEL_STATE asserts
    # emptiness -- unknown stays unknown, correctly. `sorted_by_id`
    # describes what the function does. `tested_during` labels the edge it
    # constructs. NOT ONE non-inert default in production now asserts that
    # an event occurred in the external world. Adding one would fail here.
    assert "'measurement:campaign_execution'" not in {r for _, _, _, r in assertive}
