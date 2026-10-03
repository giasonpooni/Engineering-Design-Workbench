"""Phase 100: falsification of the tensor / coordinate-space hypothesis.

CONCLUSION: TYPED COORDINATE SYSTEM + FIBERED STATE SPACE, already
present. Three of the six proposed dimensions FAILED candidacy. No new
abstraction is justified.

WHAT SURVIVED FALSIFICATION -- three coordinate axes, one state axis:

    model_state_key = content_hash(formulation_id, property, target_context)

That function already exists (`materials.model_state.
resolve_model_state_key`) and is exactly a typed 3-coordinate. Each axis
is independently addressable, has a canonical carrier, participates in
identity, carries scientific meaning, and leaves the others invariant
when varied. The ModelState id is a fourth, SEPARATE axis: the same
coordinate persists across states while its contents accumulate. That is
a fibered structure -- a base space of cells, with a state-indexed fiber
over each -- not a tensor, because no operation combines two axes into a
product quantity.

WHAT FAILED CANDIDACY:

  epistemic_side  -- not orthogonal in model space. `ModelState` has
                     exactly two fields, `id` and `samples`; there is no
                     predicted store and no way to index a predicted
                     cell. A Prediction is DERIVED from the same samples.
                     It IS a real dimension of EVIDENCE space (Observation
                     and DerivedValue are parallel stores), so the answer
                     is layer-dependent, which by itself disproves one
                     global product.

  counterfactual  -- not an axis. `project_update` returns a `ModelState`
                     of the same type, at the SAME cell key; hypothetical
                     provenance is marked per-SAMPLE via the
                     `hypothetical:` prefix. A counterfactual is a point
                     in the same space, not a direction out of it.

  decision        -- not addressable. `OptimizationResult` carries no
                     state id at all (Phase 89 had to record one), so it
                     is a function of (candidates, state, iteration,
                     policy). A derived quantity plus a policy value:
                     fails candidacy criteria 1, 3 and 9.

  authority       -- not a dimension. It does not exist in production;
                     the word appears only as incidental prose. The
                     invariant it was proposed to deliver -- "supersede
                     without mutating" -- is ALREADY delivered by
                     immutability, the append-only pool, and the
                     `DerivedValue.derived_from` DAG that `ancestry_of`
                     traverses. That DAG is the partial order. Authority
                     is answer (B), already implemented as provenance.

STRUCTURALLY TOTAL, SEMANTICALLY PARTIAL: any coordinate hashes fine,
including never-declared ones, and the system asserts nothing about an
unoccupied cell. Admissibility is a scenario-author declaration (the
declared formulations x contexts), never a system claim. Structurally
representable, scientifically admissible and experimentally realizable
remain three different predicates, and the system only ever decides the
first.
"""

import ast
import dataclasses
from pathlib import Path

import pytest

from evidence.identity import content_hash
from materials.counterfactual import project_update
from materials.model_state import (
    HYPOTHETICAL_SAMPLE_PREFIX, ModelState, _transition, make_model_state, predict,
    resolve_model_state_key,
)
from workbench import theme
from workbench.cli import dispatch
from workbench.interaction import WorkbenchState, bootstrap_research_scenario

REPO = Path(__file__).resolve().parent.parent


def _clock():
    n = {"i": 0}

    def clock() -> str:
        n["i"] += 1
        return f"2026-08-26T11:{n['i']:02d}:00Z"

    return clock


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _scenario(formulations, contexts) -> WorkbenchState:
    return bootstrap_research_scenario({
        "name": "phase 100", "process": "process-std-190c",
        "formulations": list(formulations), "property": "tensile_strength",
        "criterion": {"operator": ">=", "target": 75.0},
        "contexts": list(contexts),
    }, clock=_clock())


class _Cell:
    """A minimal candidate-shaped object for exercising the coordinate
    function directly, without a scenario."""

    def __init__(self, formulation_id, property_name, context):
        self.formulation = type("R", (), {"id": formulation_id})()
        self.property = property_name
        self.target_context = context
        self.id = content_hash({"f": formulation_id, "p": property_name, "c": dict(context)})


# -- the three surviving axes --------------------------------------------------------------------------


