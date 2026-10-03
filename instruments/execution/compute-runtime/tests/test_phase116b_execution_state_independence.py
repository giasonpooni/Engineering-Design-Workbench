"""Phase 116b: execution/state independence, identity invariance, and the
common-carrier attack at the execution boundary.

Covers the parts of the final Phase 114 spec not already settled by
Phases 114 (execution existence), 115 (execution identity vs GROMACS) and
116 (earned dynamics vs diffeqpy/HOOMD).

NVIDIA ALCHEMI TOOLKIT (nvalchemi-toolkit, 195,808 LOC) -- CLONED AND
READ. It is the strongest control in the whole program on two points.

FIRST, THE TRANSITION RULE DICTATES THE STRUCTURE OF THE STEP.
`DynamicsStage` decomposes ONE integrator step into NINE named points:
BEFORE_STEP, BEFORE/AFTER_PRE_UPDATE, BEFORE/AFTER_COMPUTE,
BEFORE/AFTER_POST_UPDATE, AFTER_STEP, ON_CONVERGE. That decomposition is
velocity-Verlet's own shape -- half-kick, force evaluation, half-kick --
and it exists because the integrator cannot be written as a single
F(x). This is the THIRD independent confirmation, after GROMACS's
`pres_prev` and diffeqpy's DDE history, that state and step structure
are set by the transition rule and never by intuition.

SECOND, AND SHARPER: ALCHEMI SEPARATES THE FAILURE MODES THAT THE
AUTONOMOUS-SEARCH TOOLKITS COLLAPSE. Three distinct hooks, three
distinct responses:

    NaNDetectorHook         non-finite forces/energy -> RAISES
    MaxForceClampHook       excessive force magnitude -> REPAIRS in place
    EnergyDriftMonitorHook  energy not conserved under a symplectic
                            integrator -> WARNS or STOPS

Numerical failure, numerical instability, and PHYSICAL implausibility
are three different events with three different remedies. Compare Phase
112a: `node.is_buggy = response["is_bug"] or node.exc_type is not None`.
The mature simulation toolkit distinguishes exactly what the autonomous
search toolkit fuses -- and it can, because its transition rule gives
"the energy should be conserved" a meaning. Phase 112a's finding that
the failure taxonomy is a COMPUTATIONAL gap, not an epistemic one, now
has its positive control.

Also notable: `DynamicsContext.converged_mask` is a per-sample boolean
TENSOR, not a global flag. Convergence is kept per item and typed, where
ShinkaEvolve keeps `correct: bool` on the artifact.

ALCHEMI's transition rule is a LEARNED model forward pass (the COMPUTE
stage), making it the one control where the force field itself is
learned -- distinct from GROMACS (analytic) and diffeqpy (user
function). It changes none of this program's conclusions: a learned
transition rule is still a transition rule, and its outputs still reach
evidence only by the Phase 111 path.

sec.9 STATE IDENTITY AND EXECUTION IDENTITY ARE PROVABLY INDEPENDENT
---------------------------------------------------------------------
Three samples admitted in all six possible orders produce SIX DISTINCT
INTERMEDIATE PATHS and ONE final `ModelState.id`. `make_model_state`
sorts by `(value, observation_id)`, so the identity is invariant to the
order in which evidence arrived.

    six execution histories -> one state identity

That is the counterexample sec.9 asks for, constructed rather than
argued. The converse case -- same configuration, different stochastic
trajectory -- CANNOT be constructed here, because no randomness exists
(Phase 116). So the two identities are independent in the one direction
the architecture can express, and the other direction is vacuous.

And the path is kept NOWHERE. `ModelStateTrajectory` must be handed the
states by a caller who retained them; the pool stores no ordering at all.
History is reconstructible only by whoever already had it.

sec.13 THE IDENTITY-INVARIANCE TABLE

    change                              identity    why
    representation (25 -> 25.0)         MINTS NEW   the cell key changes
    serialization                       PRESERVES   canonical sorted-key JSON
    hardware                            PRESERVES   not represented
    execution order                     PRESERVES   proven above
    seed                                N/A         no randomness exists
    software version                    PRESERVES   not represented
    model checkpoint                    N/A         no model, no checkpoint
    the measured value                  MINTS NEW   in the hash
    confidence                          PRESERVES   excluded from identity
    extracted_at                        PRESERVES   excluded from identity
    extraction_method                   MINTS NEW   identity-bearing
    source name                         MINTS NEW   transitively

THE SHAPE OF THAT TABLE IS THE FINDING: every change that preserves
identity is one the architecture does not represent, and every change
that mints one is recorded content. IDENTITY TRACKS THE RECORD, NEVER
THE EXECUTION. Reproducibility is therefore unrepresentable here not
because it was overlooked but because its inputs -- hardware, version,
seed, order -- are all in the first column.

sec.14 THE COMMON-CARRIER ATTACK: ALL NINE REJECTED
-----------------------------------------------------
  Execution   would need (executable, inputs, params, environment,
              outputs). "environment" is a NUISANCE parameter for
              GROMACS (nnodes changes summation order) and a DETERMINANT
              for HOOMD (rank enters the PRNG). One field, two semantics.
  Run         a synonym for Execution with no additional content.
  Simulation  unifies GROMACS (force field + integrator), HOOMD
              (operations + device + counter-PRNG) and diffeqpy (a user
              function + a chosen solver). Their "parameters" are
              force-field constants, operation settings and `p` -- the
              non-common field Phase 110 already rejected.
  Trajectory  see sec.10 below: it would have to be simultaneously an
              ordered collection, a provenance record and a result.
  State       Phase 116 showed the word spans three layers with different
              identity, temporality and mutability.
  Process     an OS concept, not a scientific one.
  Workflow    Phase 114 found no workflow exists here at all; a carrier
              for an absent concept is not an abstraction.
  Transition  GROMACS integrates, diffeqpy calls a solver, ours appends.
              A carrier would make set union and Verlet integration the
              same operation.
  Dynamics    Phase 116: two of seven prerequisites present.

Every candidate requires semantic compression, so every candidate is
rejected -- the same result Phase 110 reached one layer up, by the same
test.

sec.10 WHAT A TRAJECTORY IS HERE
---------------------------------
`ModelStateTrajectory` is AN ORDERED COLLECTION OF STATES AND NOTHING
ELSE. Its entries carry `position` (an integer), the state, its id and
its predecessor's id. Ordering IS semantically meaningful -- the
constructor REJECTS a sequence in which any cell lost a sample -- but
that meaning is exactly monotone accumulation, not continuity, not a
metric, and not a path in any space. It is not a state, not a provenance
record (the pool holds no ordering), and not an execution result
(nothing executed).

sec.16 THE STRONGEST CANDIDATE, AND ITS THREE COUNTEREXAMPLES
---------------------------------------------------------------
CANDIDATE: "The smallest missing abstraction at the execution/dynamics
boundary is an ExecutionRecord binding (executable identity, inputs,
parameters, environment) to (outputs)."

  COUNTEREXAMPLE 1 -- ONE FIELD, TWO SEMANTICS. `environment` is a
  nuisance parameter in GROMACS and a determinant in HOOMD. A record
  storing both cannot answer "does changing this change the result?",
  which is the only question an execution record exists to answer.

  COUNTEREXAMPLE 2 -- NO CONSUMER. Phase 114 found `ActionDispatcher`
  specified and empty; nothing executes. Phase 112b found execution
  identity REDUNDANT while `predict` is pure and `Prediction` is
  reproducible from `(state_id, candidate_id)`. The record would
  describe executions that do not occur.

  COUNTEREXAMPLE 3 -- IT WOULD NOT CLOSE PHASE 111. "GROMACS 2024
  produced 1.02" is itself a caller-written claim. Phase 111b proved
  content cannot encode history outside the process, so an
  ExecutionRecord is a BETTER-LABELLED FABRICATION, not a warrant.

CANDIDATE FALSIFIED. Negative result preserved; nothing proposed.

sec.18 THE ANSWERS
-------------------
 1 execution means: a Protocol with one method, specified and empty here;
   a checkpointed integrator run in GROMACS; a device plus operations in
   HOOMD; `solve(prob, alg, opts)` in diffeqpy.
 2 execution identity: ABSENT here, PRESENT and CHECKED in GROMACS.
 3 independent: YES, proven by construction above.
 4 genuine dynamics: GROMACS, HOOMD, diffeqpy.
 5 procedural iteration only: this architecture -- a filtration.
 6 trajectory: a COMPUTATIONAL ARTIFACT here (an ordered collection with
   a monotonicity invariant), a scientific object in GROMACS only because
   the integrator gives its ordering physical meaning.
 7 simulation becomes evidence NEVER automatically, and always by the
   Phase 111 path: a value written into a Record.
 8 falsified carriers: all nine, plus the ExecutionRecord candidate.
 9 survives: state identity is order-invariant; identity tracks the
   record; the evidence boundary is unmoved by any of the four substrates.
10 smallest next experiment: whether `extraction_method` -- the one
   self-declared field that IS identity-bearing -- can be shown to carry
   any load beyond classification, since it is the only place a
   simulation and a measurement currently differ.

Zero production changes.
"""

