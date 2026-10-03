"""Phase 116: earned-dynamics audit.

Positive controls, cloned and read: diffeqpy / DifferentialEquations.jl
(447 LOC wrapper over the Julia stack) and HOOMD-blue.

sec.1 THE PROBLEM TUPLE, AND WHAT IS *NOT* IN IT
-------------------------------------------------
    ODEProblem(f, u0, tspan, p)

    f      TRANSITION RULE      -- the law, as a function
    u0     INITIAL CONDITION    -- NOT the state; a point the state
                                   starts at
    tspan  TEMPORAL DOMAIN      -- and the applicability domain
    p      PARAMETER            -- distinct from both state and law

    Tsit5(), Vern9(), Rodas5P(),
    abstol, reltol, saveat,
    Float32/Float64, jit, GPU    SOLVER / EXECUTION CONFIGURATION

THE DECISIVE STRUCTURAL FACT: the solver is NOT a field of the problem.
It is an argument to `solve(prob, Vern9(), abstol=1e-10)`. The library
separates the MATHEMATICAL PROBLEM from the NUMERICAL METHOD at the API
level.

This FALSIFIES sec.8's proposition. Different solvers on the same problem
are the SAME MODEL under DIFFERENT EXECUTIONS -- the positive control
says so in its own type signature. A solver is not a model; it is an
approximation scheme with its own error controls, and `de.remake`/`solve`
exist precisely so one problem can be solved many ways.

sec.11 DDE: STATE SUFFICIENCY IS SET BY THE TRANSITION RULE
------------------------------------------------------------
A delay equation needs `h(p, t-lag)` -- history BEFORE t0. So
(current state + parameters) is NOT sufficient, and history is a
SEPARATE SEMANTIC OBJECT: not an initial condition (it is a FUNCTION, not
a point), not an external input (it is the system's own past), not state
(it is not carried forward, it is looked up).

This is the same result GROMACS gave in Phase 115 from the opposite
direction: `t_state` carries `pres_prev`/`svir_prev`/`fvir_prev` because
the integrator needs them. Neither system decides what "state" means by
intuition; the transition rule decides it.

sec.10 DAE: THE STATE SPACE ITSELF SPLITS
------------------------------------------
`f(du,u,p,t) = 0` with `differential_vars` falsifies the idea that a
dynamical system must be `du/dt = f(u,p,t)`. Some components are
EVOLVED and some are CONSTRAINED, and the declaration of which is which
is data the user supplies. "State" is not one kind of thing even inside
one problem.

sec.9/sec.12 STOCHASTIC REALIZATION IS A SEPARATE AXIS
--------------------------------------------------------
For `du = f(u,t)dt + g(u,t)dW`, two trajectories can share model
identity and parameter identity and differ in execution and result. The
EnsembleProblem interface names the axes directly: `ctx.sim_id`,
`ctx.repeat`, `ctx.rng`, `ctx.sim_seed`.

HOOMD-blue makes this exact and is the sharpest finding of the phase.
Its `seed` docstring:

    random_value = f(seed, timestep, particle identifiers, MPI ranks,
                     and other unique identifying values)

A COUNTER-BASED PRNG: the stochastic realization is a PURE FUNCTION of
declared inputs, so it is content-addressable in principle. And it
INCLUDES MPI RANK -- so the parallel decomposition is part of the
realization, exactly as GROMACS records `nnodes`/`dd_nc`/`npme`. Two
mature simulation codes, independently, make the parallel configuration
part of execution identity.

sec.7 TWO DIFFERENT OPERATIONS SHARE THE WORD "INTERPOLATION"
--------------------------------------------------------------
`sol(t*)` at an unobserved t* is a NUMERICAL RECONSTRUCTION: dense output
consistent with the integrator's order, warranted by the solver's own
error control, and applicable strictly within `tspan`. It DOES carry an
applicability domain, and that domain is declared.

Phase 108's interpolation was EMPIRICAL: an n-ary directed construction
over measured points whose applicability domain is the convex hull and
whose warrant is an assumption about the world.

Same word, different warrant, different domain. The first is legitimate
because the solver constructed the interior; the second is not, because
nobody measured it. Neither output is evidence.

sec.15 SOLVING THE LORENZ SYSTEM ESTABLISHES A MATHEMATICAL TRAJECTORY
-----------------------------------------------------------------------
Not a physical observation. To claim "the physical system followed this
trajectory" would additionally require: that the equations model that
system, that p was measured rather than chosen, that u0 was the system's
actual state, and that the numerical error is smaller than the claim's
precision. Four separate claims, none supplied by `solve`.

sec.16 THE ATTACK, ANSWERED: (B)
---------------------------------
    solver -> numerical value -> Record.raw_content -> Observation -> Claim

diffeqpy supplies NO external warrant at the solver boundary. The answer
is (B): COMPUTATION PRODUCES A RESULT. Not evidence, and not even a
candidate observation -- there is no such object here. Phase 111's
conclusion is untouched, and Phase 115 already showed a GROMACS density
and a hand-typed density are the same string in a Record.

sec.17 NO VALIDATION IMPLICATION HOLDS
---------------------------------------
    solver convergence -> numerical accuracy   NO (a converged solution
        of the wrong equation converges)
    numerical accuracy -> model validity       NO
    model validity -> parameter validity       NO
    parameter validity -> empirical validation NO
    empirical validation -> causal validity    NO

Five arrows, five failures. `abstol`/`reltol` control the distance
between the computed and the exact solution OF THE STATED EQUATION, and
say nothing about the equation.

sec.18 "STATE" IS POLYSEMOUS ACROSS THREE LAYERS

                    ODE state u(t)      ModelState        EvidencePool
    identity        none; a value       content_hash      fingerprint
    semantics       physical/math       evidence summary  the world's record
    temporal        continuous t        POSITION, not t   append order
    mutability      mutated in place    frozen            append-only
    provenance      none                sample obs ids    the Phase 113 DAG
    transition      f, integrated       set union         admission
    uncertainty     solver tolerance    sample variance   none
    external warrant none               none              none (Phase 111)

Three different things sharing one word. Note the last row: none of the
three carries external warrant, which is why the boundary sits above all
of them.

sec.19 THE SEVEN PREREQUISITES, TESTED AGAINST OURS
-----------------------------------------------------
    1 state space exists            PRESENT -- ModelState
    2 temporal domain exists        ABSENT -- ModelStateTrajectory is
          indexed by `position`, an integer, never by a time
    3 transition rule exists        DEGENERATE -- set union
    4 parameterization              ABSENT
    5 initial/history conditions    ABSENT -- and DDE shows this rung must
          read "initial OR historical", since history is a function
    6 evolution operator defined    ABSENT -- appending is not an
          evolution operator over a state space
    7 trajectory semantics          PRESENT -- ModelStateTrajectory

Two of seven. All seven are genuinely required; DAE generalises #3 to
allow implicit form, DDE generalises #5. Calling this dynamical remains
unearned, and Phase 112b named the reason: append-only gives a
filtration.

sec.20 DYNAMICS IS NOT A NEW LAYER
-----------------------------------
Problem definition, execution, solution and analysis all sit inside Phase
109's OPERATION layer. They form a STRUCTURED SUBSYSTEM BELOW THE
EVIDENCE BOUNDARY, not a fifth layer beside it. The evidence boundary is
unchanged and unmoved.

sec.21 IS THERE A COMMON SIMULATION ABSTRACTION?
-------------------------------------------------
GROMACS, HOOMD-blue and diffeqpy do share
(initial state, transition rule, parameters, execution, trajectory) --
and the abstraction is TOO BROAD to be an ontology. GROMACS's transition
is a force field plus an integrator; HOOMD's is operations applied by a
device with a counter-based RNG; diffeqpy's is a user function plus a
chosen solver. "Parameters" means force-field constants, operation
settings, and `p` respectively -- the same non-common field Phase 110
already rejected.

sec.24 DID THE AUDIT EARN A NEW PRODUCTION ABSTRACTION?

NO. What was strengthened instead: the OPERATION/EVIDENCE boundary now
has a positive control showing exactly what a fully specified operation
layer contains -- and every one of its components (solver, tolerances,
seed, rank, history, initial condition) is something this architecture
deliberately does not have, because it does not execute anything.

Zero production changes.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from materials.model_state import ModelState, Sample, make_model_state, resolve_model_state_key
from materials.trajectory import ModelStateTrajectory, TrajectoryEntry
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("evidence", "retrieval", "materials", "experiment", "workbench", "scout")


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


# -- 19. the seven prerequisites --------------------------------------------------------------------


def test_prerequisite_1_a_state_space_exists():
    key = resolve_model_state_key("f", "p", {"t": 25})
    state = make_model_state({key: (Sample(value=90.0, observation_id="o1"),)})
    assert state.samples[key][0].value == 90.0


def test_prerequisite_2_no_temporal_domain_exists():
    """`ModelStateTrajectory` is indexed by POSITION -- an integer -- and
    never by a time. There is no tspan, no dt, no clock."""
    fields = {f.name for f in dataclasses.fields(TrajectoryEntry)}
    assert fields == {"position", "state", "state_id", "predecessor_state_id"}
    annotations = {f.name: str(f.type) for f in dataclasses.fields(TrajectoryEntry)}
    assert "int" in annotations["position"]
    for absent in ("t", "time", "tspan", "dt", "timestep"):
        assert absent not in fields


def test_prerequisite_3_the_transition_rule_is_degenerate():
    from materials.model_state import _transition
    doc = inspect.getdoc(_transition)
    assert "append exactly one" in doc


def test_prerequisite_4_no_parameterization_exists():
    from materials.model_state import predict
    source = inspect.getsource(predict)
    for absent in ("param", "theta", "coefficient", "p["):
        assert absent not in source.lower()


def test_prerequisite_5_no_initial_or_history_condition_exists():
    """DDE shows this rung must read "initial OR historical", since
    history is a function, not a point. Neither is present."""
    fields = {f.name for f in dataclasses.fields(ModelState)}
    for absent in ("u0", "initial", "history", "lag", "h"):
        assert absent not in fields


def test_prerequisite_6_no_evolution_operator_exists():
    """Appending is not an evolution operator over a state space."""
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    if node.name.lower() in {"evolve", "integrate", "step_forward",
                                             "propagate", "advance"}:
                        hits.append(f"{path.relative_to(REPO)}: {node.name}")
    assert hits == [], hits


def test_prerequisite_7_trajectory_semantics_exist():
    fields = {f.name for f in dataclasses.fields(ModelStateTrajectory)}
    assert "entries" in fields


# -- 1/8. the solver is not part of the problem -------------------------------------------------------


def test_no_solver_or_tolerance_concept_exists_here():
    """DifferentialEquations.jl separates the problem from the numerical
    method at the API level: solve(prob, Vern9(), abstol=...). Neither
    half has a counterpart here."""
    forbidden = {"solver", "abstol", "reltol", "saveat", "tolerance",
                 "integrator", "stepper"}
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                name = None
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    name = node.name.lower()
                elif isinstance(node, ast.arg):
                    name = node.arg.lower()
                if name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {name}")
    assert hits == [], hits


# -- 9/12. no stochastic realization axis -------------------------------------------------------------


def test_no_seed_or_realization_axis_exists():
    """HOOMD makes realization a pure function of
    (seed, timestep, particle id, MPI rank). None of the four is
    representable here."""
    forbidden = {"seed", "rng", "random_state", "realization", "sim_id", "repeat"}
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


def test_production_computation_is_deterministic_by_absence_not_by_seeding():
    """A counter-based PRNG is one way to be reproducible. Having no
    randomness at all is another, and it is the one taken here."""
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            text = path.read_text()
            for token in ("import random", "numpy.random", "np.random", "secrets."):
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert hits == [], hits


# -- 7. two operations sharing one word ----------------------------------------------------------------


def test_no_interpolation_of_either_kind_exists():
    """Solver dense output is warranted by error control within tspan;
    empirical interpolation is warranted by an assumption about the
    world. Neither is implemented."""
    from materials.model_state import predict

    class _Probe:
        formulation = type("R", (), {"id": "f"})()
        property = "p"
        target_context = {"t": 60}
        id = "probe"

    key = resolve_model_state_key("f", "p", {"t": 25})
    state = make_model_state({key: (Sample(value=90.0, observation_id="o1"),)})
    between = predict(state, _Probe())
    assert between.predicted_value is None
    assert between.sample_count == 0


# -- 15/16/17. the attack and the validation implications ----------------------------------------------


def test_no_convergence_or_validation_field_exists_anywhere():
    """Five implication arrows, five failures. Nothing records any of the
    five quantities."""
    forbidden = {"converged", "convergence", "tolerance_met", "validated",
                 "model_valid", "empirically_validated"}
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


def test_a_computed_trajectory_has_no_route_into_the_pool_as_itself():
    """Answer (B): computation produces a RESULT. There is no candidate
    observation object, and no put_* accepts a trajectory."""
    from evidence.pool import EvidencePool
    pool = EvidencePool()
    for absent in ("put_trajectory", "put_solution", "put_simulation", "put_state"):
        assert not hasattr(pool, absent)
    assert "id" not in {f.name for f in dataclasses.fields(TrajectoryEntry)}


# -- 18. "state" is polysemous ---------------------------------------------------------------------------


def test_the_three_states_differ_in_identity_temporality_and_mutability():
    from evidence.pool import EvidencePool

    # ModelState: content-addressed, frozen, position-indexed
    assert ModelState.__dataclass_params__.frozen
    assert "id" in {f.name for f in dataclasses.fields(ModelState)}

    # EvidencePool: not a dataclass, append-only, fingerprinted
    assert not dataclasses.is_dataclass(EvidencePool)
    assert hasattr(EvidencePool, "fingerprint")

    # an ODE state u(t) has no identity at all -- it is a mutated array.
    # Nothing here corresponds to it.


# -- 20/24. nothing was added -----------------------------------------------------------------------------


def test_phase_116_added_no_dynamics_machinery():
    forbidden = (
        "ODEProblem", "EnsembleProblem", "diffeqpy", "hoomd", "Dynamics",
        "TransitionRule", "InitialCondition", "Solver", "Interpolant",
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