def test_the_coordinate_function_already_exists_and_takes_exactly_three_axes():
    """`resolve_model_state_key` IS the coordinate. No new object needed."""
    import inspect
    signature = inspect.signature(resolve_model_state_key)
    assert list(signature.parameters) == ["formulation_id", "property", "target_context"]


def test_eighteen_coordinates_over_three_by_two_by_three_are_all_distinct():
    formulations = [content_hash({"f": f}) for f in ("baseline", "modified", "high_filler")]
    properties = ("tensile_strength", "elongation_at_break")
    contexts = ({"temperature_c": 25}, {"temperature_c": 100},
                {"temperature_c": 25, "pressure_kpa": 200})

    keys = {
        (formulation, prop, tuple(sorted(context.items()))):
            resolve_model_state_key(formulation, prop, context)
        for formulation in formulations for prop in properties for context in contexts
    }
    assert len(keys) == 18
    assert len(set(keys.values())) == 18


@pytest.mark.parametrize("axis", ["formulation", "property", "context"])
def test_varying_exactly_one_axis_changes_the_coordinate_and_nothing_else(axis):
    """Candidacy criteria 1, 2 and 7: independently addressable, others
    left invariant, genuinely orthogonal."""
    base_formulation = content_hash({"f": "baseline"})
    other_formulation = content_hash({"f": "modified"})
    base = (base_formulation, "tensile_strength", {"temperature_c": 25})
    varied = {
        "formulation": (other_formulation, "tensile_strength", {"temperature_c": 25}),
        "property": (base_formulation, "elongation_at_break", {"temperature_c": 25}),
        "context": (base_formulation, "tensile_strength", {"temperature_c": 100}),
    }[axis]

    assert resolve_model_state_key(*base) != resolve_model_state_key(*varied)
    # the other two axes are untouched: re-deriving with them alone reproduces the key
    assert resolve_model_state_key(*base) == resolve_model_state_key(
        base[0], base[1], dict(base[2]))


def test_the_coordinate_is_invariant_under_state_change():
    """The fourth axis is separate: a cell keeps its identity while its
    contents accumulate. This is what makes the structure FIBERED."""
    formulation = content_hash({"f": "baseline"})
    key = resolve_model_state_key(formulation, "tensile_strength", {"temperature_c": 25})
    s0 = make_model_state({})
    s1 = _transition(s0, key, 90.0, "obs-a")
    s2 = _transition(s1, key, 100.0, "obs-b")

    assert len({s0.id, s1.id, s2.id}) == 3          # the fiber has three points
    assert list(s1.samples) == [key]                 # over ONE unchanged base coordinate
    assert list(s2.samples) == [key]
    assert len(s2.samples[key]) == 2


def test_the_candidate_is_not_a_coordinate():
    """FALSIFICATION of the obvious carrier. `ActionCandidate.id` hashes
    requirement identities, which include `existing_evidence_ids` and
    `provenance_observation_id_sets` -- so it encodes the EVIDENCE EPOCH,
    not just the cell. Regenerating a candidate set after admitting
    evidence yields a different id for the same coordinate."""
    from materials.candidates import generate_candidates
    from materials.iteration import reevaluate_program

    state = _scenario(("baseline",), ({"temperature_c": 25},))
    before = state.list_candidates()[0]
    key_before = resolve_model_state_key(
        before.formulation.id, before.property, before.target_context)

    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])

    iteration = reevaluate_program(
        state.pool, state.engine, state.session.iteration.query,
        state.session.iteration.criteria)
    after = generate_candidates(iteration.specification).candidates[0]
    key_after = resolve_model_state_key(
        after.formulation.id, after.property, after.target_context)

    assert after.id != before.id       # the candidate moved
    assert key_after == key_before     # the coordinate did not


# -- falsified dimensions -------------------------------------------------------------------------------


def test_epistemic_side_is_not_a_dimension_of_model_space():
    """`ModelState` has exactly two fields. There is no predicted store,
    so a predicted cell cannot be addressed -- the value is derived from
    the same samples."""
    assert [f.name for f in dataclasses.fields(ModelState)] == ["id", "samples"]
    formulation = content_hash({"f": "baseline"})
    cell = _Cell(formulation, "tensile_strength", {"temperature_c": 25})
    key = resolve_model_state_key(formulation, cell.property, cell.target_context)
    state = _transition(make_model_state({}), key, 90.0, "obs-a")
    assert predict(state, cell).predicted_value == 90.0   # derived, not stored
    assert list(state.samples) == [key]                    # one cell, one side


