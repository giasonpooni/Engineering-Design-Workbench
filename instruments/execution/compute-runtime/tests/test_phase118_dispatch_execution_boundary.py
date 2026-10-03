"""Phase 118: dispatched measurement / execution boundary audit.

CENTRAL QUESTION: does the architecture distinguish "a measurement was
requested" from "a measurement was executed and produced a result"?

ANSWER: NO, and the failure is sharper than Phase 111's. Phase 111 needed
a caller to fabricate a Source/Document/Record chain and to WRITE a
plausible `extraction_method`. Here the claim is SUPPLIED BY A DEFAULT.

sec.12 THE FALSIFICATION, IN SIX LINES OF PUBLIC API
------------------------------------------------------
    value = 12345.6789                      # invented on this line
    rec = make_record(document_id=..., locator="run 1",
                      raw_content=str(value))
    admit_record(pool, rec); pool.put_record(rec)
    result = make_experimental_result(campaign, entry,
                 content={"property": ..., "value": value, "unit": "MPa"},
                 record_id=rec.id, extracted_at=...)   # NO extraction_method
    admit_experimental_result(pool, result, confidence=1.0)   # ACCEPTED

    result.extraction_method == "measurement:campaign_execution"

No dispatcher was called. No `ActionDispatcher` implementation exists
anywhere (Phase 114). The number was invented in the first line, and the
pool now holds it as a measurement produced by campaign execution, with a
`tested_during` ClaimedRelationship attaching it to the formulation.

sec.3 THE DEFAULT EXISTS TWICE
-------------------------------
    experiment/interface.py   DispatchedMeasurement.extraction_method
                              = "measurement:campaign_execution"
    materials/results.py      make_experimental_result(...,
                                extraction_method: str
                                = "measurement:campaign_execution")

The SECOND is the one that matters. `DispatchedMeasurement`'s default is
defensible -- a dispatcher is meant to measure. But `make_experimental_
result` carries the same default independently, so THE DISPATCHER CAN BE
BYPASSED ENTIRELY AND THE MEASUREMENT CLAIM STILL APPEARS. The value is
not a description of an observed event; it is an assertion made by a
constructor when the caller says nothing.

Every other default in this architecture defaults to UNKNOWN or to an
explicit refusal (`SelectionPolicy` has no defaults at all; `Prediction`
returns None rather than zero; `RankingPolicy.unknown_utility_policy` is
required). This is the one default that asserts the strongest available
claim on the caller's behalf.

sec.1/sec.7 THE CHAIN IS NOT THE CHAIN
----------------------------------------
The assumed shape --
    Campaign -> Dispatch -> Execution -> Result -> Observation
-- is not what the code does. `DispatchedMeasurement` has NO `id` and NO
`candidate_id`: it does not reference what it was dispatched for, and
nothing can reference it. `make_experimental_result(campaign, entry, ...)`
takes the candidate linkage from the CAMPAIGN ENTRY. The real shape is:

    Campaign --entry--------> ExperimentalResult --> Observation
    Dispatch --payload------->        ^
              (content, locator, raw_content, extracted_at, method)

DISPATCH IS A PAYLOAD SUPPLIER, NOT A LINK IN A PROVENANCE CHAIN. The
arrows mean, precisely: campaign->result is REFERENCED (`campaign_id`),
dispatch->result is COPIED (five fields, no reference retained),
result->observation is DERIVED (`admit_experimental_result` builds it),
observation->record is REFERENCED. None of them means CAUSED or PRODUCED.

sec.2 THE FOUR WORLDS
----------------------
  A requested + executed + result   an Observation
  B requested + never executed      NO OBJECT AT ALL. `dispatch()` is a
        plain method call; not calling it leaves no trace anywhere.
  C requested + execution failed    the exception propagates out of
        `run_experiment_step`. No failed-dispatch object, no partial
        state, nothing in the pool. FAILURE DISAPPEARS.
  D requested + fabricated result   INDISTINGUISHABLE FROM A.

B and C are unrepresentable; D is indistinguishable. So the substrate
does not distinguish request from execution from result -- it represents
only the fourth thing, the admitted value.

sec.5 FAILURE SEMANTICS: SIX OF SEVEN CASES ADMIT
---------------------------------------------------
    valid result            ACCEPTED
    NaN                     ACCEPTED
    infinity                ACCEPTED
    negative tensile strength ACCEPTED
    a string where a float belongs ACCEPTED
    missing `value` key     ACCEPTED
    empty content           ValueError (the only rejection)

And NaN PROPAGATES: a cell holding (NaN, 90.0) predicts mean=nan,
variance=nan. There is no `NaNDetectorHook` analogue, no clamp, no drift
monitor.

sec.9 THE ALCHEMI CONTRAST IS EXACT
-------------------------------------
    ALCHEMI                        here
    NaNDetectorHook   -> RAISES    NaN admits and propagates
    MaxForceClampHook -> REPAIRS   no analogue
    EnergyDriftMonitor-> WARNS     no analogue
    DynamicsStage (9 points)       one function call
    converged_mask (per sample)    no execution state at all

ALCHEMI can distinguish numerical failure from instability from physical
implausibility because its transition rule gives "the energy should be
conserved" a meaning. This subsystem has no transition rule beyond
appending, so it has nothing against which a value could be implausible.
That is consistent with Phase 116's finding and is not a defect of the
same kind -- but the ABSENCE OF ANY EXECUTION STATE is.

sec.6 DISPATCH IDENTITY DOES NOT EXIST
----------------------------------------
The question "can an operation go not-executed -> executed without a new
identity?" is malformed here in an informative way: `DispatchedMeasurement`
has no id, so there is no dispatch identity to conflate with execution
identity. Nothing is conflated because nothing is represented. What DOES
change identity is the CONTENT: `ExperimentalResult.id` hashes
campaign_id, candidate_id, formulation_id, property, content, record_id
and extraction_method -- so the same fabricated content under two
declared methods gives two results, and a genuine and a fabricated
measurement with the same content give ONE.

sec.11 DispatchedMeasurement HAS NO EVIDENTIAL STANDING
---------------------------------------------------------
It has no id, so no `put_*` can accept it and no object can cite it. It
cannot reach the pool as itself -- consistent with Phase 112b's
eighteen-objects finding. Its VALUES reach the pool by being copied into
a Record, which is Phase 111's route.

sec.14 CLASSIFICATION

  dispatch implies execution                  FALSIFIED -- dispatch is a
        method call; its absence and its failure are both untraceable
  execution implies result                    FALSIFIED -- an exception
        leaves nothing; there is no partial or failed result
  result implies measurement                  FALSIFIED -- sec.12
  "measurement:campaign_execution" is
        evidence-bearing                      FALSIFIED -- it is a
        constructor default, not an observation of an event
  extraction_method records actual origin     FALSIFIED (Phase 117,
        re-confirmed: here it records nothing, since nobody wrote it)
  failed execution is representable           FALSIFIED -- no state, no
        object, no record; failure disappears
  synthetic result is distinguishable         FALSIFIED -- byte-identical
  execution identity is independent of
        dispatch identity                     VACUOUS -- neither exists
  experiment and simulation remain
        distinguishable downstream            FALSIFIED -- both converge
        at the Record (Phase 117), and here the default actively
        mislabels the computational path as a measurement

SMALLEST GENUINELY UNREPRESENTED DISTINCTION
---------------------------------------------
Not "execution identity" (Phase 116b falsified the ExecutionRecord
candidate on three counts, and those counterexamples still hold).

It is narrower: THAT AN ATTEMPT OCCURRED AND HOW IT ENDED. Worlds B and C
have no representation at all, and that is the only thing in this audit
that is missing rather than merely unverifiable. Whether it should exist
is a separate question this phase was not asked and does not answer --
note only that adding it would not close sec.12, since a fabricator would
simply declare success, exactly as Phase 114 found for a dishonest
dispatcher.

WHAT THIS PHASE ACTUALLY ADDS TO PHASE 111
--------------------------------------------
A second, shorter route with a STRONGER default claim. In Phase 111 the
attacker had to write `extraction_method="regex:kv_v1"` -- a hedge. Here
the attacker writes nothing and the architecture supplies
"measurement:campaign_execution" on their behalf.

CONSEQUENCE FOR PRODUCTION: none. Zero production changes; nothing
repaired. Reported, not fixed, per the standing constraint.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import math
from pathlib import Path

import pytest

from evidence.admission import admit_record
from evidence.pool import EvidencePool
from evidence.types import make_record
from experiment.interface import DispatchedMeasurement
from materials.model_state import (
    Sample,
    make_model_state,
    predict,
    resolve_model_state_key,
)
from materials.results import ExperimentalResult, admit_experimental_result, make_experimental_result
from retrieval.epistemic import EXTRACTED, classify_epistemic_status
from workbench import theme
from workbench.interaction import bootstrap_research_scenario

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("evidence", "retrieval", "materials", "experiment", "workbench", "scout")
TIMESTAMP = "2026-01-01T00:00:00Z"
DEFAULT_METHOD = "measurement:campaign_execution"


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


@pytest.fixture
def scenario():
    state = bootstrap_research_scenario({
        "name": "phase 118", "process": "process-std-190c",
        "formulations": ["formulation-a"], "property": "tensile_strength",
        "criterion": {"operator": ">=", "target": 75.0},
        "contexts": [{"temperature_c": 25}],
    }, clock=_clock())
    candidate = state.candidates.candidates[0]
    entry = next(e for e in state.campaign.entries if e.candidate_id == candidate.id)
    return state, candidate, entry


def _admit_value(state, entry, value, method=None, content=None):
    record = make_record(document_id=state.document_id, locator="run 1",
                         raw_content=str(value))
    assert not isinstance(admit_record(state.pool, record), list)
    state.pool.put_record(record)
    payload = content if content is not None else {
        "property": "tensile_strength", "value": value, "unit": "MPa"}
    kwargs = dict(content=payload, record_id=record.id, extracted_at=TIMESTAMP)
    if method is not None:
        kwargs["extraction_method"] = method
    result = make_experimental_result(state.campaign, entry, **kwargs, extraction_method="measurement:campaign_execution")
    return result, admit_experimental_result(state.pool, result, confidence=1.0)


# -- 12. the falsification -----------------------------------------------------------------------------


def test_an_invented_number_becomes_a_campaign_measurement_with_no_dispatcher(scenario):
    """THE CENTRAL RESULT. Six lines of public API, no ActionDispatcher."""
    state, _, entry = scenario
    invented = 12345.6789
    result, admitted = _admit_value(state, entry, invented)

    assert result.extraction_method == DEFAULT_METHOD
    assert not isinstance(admitted, list)
    observation, relationship = admitted
    assert state.pool.has_observation(observation.id)
    assert observation.content["value"] == invented
    assert classify_epistemic_status(observation) == EXTRACTED
    assert relationship.type == "tested_during"


def test_no_action_dispatcher_implementation_exists_to_have_been_called():
    implementations = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ClassDef):
                    bases = {getattr(b, "id", getattr(b, "attr", "")) for b in node.bases}
                    if "ActionDispatcher" in bases:
                        implementations.append(node.name)
    assert implementations == []


# -- 3. the default exists twice -------------------------------------------------------------------------


def test_both_of_the_two_defaults_have_since_been_removed():
    """WHEN THIS AUDIT RAN there were two independent defaults asserting
    the measurement claim: the second let the dispatcher be bypassed while
    the claim still appeared, and the first was provisionally called
    defensible. Phase 119 removed the second; Phase 120 falsified the
    defence for the first and it was removed too. Neither can now arise
    from a caller's silence."""
    field = [f for f in dataclasses.fields(DispatchedMeasurement)
             if f.name == "extraction_method"][0]
    assert field.default is dataclasses.MISSING
    assert inspect.signature(make_experimental_result).parameters[
        "extraction_method"].default is inspect.Parameter.empty


