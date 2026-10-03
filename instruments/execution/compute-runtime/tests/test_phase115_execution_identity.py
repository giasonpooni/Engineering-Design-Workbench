"""Phase 115: scientific computation / execution identity audit.

Comparative control: GROMACS (287 MB, cloned; source traced, not README).

sec.1/sec.3 WHAT A MATURE SCIENTIFIC-COMPUTING SYSTEM ACTUALLY RECORDS
-----------------------------------------------------------------------
GROMACS keeps SCIENTIFIC STATE and EXECUTION IDENTITY in two different
structures, in two different files.

`src/gromacs/mdtypes/state.h::t_state` is the dynamical state:
positions, velocities, `box`, `boxv`, `pres_prev`, `svir_prev`,
`fvir_prev`, temperature-coupling groups, `fep_state`, `lambda`. Note
`*_prev`: the state carries PREVIOUS-STEP terms BECAUSE THE INTEGRATOR
NEEDS THEM. State sufficiency is determined by the transition rule, not
by intuition about what a state "should" contain.

`src/gromacs/fileio/checkpoint.h::CheckpointHeaderContents` is execution
identity, and it records precisely what this architecture does not:

    version            the GROMACS version string
    fprog              the generating program
    ftime              generation time
    double_prec        numerical precision
    eIntegrator        which integrator
    simulation_part,
      step, t          position in the trajectory
    nnodes, dd_nc, npme the parallel decomposition
    btime_UNUSED,
      buser_UNUSED,
      bhost_UNUSED     DEPRECATED

Two findings follow directly.

FIRST: `nnodes`/`dd_nc`/`npme` ARE recorded. The parallel decomposition
is part of execution identity because it CHANGES THE NUMBERS --
floating-point summation order depends on how the domain is split. So
sec.3's case C (same executable, different MPI/thread configuration) is
represented, and represented because it is known to matter.

SECOND, and sharper: `buser` and `bhost` are DEPRECATED. A mature
scientific computing system recorded WHO ran it and WHERE, and then
REMOVED both. Who ran a simulation is not part of what makes its result
reproducible. That is Phase 105's authority-is-not-truth finding,
arrived at independently by a molecular dynamics code.

And `checkpoint.cpp:2578` calls
`check_string(fplog, "Version", gmx_version(), headerContents.version,
&versionDiffers)` -- on restart the running version is COMPARED against
the recorded one and a difference is reported. Execution identity is not
merely recorded there; it is checked.

sec.3 IS EXECUTION IDENTITY THE SAME AS RESULT IDENTITY? NO.
-------------------------------------------------------------
    A same executable + same inputs + same parameters   same execution id,
                                                        and results may
                                                        still differ by
                                                        thread scheduling
    B different hardware                                different execution,
                                                        possibly same result
    C different MPI/thread configuration                RECORDED, changes
                                                        summation order
    D different executable version                      RECORDED and CHECKED
    E different force field                             different INPUT, not
                                                        a different execution
    F different random seed                             different trajectory,
                                                        same model

The map from execution identity to result identity is neither injective
(B) nor a function (A). They are independent axes, and GROMACS treats
them as such by storing them in different structures.

sec.4 WHAT REPRODUCIBILITY ACTUALLY IS
---------------------------------------
NOT content identity, NOT execution identity, but A RELATION BETWEEN
EXECUTION CONDITIONS AND OUTPUTS. `hash(output_a) == hash(output_b)` is
neither necessary (a correct rerun may differ in the last bits) nor
sufficient (identical outputs can arise from different computations --
Phase 111b's World A / World B, one layer down). GROMACS's checkpoint
comparison is a relation over recorded conditions, which is why it warns
rather than asserting equality.

sec.11 WHERE THE ANALOGY TO ModelState STOPS
---------------------------------------------
    GROMACS            here
    t_state            ModelState
    x(t) -> x(t+dt)    S_t -> S_(t+1)
    F = forces/integrator   `update` = append one Sample
    dt, integrator, thermostat   NONE
    trajectory         ModelStateTrajectory

The analogy holds for exactly one step and then breaks completely.
GROMACS's transition is a NUMERICAL INTEGRATION of a physical law with a
timestep, a thermostat and a barostat. Ours is set union. Phase 112b
named this: append-only gives a FILTRATION, not dynamics. `ModelState`
is an immutable evidence-indexed state SUMMARY, and calling it dynamical
would be unearned.

sec.12 WHY x,y,z IS DIFFERENT FROM target_context["temperature_c"]
-------------------------------------------------------------------
Both are numbers. The molecular coordinate additionally has: a vector
space it lives in, a metric on that space, periodic boundary conditions
declared in `box`, a topology declaring which atoms are bonded, and a
force field assigning an energy to every configuration. The context
coordinate has NONE of these -- Phases 104 and 106 established that it
has no order, no difference and no metric unless externally declared.

The difference is not the numbers. It is that GROMACS SUPPLIES THE
STRUCTURE and the context coordinate does not.

sec.13 WHERE GEOMETRY IS LEGITIMATE
------------------------------------
GROMACS earns Euclidean distance, neighbourhood, gradient and force
because `box` declares the metric and the boundary conditions, the
topology declares adjacency, and the force field declares a scalar field
whose gradient IS the force. Every prerequisite Phases 106-110 found
missing from `target_context` is present here, explicitly, as data.

sec.17/sec.18 THE FIREWALL, RETESTED
-------------------------------------
    executable output != scientific observation != evidence != truth

All three inequalities survive, and GROMACS supplies NO external warrant
at the solver boundary. A density of 1.02 g/cm3 computed by mdrun and a
1.02 typed by hand are, at the point of admission, the same string in a
Record's `raw_content`. The only difference the architecture can encode
is the declared `extraction_method` -- and `simulation:` is already a
recognised prefix, unenforced. Phase 111's conclusion stands untouched.

sec.18 THE INDEPENDENT AXES, CONFIRMED

    evidence identity       EXISTS
    observation identity    EXISTS (a function of the above)
    execution identity      ABSENT
    executable identity     ABSENT
    model identity          ABSENT (there is one model)
    result identity         EXISTS as ExperimentalResult

sec.20 THE TEN TARGETS

  1 scientific computation is distinct from evidence   SURVIVES
  2 execution identity != evidence identity            SURVIVES VACUOUSLY
  3 executable identity != model identity              SURVIVES VACUOUSLY
  4 workflow dependency != provenance                  SURVIVES (Phase 114)
  5 simulation dynamics != ModelState                  SURVIVES -- filtration
  6 numerical output != scientific observation         SURVIVES for objects,
                                                       FALSIFIED for values
  7 successful execution is not validation             SURVIVES -- GROMACS
        checks convergence, never physical validity
  8 GROMACS has genuine geometry/dynamics that we
    do not                                             SURVIVES -- and the
        reason is supplied structure, not sophistication
  9 reproducibility is a relation over execution
    conditions, not output identity                    SURVIVES
 10 an execution boundary is needed before an agent
    can be represented                                 SURVIVES -- Phase 114
        found that boundary specified and empty

FINAL CLASSIFICATION
    evidence identity, observation identity, result identity   EXISTING
    execution boundary                                         PARTIAL
    execution identity, executable identity, environment       ABSENT
    dynamics, geometry, metric on a coordinate                 ABSENT
    reproducibility relation                                   RESEARCH-ONLY
    "ModelState is a dynamical state"                          FALSE ANALOGY

NO PRODUCTION ABSTRACTION HAS BEEN EARNED. Zero production changes.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from evidence.types import Observation
from experiment.interface import DispatchedMeasurement
from materials.model_state import ModelState, Sample, make_model_state, resolve_model_state_key
from materials.results import ExperimentalResult
from retrieval.epistemic import SIMULATED, classify_epistemic_status
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("evidence", "retrieval", "materials", "experiment", "workbench", "scout")
TIMESTAMP = "2026-01-01T00:00:00Z"


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


# -- 3/10. execution identity is absent, field by field ----------------------------------------------


GROMACS_EXECUTION_FIELDS = {
    "version": "the executable's version string",
    "fprog": "the generating program",
    "double_prec": "numerical precision",
    "eIntegrator": "which integrator",
    "nnodes": "parallel rank count",
    "dd_nc": "domain decomposition grid",
    "npme": "separate PME rank count",
}


@pytest.mark.parametrize("field", sorted(GROMACS_EXECUTION_FIELDS))
def test_no_production_object_records_this_execution_field(field):
    """GROMACS records all seven. Here none has a counterpart."""
    aliases = {
        "version": ("version", "code_version", "software_version"),
        "fprog": ("program", "executable", "generator"),
        "double_prec": ("precision", "dtype", "float_width"),
        "eIntegrator": ("integrator", "solver", "method_impl"),
        "nnodes": ("nnodes", "ranks", "n_workers", "parallelism"),
        "dd_nc": ("decomposition", "grid", "partition"),
        "npme": ("npme", "pme_ranks"),
    }[field]
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
                                and stmt.target.id in aliases):
                            hits.append(f"{path.relative_to(REPO)}: {node.name}.{stmt.target.id}")
    assert hits == [], hits


def test_two_runs_differing_only_in_environment_would_be_indistinguishable():
    """`DispatchedMeasurement` carries nothing about how it was produced
    except a self-declared method string."""
    fields = {f.name for f in dataclasses.fields(DispatchedMeasurement)}
    assert fields == {"content", "record_locator", "record_raw_content",
                      "extracted_at", "extraction_method"}
    for absent in ("environment", "host", "version", "precision", "ranks"):
        assert absent not in fields


def test_result_identity_exists_and_execution_identity_does_not():
    fields = {f.name for f in dataclasses.fields(ExperimentalResult)}
    assert "id" in fields                                  # result identity
    assert "record_id" in fields                           # its evidence anchor
    for absent in ("execution_id", "executable_id", "run_id", "environment_id"):
        assert absent not in fields


# -- 11. where the analogy to ModelState stops -------------------------------------------------------


def test_the_transition_rule_has_no_timestep_integrator_or_parameters():
    """GROMACS: numerical integration of a physical law. Here: set union."""
    from materials.model_state import _transition, update
    source = inspect.getsource(_transition)
    for absent in ("dt", "timestep", "integrat", "thermostat", "barostat", "force"):
        assert absent not in source.lower()
    assert "append exactly one" in inspect.getdoc(_transition)
    assert set(inspect.signature(update).parameters) == {
        "state", "candidate", "result", "observation"}


def test_model_state_carries_no_previous_step_terms():
    """GROMACS's t_state carries pres_prev/svir_prev/fvir_prev BECAUSE the
    integrator needs them -- state sufficiency is set by the transition
    rule. Ours needs nothing, because appending needs nothing."""
    assert {f.name for f in dataclasses.fields(ModelState)} == {"id", "samples"}
    assert {f.name for f in dataclasses.fields(Sample)} == {"value", "observation_id"}


def test_the_state_transition_is_monotone_and_therefore_a_filtration():
    key = resolve_model_state_key("f", "p", {"t": 25})
    before = make_model_state({key: (Sample(value=90.0, observation_id="o1"),)})
    after = make_model_state({key: (
        Sample(value=90.0, observation_id="o1"),
        Sample(value=92.0, observation_id="o2"))})
    assert set(before.samples[key]) < set(after.samples[key])
    # No state can decrease, oscillate, or be transformed.


# -- 12/13. why molecular coordinates differ from context coordinates ---------------------------------


def test_no_box_topology_or_force_field_declares_structure_over_a_context():
    """GROMACS earns distance, neighbourhood and gradient because `box`
    declares the metric and boundary conditions, the topology declares
    adjacency, and the force field declares a scalar field. None of the
    three has any counterpart here."""
    forbidden = {"box", "topology", "force_field", "periodic", "neighbour_list",
                 "neighbor_list", "gradient", "potential_energy"}
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
                elif isinstance(node, ast.Attribute):
                    name = node.attr.lower()
                if name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {name}")
    assert hits == [], hits


def test_a_context_coordinate_is_a_bare_object_with_no_declared_structure():
    from materials.candidates import ActionCandidate
    assert ActionCandidate.__annotations__["target_context"] == "Mapping[str, object]"


# -- 17. the firewall, retested with a simulation ------------------------------------------------------


def test_a_simulated_value_and_a_typed_value_differ_only_by_a_declared_string():
    from evidence.types import make_observation

    def observation(method):
        return make_observation(
            record_ids=("r",), extraction_method=method,
            content={"property": "density", "value": 1.02, "unit": "g_per_cm3"},
            confidence=1.0, extracted_at=TIMESTAMP)

    simulated = observation("simulation:gromacs_2024")
    transcribed = observation("human_transcription")
    assert classify_epistemic_status(simulated) == SIMULATED
    assert simulated.id != transcribed.id       # the METHOD is identity-bearing
    # ...but the method is a self-report, and nothing checks it. Same content,
    # same record, and only the caller's declaration separates them.
    assert simulated.content == transcribed.content


def test_the_only_numeric_field_on_an_observation_is_the_content_itself():
    fields = {f.name for f in dataclasses.fields(Observation)}
    assert fields == {"id", "record_ids", "extraction_method", "content",
                      "confidence", "extracted_at"}
    for absent in ("convergence", "residual", "tolerance", "validated"):
        assert absent not in fields


# -- 4/19. reproducibility is a relation, not a hash ----------------------------------------------------


def test_nothing_expresses_a_reproducibility_relation():
    forbidden = {"reproducible", "reproduces", "same_execution", "rerun_of"}
    hits = []
    for package in PRODUCTION:
        root = REPO / package
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name.lower() in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {node.name}")
    assert hits == [], hits


def test_equal_output_hashes_do_not_establish_equal_computations():
    """Phase 111b's World A / World B, one layer down: two different
    computations yielding the same bytes produce the same object."""
    key = resolve_model_state_key("f", "p", {"t": 25})
    from_simulation = make_model_state(
        {key: (Sample(value=1.02, observation_id="obs-x"),)})
    from_measurement = make_model_state(
        {key: (Sample(value=1.02, observation_id="obs-x"),)})
    assert from_simulation.id == from_measurement.id


# -- 20. nothing was added ------------------------------------------------------------------------------


def test_phase_115_added_no_simulation_machinery():
    forbidden = (
        "gromacs", "GROMACS", "mdrun", "CheckpointHeader", "Integrator",
        "ExecutionIdentity", "ReproducibilityRelation", "ForceField",
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