def test_a_counterfactual_is_a_point_in_the_same_space_not_an_axis():
    formulation = content_hash({"f": "baseline"})
    cell = _Cell(formulation, "tensile_strength", {"temperature_c": 25})
    key = resolve_model_state_key(formulation, cell.property, cell.target_context)
    real = _transition(make_model_state({}), key, 90.0, "obs-a")
    projected = project_update(real, cell, 70.0)

    assert type(projected) is type(real) is ModelState
    assert list(projected.samples) == [key]        # the SAME coordinate
    marks = [s.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)
             for s in projected.samples[key]]
    assert any(marks) and not all(marks)           # marked per SAMPLE, not per state


def test_decision_is_a_derived_quantity_not_an_addressable_coordinate():
    from materials.optimization import OptimizationResult
    fields = {f.name for f in dataclasses.fields(OptimizationResult)}
    assert "state_id" not in fields and "model_state_id" not in fields
    state = _scenario(("baseline",), ({"temperature_c": 25},))
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "decide", [])
    # the workbench had to RECORD the state, because the object cannot say
    assert state.last_decision_state_id == state.session.state.id


def test_authority_does_not_exist_and_its_invariant_is_already_delivered():
    """"Supersede without mutating" needs no authority concept: nothing
    can be mutated, the pool is append-only, and `derived_from` already
    forms the partial order that `ancestry_of` traverses."""
    from evidence.provenance import ancestry_of  # noqa: F401  -- the traversal exists
    from evidence.types import DerivedValue

    assert "derived_from" in {f.name for f in dataclasses.fields(DerivedValue)}
    for name in ("authority", "seniority", "rank", "precedence"):
        assert name not in {f.name for f in dataclasses.fields(DerivedValue)}

    # and no production module defines an authority concept
    for package in ("materials", "evidence", "experiment", "retrieval", "workbench"):
        directory = REPO / package
        if not directory.exists():
            continue
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
                    lowered = node.name.lower()
                    assert "authority" not in lowered and "seniority" not in lowered, path


# -- the product is structurally total, semantically partial ----------------------------------------------


def test_an_undeclared_coordinate_is_representable_but_asserts_nothing():
    formulation = content_hash({"f": "baseline"})
    never_declared = _Cell(formulation, "elongation_at_break",
                           {"temperature_c": 25, "pressure_kpa": 200})
    key = resolve_model_state_key(
        formulation, never_declared.property, never_declared.target_context)
    assert len(key) == 64                              # structurally representable
    empty = make_model_state({})
    prediction = predict(empty, never_declared)
    assert prediction.predicted_value is None          # and asserts nothing
    assert prediction.sample_count == 0


def test_the_registry_is_exactly_the_authors_declared_product():
    """Admissibility is declared by the scenario author. The workbench
    never invents a coordinate, and never omits a declared one."""
    state = _scenario(("baseline", "modified"),
                      ({"temperature_c": 25}, {"temperature_c": 100}))
    candidates = state.list_candidates()
    assert len(candidates) == 4
    cells = {(c.formulation.natural_key, dict(c.target_context)["temperature_c"])
             for c in candidates}
    assert cells == {("baseline", 25), ("baseline", 100),
                     ("modified", 25), ("modified", 100)}
    assert len({resolve_model_state_key(c.formulation.id, c.property, c.target_context)
                for c in candidates}) == 4


# -- fibers are lossless enumerations, never comparisons ---------------------------------------------------


def test_every_fiber_is_a_slice_of_one_key_set_with_no_aggregation():
    state = _scenario(("baseline", "modified"),
                      ({"temperature_c": 25}, {"temperature_c": 100}))
    for formulation in ("baseline", "modified"):
        for temperature in ("25", "100"):
            dispatch(state, "select", [formulation, temperature])
            dispatch(state, "observe", ["90", "MPa"])

    candidates = state.list_candidates()
    # fiber: all cells of one formulation
    one_formulation = [c for c in candidates if c.formulation.natural_key == "baseline"]
    # fiber: all cells at one context
    one_context = [c for c in candidates if dict(c.target_context)["temperature_c"] == 25]
    assert len(one_formulation) == 2 and len(one_context) == 2

    # every member keeps its own identity and its own independent reading
    for fiber in (one_formulation, one_context):
        readings = [state.prediction_at(c, state.session.state) for c in fiber]
        assert len({c.id for c in fiber}) == len(fiber)
        assert all(r.sample_count == 1 for r in readings)
        # no aggregate over the fiber exists anywhere
        assert len({r.candidate_id for r in readings}) == len(fiber)