def test_this_is_the_only_default_in_production_that_asserts_a_claim():
    """Every other default is a refusal or an absence."""
    from materials.optimization import OptimizationPolicy
    from materials.ranking import RankingPolicy
    from materials.selection import SelectionPolicy

    for policy in (SelectionPolicy, OptimizationPolicy, RankingPolicy):
        for field in dataclasses.fields(policy):
            assert field.default is dataclasses.MISSING, f"{policy.__name__}.{field.name}"
    # ...and Prediction returns None rather than zero where it cannot know.
    key = resolve_model_state_key("f", "p", {"t": 25})
    empty = make_model_state({key: ()})

    class _Probe:
        formulation = type("R", (), {"id": "f"})()
        property = "p"
        target_context = {"t": 25}
        id = "probe"

    assert predict(empty, _Probe()).predicted_value is None


# -- 1/7. the chain is not the chain -----------------------------------------------------------------------


def test_dispatch_has_no_identity_and_no_link_to_its_request():
    fields = {f.name for f in dataclasses.fields(DispatchedMeasurement)}
    assert fields == {"content", "record_locator", "record_raw_content",
                      "extracted_at", "extraction_method"}
    assert "id" not in fields
    assert "candidate_id" not in fields


def test_the_result_takes_its_linkage_from_the_campaign_entry_not_the_dispatch():
    parameters = list(inspect.signature(make_experimental_result).parameters)
    assert parameters == ["campaign", "entry", "content", "record_id",
                          "extracted_at", "extraction_method"]
    assert "dispatch" not in parameters and "dispatch_id" not in parameters
    fields = {f.name for f in dataclasses.fields(ExperimentalResult)}
    assert {"campaign_id", "candidate_id", "record_id"} <= fields
    assert "dispatch_id" not in fields