from __future__ import annotations

import dataclasses
import itertools
from pathlib import Path

import pytest

from materials.model_state import Sample, make_model_state, resolve_model_state_key
from materials.trajectory import ModelStateTrajectory, TrajectoryEntry, make_model_state_trajectory
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
KEY = resolve_model_state_key("f", "p", {"t": 25})
SAMPLES = (
    Sample(value=90.0, observation_id="o1"),
    Sample(value=92.0, observation_id="o2"),
    Sample(value=88.0, observation_id="o3"),
)


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


# -- 9. six histories, one identity ------------------------------------------------------------------


def test_state_identity_is_invariant_to_the_order_evidence_arrived():
    identities = {make_model_state({KEY: order}).id
                  for order in itertools.permutations(SAMPLES)}
    assert len(identities) == 1


def test_the_intermediate_paths_all_differ_while_the_endpoint_does_not():
    paths = []
    for order in itertools.permutations(SAMPLES):
        accumulated: tuple = ()
        sequence = []
        for sample in order:
            accumulated = accumulated + (sample,)
            sequence.append(make_model_state({KEY: accumulated}).id)
        paths.append(tuple(sequence))
    assert len(set(paths)) == 6
    assert len({path[-1] for path in paths}) == 1


def test_no_ordering_is_stored_anywhere_in_the_pool():
    """The path is reconstructible only by a caller who kept the states."""
    from evidence.pool import EvidencePool
    pool = EvidencePool()
    for absent in ("put_state", "put_trajectory", "states", "history"):
        assert not hasattr(pool, absent)