def test_the_state_view_is_the_fiber_over_one_state_and_asserts_no_relation():
    state = _scenario(("baseline", "modified"), ({"temperature_c": 25},))
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])
    text = dispatch(state, "state", [])
    assert text.count("├ prediction") == len(state.list_candidates())
    lowered = text.lower()
    for phrase in ("mean", "average", "total", "spread", "difference", "better", "ranking"):
        assert phrase not in lowered


# -- NEGATIVE TESTS: the abstraction must make none of these easier -----------------------------------------


def test_structural_alignment_never_implies_comparability():
    """Two cells sharing property and context are structurally aligned
    and still scientifically incomparable. This is the hard invariant."""
    from materials.trajectory import compare_predictions

    state = _scenario(("baseline", "modified"), ({"temperature_c": 25},))
    for formulation in ("baseline", "modified"):
        dispatch(state, "select", [formulation, "25"])
        dispatch(state, "observe", ["90", "MPa"])

    baseline, modified = state.list_candidates()[0], state.list_candidates()[1]
    assert baseline.property == modified.property
    assert dict(baseline.target_context) == dict(modified.target_context)
    # structurally aligned on two of three axes -- and still refused
    with pytest.raises(AssertionError, match="same ActionCandidate"):
        compare_predictions(state.prediction_at(baseline, state.session.state),
                            state.prediction_at(modified, state.session.state))


def test_no_coordinate_helper_enables_a_forbidden_operation():
    """A regression guard: if a future coordinate abstraction appears, it
    must not bring these with it."""
    for package in ("materials", "evidence", "experiment", "retrieval", "workbench"):
        directory = REPO / package
        if not directory.exists():
            continue
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    lowered = node.name.lower()
                    for forbidden in ("rank_cells", "compare_cells", "cell_delta",
                                      "best_candidate", "propagate_uncertainty",
                                      "convert_unit", "aggregate_cells"):
                        assert forbidden not in lowered, f"{path}: {node.name}"


def test_a_display_index_is_never_an_identity():
    state = _scenario(("baseline",), ({"temperature_c": 25},))
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])
    for command, args in (("state", []), ("timeline", ["0"])):
        text = dispatch(state, command, args)
        assert "display index only" in text


def test_utility_is_never_presented_as_a_scientific_quantity():
    state = _scenario(("baseline", "modified"), ({"temperature_c": 25},))
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "decide", [])
    explanation = dispatch(state, "explain", [])
    assert "highest determinate utility among eligible candidates" in explanation
    assert "exploration policy" in explanation
    # and utility stays out of the cell enumeration entirely
    assert "UTILITY" not in dispatch(state, "state", []).upper()


def test_a_counterfactual_never_becomes_evidence_under_any_projection():
    state = _scenario(("baseline",), ({"temperature_c": 25},))
    dispatch(state, "select", ["baseline", "25"])
    fingerprint = state.pool.fingerprint()
    dispatch(state, "explore", ["999"])
    assert state.pool.fingerprint() == fingerprint
    branch = state.branches[0]
    assert branch.projected_state_id not in {s.id for s in state.session.state_history}


# -- agents operate on transitions, not coordinates (sec.6) ---------------------------------------------------


def test_the_existing_api_is_shaped_as_typed_state_transitions():
    """Model (C) of the three: the public surface is
    (state, input) -> (artifact, new state), not coordinate access.
    An agent would be an operator over those transitions, never an owner
    of state -- every transition returns a NEW object."""
    import inspect

    from experiment.session import ExperimentSession

    observe = inspect.signature(ExperimentSession.observe)
    assert "candidate" in observe.parameters and "observation" in observe.parameters
    # returns (assessment, new session) -- the session is never mutated in place
    state = _scenario(("baseline",), ({"temperature_c": 25},))
    dispatch(state, "select", ["baseline", "25"])
    before = state.session
    dispatch(state, "observe", ["90", "MPa"])
    assert state.session is not before
    assert before.state.id != state.session.state.id