def test_dispatch_is_now_observed_but_its_failure_is_still_not_handled(scenario):
    """WHEN THIS AUDIT RAN, `dispatch` was a bare call: worlds B and C left
    no trace, and an exception propagated with nothing written. Phase 125
    attached an OPTIONAL observer. The exception behaviour is unchanged --
    the trace RECORDS the failure and re-raises; it does not handle it."""
    from experiment.step import run_experiment_step
    source = inspect.getsource(run_experiment_step)
    assert "dispatched = dispatcher.dispatch(chosen_candidate)" in source

    tree = ast.parse(source.lstrip())
    handlers = [n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)]
    assert len(handlers) == 2      # dispatch itself, and everything downstream
    # EVERY handler ends in a bare `raise` -- nothing is ever swallowed
    for handler in handlers:
        assert isinstance(handler.body[-1], ast.Raise)
        assert handler.body[-1].exc is None
    # dispatch-specific tokens only -- `o.status == SELECTED` is the
    # optimization status, a legitimate and unrelated use.
    for absent in ("DispatchFailure", "dispatch_failed", "dispatch_status",
                   "execution_status", "attempted"):
        assert absent not in source


# -- 5. failure semantics -----------------------------------------------------------------------------------


@pytest.mark.parametrize("label,content", [
    ("valid", {"property": "tensile_strength", "value": 90.0, "unit": "MPa"}),
    ("nan", {"property": "tensile_strength", "value": float("nan"), "unit": "MPa"}),
    ("infinity", {"property": "tensile_strength", "value": float("inf"), "unit": "MPa"}),
    ("negative", {"property": "tensile_strength", "value": -500.0, "unit": "MPa"}),
    ("string value", {"property": "tensile_strength", "value": "broken", "unit": "MPa"}),
    ("no value key", {"property": "tensile_strength", "unit": "MPa"}),
])
def test_six_of_seven_failure_modes_admit_as_ordinary_measurements(scenario, label, content):
    state, _, entry = scenario
    _, admitted = _admit_value(state, entry, 0.0, content=content)
    assert not isinstance(admitted, list), label
    observation, _relationship = admitted
    assert classify_epistemic_status(observation) == EXTRACTED


