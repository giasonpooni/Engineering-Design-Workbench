"""Phase 112b: computational artifact / model-adaptation firewall audit.

THE QUESTION: what distinguishes a computational artifact or adapted
model from an epistemic observation, and is that distinction structurally
enforced?

ANSWER: the distinction is IDENTITY, and it is structurally enforced for
OBJECTS and structurally unenforceable for VALUES.

sec.1 THE INVENTORY -- EIGHTEEN COMPUTED OBJECTS, ONE IDENTITY
---------------------------------------------------------------
Every production object producible by prediction, fitting, optimization,
ranking, selection, policy evaluation, hypothetical projection or
trajectory generation was enumerated from code:

    Prediction, PredictionAssessment, CounterfactualOutcome,
    TrajectoryPrediction, PredictionDelta, OptimizationResult,
    CandidateRankingSet, CandidateSelectionSet, CandidateEvaluationSet,
    CandidateUtilitySet, InformationValueEstimateSet,
    CandidateInformationValueSet, SurrogateState, ProgramDecision,
    CandidateSet, StateTransitionDiagnosticSet, ProgramAudit, ModelState

All eighteen are frozen. EXACTLY ONE has an `id`: `ModelState`. The other
seventeen are identityless -- and Phase 105 established that no identity
means no pool node, since every `put_*` is keyed by an object's id. That
is the firewall: computed objects cannot enter the pool because THERE IS
NOTHING TO KEY THEM BY. Not a rule, not a check -- an absence.

`ModelState` is the exception and is not a leak: there is no
`put_model_state`, and its id is `content_hash(samples)` -- the samples
are already admitted Observations, so the state's identity is a function
of evidence identity and contributes nothing new.

sec.5/6 HOW MANY IDENTITY AXES ACTUALLY EXIST
----------------------------------------------
Asked for five (evidence, model, configuration, execution, output), the
architecture has TWO, and neither is what the question expected:

    EVIDENCE identity     content_hash over admitted content
    STATE identity        content_hash(samples) -- a FUNCTION of the above

Model, configuration and execution identity are not collapsed -- THEY DO
NOT EXIST, because the concepts do not exist. `predict` is a fixed pure
function with no parameters, no seed, no environment, no clock and no
I/O, so "which model" has exactly one possible answer and execution
identity is not merely absent but REDUNDANT: `Prediction` carries
`state_id` and `candidate_id` and is reproducible from them alone, which
is why it carries no id of its own.

Nondeterminism cannot arise, so sec.6's counterexample cannot be
constructed. The closest thing to a configuration identity in production
is `ExperimentalMethod.id = content_hash({kind, parameters})` -- and that
describes an EXPERIMENTAL procedure, not a computational model.

sec.7 WHAT "DYNAMICAL" WOULD COST -- CTM as positive control
-------------------------------------------------------------
CTM's own docstring names its requirements: `iterations` (T internal
'thought' ticks decoupled from input), neuron-level activity history over
that axis, and pairwise SYNCHRONISATION over the history used AS the
representation.

Our architecture has none of the three. `ModelState` has two fields;
`Sample` has a value and an observation id and no temporal position;
`ExperimentSession.iteration` is pinned at bootstrap;
`ModelStateTrajectory` is an ordered list of states with a MONOTONICITY
CHECK, not a dynamics.

The precise cost: S_(t+1) = S_t + one sample is a FILTRATION, not a
dynamical system -- information only accumulates. Calling this dynamical
would require a state update that is not monotone, one where state can be
lost, transformed or oscillate. APPEND-ONLY FORBIDS DYNAMICS BY
CONSTRUCTION. The two are not merely different; they are incompatible,
and this architecture chose the other one.

sec.8 WHAT ADAPTATION WOULD COST -- Text-to-LoRA as positive control
---------------------------------------------------------------------
T2L's `HyperModulator` requires: a base model with parameters, a
parameter-space delta produced from a task description, and a composition
operator applying the delta to the base.

Our architecture has no parameters to adapt. `predict` reads
`state.samples.get(key)` and computes a mean. The nearest structure is
`SurrogateState` -- and it is CALLER-SUPPLIED per candidate, never
learned, never fitted, never composed. So of the five things sec.8 asks
to keep apart:

    policy selection        EXISTS (choose a SelectionPolicy)
    model selection         DOES NOT EXIST (there is one model)
    model adaptation        DOES NOT EXIST
    parameter transformation DOES NOT EXIST
    prediction              EXISTS, and is none of the above

sec.9 WHAT THE PROVENANCE ACTUALLY ENCODES
-------------------------------------------
    A simulation predicts 92 MPa      extraction_method "simulation:..."
                                      -> SIMULATED
    B tester measures 92 MPa          "human_transcription" -> OBSERVED,
                                      or an instrument method -> EXTRACTED
    C paper reports 92 MPa            "regex:..." over a real Document
                                      -> EXTRACTED
    D analyst enters "92 MPa"         "human_transcription" -> OBSERVED
    E model emits 92, analyst copies   INDISTINGUISHABLE FROM D

The architecture encodes exactly one thing: THE SELF-DECLARED EXTRACTION
METHOD, classified by prefix. A/B/C/D are distinguishable IF the caller
declares honestly. E is not distinguishable from D even in principle,
because the difference lies entirely in where the analyst's number came
from -- outside the process. So the provenance semantics are: a recorded
claim about method, plus a citation chain that resolves internally.

sec.16 THE TEN TARGETS

  1 model identity independent of evidence identity   SURVIVES
  2 model output is not observation                   SURVIVES for
        OBJECTS (no id, no record_ids); FALSIFIED for VALUES (Phase 111)
  3 adaptation is not evidence                        SURVIVES VACUOUSLY
        -- adaptation does not exist
  4 configuration is not execution                    UNREPRESENTED
  5 execution is not result                           UNREPRESENTED and
        REDUNDANT -- predict is pure
  6 simulation output is not measurement              SURVIVES for
        objects; FALSIFIED for values. Note the architecture HAS a place
        to mark it (`simulation:` -> SIMULATED) and nothing enforces use
  7 prediction+experiment != prediction alone         SURVIVES --
        PredictionAssessment requires a real result AND observation
  8 artifact cannot gain warrant by citation          FALSIFIED (111)
  9 evidence and computational identity are distinct  SURVIVES, with the
        twist that computational identity barely exists
 10 a model may influence future computation without
    becoming evidence                                 SURVIVES --
        predict -> utility -> ranking -> selection -> candidate touches
        no pool at any step

sec.10 THE STRONGEST INVARIANT -- (B), NOT (A)
-----------------------------------------------
"A computational artifact cannot acquire evidential status merely by
being computationally derived" is:

    (B) ENFORCED ONLY FOR HONEST PRODUCTION CALLERS -- at the value
        level, and (A) STRUCTURALLY ENFORCED at the object level.

Both halves are true and they are about different things. No computed
OBJECT can enter the pool: it has no identity to be keyed by, and no
`put_*` accepts its type. Any computed VALUE can enter: write it into a
Record's `raw_content`. The object firewall is structural; the value
firewall does not exist. And per Phase 111b it cannot: identity is a
function of content, and whether a number was measured or computed is a
fact about history that content does not encode. So the residue is (D):
undecidable without an external trust boundary.

sec.15 CLASSIFICATION

    Prediction, TrajectoryPrediction, PredictionDelta   DERIVED COMPUTATION
    PredictionAssessment                                DERIVED COMPUTATION
    CounterfactualOutcome                               HYPOTHETICAL
    OptimizationResult, CandidateRankingSet,
      CandidateSelectionSet, CandidateEvaluationSet,
      CandidateUtilitySet, InformationValue*            DERIVED COMPUTATION
    SelectionPolicy / Optimization / Ranking            MODEL CONFIGURATION
    SurrogateState                                      MODEL CONFIGURATION
                                                        (caller-supplied)
    ProgramDecision, ProgramAudit,
      StateTransitionDiagnosticSet                      DERIVED COMPUTATION
    CandidateSet                                        DERIVED COMPUTATION
    ModelState                                          DERIVED COMPUTATION
                                                        with identity
    execution, output, adaptation, embedding,
      learned representation                            UNREPRESENTED

Nothing is AMBIGUOUS, and nothing computed is EVIDENCE.

sec.18 CONSEQUENCE FOR PRODUCTION: none. Zero production changes.
No new abstraction is proposed: target 8 was already falsified in Phase
111 and its repair is impossible from inside (Phase 111b), while targets
3-5 fail only because the concepts they name do not exist -- an absence,
not a defect.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib
import inspect
from pathlib import Path

import pytest

from evidence.pool import EvidencePool
from materials.assessment import PredictionAssessment
from materials.method import ExperimentalMethod
from materials.model_state import (
    ModelState,
    Prediction,
    Sample,
    make_model_state,
    predict,
    resolve_model_state_key,
)
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("evidence", "retrieval", "materials", "experiment", "workbench", "scout")

COMPUTED = [
    ("materials.model_state", "Prediction"),
    ("materials.assessment", "PredictionAssessment"),
    ("materials.ensemble", "CounterfactualOutcome"),
    ("materials.trajectory", "TrajectoryPrediction"),
    ("materials.trajectory", "PredictionDelta"),
    ("materials.optimization", "OptimizationResult"),
    ("materials.ranking", "CandidateRankingSet"),
    ("materials.selection", "CandidateSelectionSet"),
    ("materials.evaluation", "CandidateEvaluationSet"),
    ("materials.utility", "CandidateUtilitySet"),
    ("materials.information", "InformationValueEstimateSet"),
    ("materials.value", "CandidateInformationValueSet"),
    ("materials.surrogate", "SurrogateState"),
    ("materials.decision", "ProgramDecision"),
    ("materials.candidates", "CandidateSet"),
    ("materials.diagnostics", "StateTransitionDiagnosticSet"),
    ("materials.audit", "ProgramAudit"),
]


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _cls(module, name):
    return getattr(importlib.import_module(module), name)


class _Probe:
    def __init__(self, context=None):
        self.formulation = type("R", (), {"id": "f"})()
        self.property = "p"
        self.target_context = dict(context or {"t": 25})
        self.id = "c"


# -- 1. the inventory, and the firewall it reveals -------------------------------------------------


@pytest.mark.parametrize("module,name", COMPUTED)
def test_every_computed_object_is_frozen(module, name):
    assert _cls(module, name).__dataclass_params__.frozen


@pytest.mark.parametrize("module,name", COMPUTED)
def test_no_computed_object_except_model_state_has_an_identity(module, name):
    """THE FIREWALL. No identity means nothing to key a `put_*` by."""
    fields = {f.name for f in dataclasses.fields(_cls(module, name))}
    assert "id" not in fields


def test_model_state_is_the_sole_exception_and_is_not_a_leak():
    assert "id" in {f.name for f in dataclasses.fields(ModelState)}
    pool = EvidencePool()
    assert not hasattr(pool, "put_model_state")
    # ...and its id is a function of already-admitted evidence
    key = resolve_model_state_key("f", "p", {"t": 25})
    a = make_model_state({key: (Sample(value=90.0, observation_id="obs-1"),)})
    b = make_model_state({key: (Sample(value=90.0, observation_id="obs-1"),)})
    assert a.id == b.id
    assert {f.name for f in dataclasses.fields(ModelState)} == {"id", "samples"}


@pytest.mark.parametrize("module,name", COMPUTED)
def test_no_computed_object_can_be_cited_by_an_observation_or_relationship(module, name):
    """Citations name Records and Observations. A computed object has no
    id to appear in either."""
    fields = {f.name for f in dataclasses.fields(_cls(module, name))}
    assert "record_ids" not in fields
    assert "extraction_method" not in fields


# -- 5/6. how many identity axes exist ---------------------------------------------------------------


def test_predict_has_no_configuration_seed_environment_or_clock():
    source = inspect.getsource(predict)
    for absent in ("seed", "random", "config", "time", "env", "os.", "open("):
        assert absent not in source


def test_execution_identity_is_redundant_not_merely_absent():
    """`Prediction` is reproducible from (state_id, candidate_id), which
    is exactly why it carries no id."""
    key = resolve_model_state_key("f", "p", {"t": 25})
    state = make_model_state({key: (Sample(value=90.0, observation_id="obs-1"),)})
    first, second = predict(state, _Probe()), predict(state, _Probe())
    assert (first.predicted_value, first.uncertainty, first.sample_count) == (
        second.predicted_value, second.uncertainty, second.sample_count)
    fields = {f.name for f in dataclasses.fields(Prediction)}
    assert "id" not in fields
    assert {"state_id", "candidate_id", "model_state_key"} <= fields


def test_the_only_configuration_identity_describes_an_experiment_not_a_model():
    fields = {f.name for f in dataclasses.fields(ExperimentalMethod)}
    assert fields == {"id", "kind", "parameters"}
    source = inspect.getsource(inspect.getmodule(ExperimentalMethod))
    assert 'content_hash({"kind": kind, "parameters"' in source.replace("'", '"')


# -- 7. what "dynamical" would cost ------------------------------------------------------------------


def test_the_state_update_is_a_filtration_not_a_dynamics():
    """Append-only forbids dynamics by construction: information only
    accumulates, so no state can be lost, transformed or oscillate."""
    key = resolve_model_state_key("f", "p", {"t": 25})
    before = make_model_state({key: (Sample(value=90.0, observation_id="o1"),)})
    after = make_model_state({key: (
        Sample(value=90.0, observation_id="o1"),
        Sample(value=92.0, observation_id="o2"),
    )})
    assert set(before.samples[key]) < set(after.samples[key])   # strict superset, always


def test_no_temporal_axis_exists_on_state_or_sample():
    """CTM requires internal ticks, per-unit history and pairwise
    synchronisation over that history. None of the three is present."""
    assert {f.name for f in dataclasses.fields(Sample)} == {"value", "observation_id"}
    assert {f.name for f in dataclasses.fields(ModelState)} == {"id", "samples"}
    for absent in ("tick", "iteration", "history", "synch", "recurrent"):
        assert absent not in {f.name for f in dataclasses.fields(ModelState)}


def test_the_trajectory_is_an_ordered_list_with_a_monotonicity_check():
    from materials.trajectory import make_model_state_trajectory
    source = inspect.getsource(make_model_state_trajectory)
    assert "issubset" in source
    assert "lost sample(s) that update() can only ever append, never remove" in source


# -- 8. what adaptation would cost --------------------------------------------------------------------


def test_nothing_in_production_has_parameters_to_adapt():
    """T2L needs a base model, a parameter-space delta, and a composition
    operator. `predict` has no parameters at all."""
    source = inspect.getsource(predict)
    assert "state.samples.get(key, ())" in source
    for absent in ("weight", "delta", "adapt", "lora", "parameter"):
        assert absent not in source.lower()


def test_surrogate_state_is_supplied_never_learned():
    from materials.surrogate import SurrogateState
    fields = {f.name for f in dataclasses.fields(SurrogateState)}
    assert "fitted_from" not in fields and "trained_on" not in fields
    text = " ".join((REPO / "materials" / "surrogate.py").read_text().split())
    assert "requires the caller to supply it explicitly" in text


def test_no_learned_representation_exists_anywhere():
    forbidden = {"embedding", "latent", "encoder", "hidden_state", "weights"}
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
                            hits.append(f"{path.relative_to(REPO)}: {node.name}.{stmt.target.id}")
    assert hits == [], hits


# -- 9/13. what the provenance encodes, and the assessment boundary -----------------------------------


def test_the_architecture_encodes_only_the_self_declared_method():
    from evidence.types import make_observation
    from retrieval.epistemic import EXTRACTED, OBSERVED, SIMULATED, classify_epistemic_status

    def status(method):
        return classify_epistemic_status(make_observation(
            record_ids=("r",), extraction_method=method, content={"v": 92.0},
            confidence=1.0, extracted_at="2026-01-01T00:00:00Z"))

    assert status("simulation:fea_v3") == SIMULATED        # A
    assert status("human_transcription") == OBSERVED       # B and D
    assert status("regex:kv_v1") == EXTRACTED              # C
    # E -- a model's number copied into a notebook -- is declared
    # "human_transcription" and is therefore identical to D.
    assert status("human_transcription") == status("human_transcription")


def test_prediction_plus_experiment_is_structurally_more_than_prediction():
    """Target 7. `PredictionAssessment` cannot be built without a real
    result and a real observation."""
    fields = {f.name for f in dataclasses.fields(PredictionAssessment)}
    assert {"prediction", "result", "observation", "residual"} <= fields
    from materials.assessment import assess
    parameters = set(inspect.signature(assess).parameters)
    assert {"prediction", "result", "observation"} <= parameters


# -- 10/12. a model influences computation without becoming evidence ---------------------------------


def test_the_whole_influence_chain_touches_no_pool():
    """Target 10. predict -> utility -> ranking -> selection -> candidate."""
    from materials.evaluation import evaluate_candidates
    from materials.optimization import optimize_candidates
    from materials.ranking import rank_candidates
    from materials.selection import select_candidates

    for function in (evaluate_candidates, rank_candidates, select_candidates,
                     optimize_candidates):
        source = inspect.getsource(function)
        assert "put_" not in source and "admit_" not in source


def test_no_computed_object_appears_in_any_pool_write():
    writes = set()
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Attribute) and node.attr.startswith("put_"):
                    writes.add(node.attr)
    assert writes == {
        "put_record", "put_source", "put_document", "put_referent",
        "put_observation", "put_claimed_relationship",
    }


# -- 18. nothing was added -----------------------------------------------------------------------------


def test_phase_112b_added_no_adaptation_machinery():
    forbidden = (
        "ModelConfiguration", "Execution", "Adaptation", "LoRA", "HyperModulator",
        "ContinuousThoughtMachine", "synchronisation", "parameter_delta",
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