def test_a_stochastic_counterexample_cannot_be_constructed():
    """Same configuration, different trajectory -- vacuous here."""
    first = make_model_state({KEY: SAMPLES})
    second = make_model_state({KEY: SAMPLES})
    assert first.id == second.id


# -- 13. the identity-invariance table ----------------------------------------------------------------


def test_serialization_and_key_order_preserve_identity():
    from evidence.identity import content_hash
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})


def test_representation_change_mints_a_new_identity():
    from evidence.identity import content_hash
    assert content_hash({"t": 25}) != content_hash({"t": 25.0})


@pytest.mark.parametrize("field,mints", [
    ("extraction_method", True),
    ("content", True),
    ("record_ids", True),
    ("confidence", False),
    ("extracted_at", False),
])
def test_observation_identity_tracks_the_record_not_the_execution(field, mints):
    from evidence.types import make_observation
    base = dict(record_ids=("r",), extraction_method="regex:kv_v1",
                content={"v": 90.0}, confidence=1.0,
                extracted_at="2026-01-01T00:00:00Z")
    altered = dict(base)
    altered[field] = {
        "extraction_method": "model:llm",
        "content": {"v": 91.0},
        "record_ids": ("r2",),
        "confidence": 0.1,
        "extracted_at": "2099-01-01T00:00:00Z",
    }[field]
    assert (make_observation(**base).id != make_observation(**altered).id) is mints


def test_nothing_representable_records_hardware_version_or_seed():
    """Every identity-preserving change in the table is a change to
    something the architecture does not represent."""
    from evidence.types import Observation
    from materials.results import ExperimentalResult
    for cls in (Observation, ExperimentalResult):
        fields = {f.name for f in dataclasses.fields(cls)}
        for absent in ("hardware", "version", "seed", "environment", "order"):
            assert absent not in fields


# -- 10. what a trajectory is -------------------------------------------------------------------------


def test_a_trajectory_is_an_ordered_collection_with_a_monotonicity_invariant():
    a = make_model_state({KEY: SAMPLES[:1]})
    b = make_model_state({KEY: SAMPLES[:2]})
    trajectory = make_model_state_trajectory((a, b))
    assert isinstance(trajectory, ModelStateTrajectory)
    assert [e.position for e in trajectory.entries] == [0, 1]
    assert trajectory.entries[1].predecessor_state_id == a.id

    with pytest.raises(ValueError, match="lost sample"):
        make_model_state_trajectory((b, a))       # ordering IS meaningful


def test_a_trajectory_entry_carries_a_position_never_a_time():
    fields = {f.name for f in dataclasses.fields(TrajectoryEntry)}
    assert fields == {"position", "state", "state_id", "predecessor_state_id"}


def test_a_trajectory_has_no_identity_of_its_own():
    """So it is not a provenance record and not an execution result."""
    assert "id" not in {f.name for f in dataclasses.fields(ModelStateTrajectory)}


# -- 14/16. the carriers, and the candidate ------------------------------------------------------------


CARRIERS = ("Execution", "Run", "Simulation", "Trajectory", "State",
            "Process", "Workflow", "Transition", "Dynamics", "ExecutionRecord")


@pytest.mark.parametrize("carrier", CARRIERS)
def test_no_common_carrier_was_introduced(carrier):
    import ast
    hits = []
    for package in ("evidence", "retrieval", "materials", "experiment", "workbench", "scout"):
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ClassDef) and node.name == carrier:
                    hits.append(f"{path.relative_to(REPO)}: {node.name}")
    assert hits == [], hits


def test_the_execution_record_candidate_has_no_consumer():
    """Counterexample 2: nothing executes, and `Prediction` is already
    reproducible from (state_id, candidate_id)."""
    import inspect
    from materials.model_state import Prediction, predict
    fields = {f.name for f in dataclasses.fields(Prediction)}
    assert {"state_id", "candidate_id"} <= fields
    assert "id" not in fields
    assert set(inspect.signature(predict).parameters) == {"state", "candidate"}