def test_only_empty_content_is_refused(scenario):
    state, _, entry = scenario
    with pytest.raises(ValueError):
        _admit_value(state, entry, 0.0, content={})


def test_nan_propagates_silently_through_the_mean():
    """No NaNDetectorHook analogue, no clamp, no drift monitor."""
    key = resolve_model_state_key("f", "tensile_strength", {"t": 25})
    state = make_model_state({key: (
        Sample(value=float("nan"), observation_id="o1"),
        Sample(value=90.0, observation_id="o2"))})

    class _Probe:
        formulation = type("R", (), {"id": "f"})()
        property = "tensile_strength"
        target_context = {"t": 25}
        id = "probe"

    result = predict(state, _Probe())
    assert math.isnan(result.predicted_value)
    assert math.isnan(result.uncertainty)


def test_no_execution_state_or_failure_taxonomy_exists():
    """The ALCHEMI contrast: three hooks with three remedies there, none
    here."""
    forbidden = {"ExecutionStatus", "DispatchFailure", "MeasurementFailure",
                 "NaNDetector", "ForceClamp", "DriftMonitor", "attempted",
                 "execution_state"}
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {node.name}")
    assert hits == [], hits


# -- 2/6/8. genuine and fabricated results are the same object ----------------------------------------------


def test_a_genuine_and_a_fabricated_result_with_equal_content_are_one_object(scenario):
    """Worlds A and D. `ExperimentalResult.id` hashes content, not origin."""
    state, _, entry = scenario
    genuine, _ = _admit_value(state, entry, 90.0)
    fabricated = make_experimental_result(
        state.campaign, entry,
        content={"property": "tensile_strength", "value": 90.0, "unit": "MPa"},
        record_id=genuine.record_id, extracted_at=TIMESTAMP, extraction_method="measurement:campaign_execution")
    assert genuine.id == fabricated.id


def test_declaring_a_different_method_is_the_only_thing_that_separates_them(scenario):
    state, _, entry = scenario
    measured, _ = _admit_value(state, entry, 90.0)
    simulated = make_experimental_result(
        state.campaign, entry,
        content={"property": "tensile_strength", "value": 90.0, "unit": "MPa"},
        record_id=measured.record_id, extracted_at=TIMESTAMP,
        extraction_method="simulation:fea_v3")
    assert measured.id != simulated.id
    assert measured.content == simulated.content
    # Identity-bearing, unverified, and defaulted -- Phase 117's finding,
    # now with the default doing the declaring.


# -- 11. dispatch has no evidential standing -----------------------------------------------------------------


def test_a_dispatched_measurement_cannot_reach_the_pool_as_itself():
    pool = EvidencePool()
    for absent in ("put_dispatched_measurement", "put_dispatch", "put_measurement"):
        assert not hasattr(pool, absent)
    assert "id" not in {f.name for f in dataclasses.fields(DispatchedMeasurement)}


# -- 13. nothing was repaired --------------------------------------------------------------------------------


def test_phase_118_added_no_execution_machinery():
    forbidden = (
        "ExecutionRecord", "MeasurementExecution", "ObservationOrigin",
        "ProvenanceEvent", "ExecutionStatusEnum", "verify_dispatch",
    )
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            text = path.read_text()
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert hits == [], hits


def test_the_finding_was_acted_on_and_the_rest_was_not():
    """THE REGRESSION LOCK. `extraction_method` is required, so a caller's
    silence can never again become a measurement claim. Everything else
    this audit found -- worlds B and C unrepresentable, world D
    indistinguishable -- is UNCHANGED and unrepaired, by design."""
    assert inspect.signature(make_experimental_result).parameters[
        "extraction_method"].default is inspect.Parameter.empty

    with pytest.raises(TypeError):
        make_experimental_result(campaign=None, entry=None, content={"x": 1},
                                 record_id="r", extracted_at=TIMESTAMP)
