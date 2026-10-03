"""Phase 95: the cross-cell semantics gate.

Phase 92 locked the boundary from the workbench's side: no cross-candidate
relation is defined. Phase 95 asks the deeper question -- what WOULD make
one legitimate -- and finds the answer already written into the materials
layer, in a shape that says precisely what is missing.

THE ONE COMPARISON THE SYSTEM DEFINES
-------------------------------------
`materials.decision.evaluate_program` compares a cell against a
caller-supplied `Criterion` -- a plain (property, operator, target,
context) record. Not against another cell. Its shape is the precedent
any cross-cell comparison would have to follow:

  * the reference is DECLARED by the caller, never inferred
  * context is matched by subset containment, and a criterion matching
    more than one comparison group yields INCOMPARABLE rather than a
    guess
  * observed and predicted are answered SEPARATELY and, in the module's
    own words, "never combined"
  * INCOMPARABLE is a first-class outcome, not an error

`evaluate_program` maps over formulations independently. Nothing in it
relates one formulation to another.

WHAT IS MISSING FOR CELL-VS-CELL
--------------------------------
Exactly one thing, and it is a scientific concept rather than a
function: a DECLARED REFERENCE RELATION between two materials -- which
is the control and which the treatment, and what intervention separates
them. The repository contains no control, treatment, reference,
intervention, contrast, or experimental-factor concept anywhere, and
none of the six gap categories in `materials.experiment` concerns a
relationship between two formulations. The ontology never anticipated
it, so there is nothing to compose.

UNCERTAINTY (why B - A cannot be propagated)
--------------------------------------------
`predict` reports the POPULATION VARIANCE of the samples admitted to one
cell. That is a descriptive dispersion of measurements already taken --
not the standard error of an estimator, and the module states outright
that it "makes NO claim about what a NOT-YET-PERFORMED experiment will
produce." So the obstacle to propagating uncertainty through B - A is
not a missing independence assumption; it is that the quantity is not an
uncertainty OF AN ESTIMATE in the first place. Propagating it would
manufacture statistical structure the model has never claimed.
"""

import json
from pathlib import Path

import pytest

from materials.decision import (
    CONFLICTING_EVIDENCE, INCOMPARABLE, INSUFFICIENT_EVIDENCE, make_criterion,
)
from materials.experiment import ALL_GAP_CATEGORIES
from materials.model_state import resolve_model_state_key
from workbench import theme
from workbench.cli import dispatch
from workbench.interaction import WorkbenchState, bootstrap_research_scenario

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "polymer_tensile_strength.json"
REPO = Path(__file__).resolve().parent.parent


def _clock():
    n = {"i": 0}

    def clock() -> str:
        n["i"] += 1
        return f"2026-08-25T03:{n['i']:02d}:00Z"

    return clock


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


@pytest.fixture()
def state() -> WorkbenchState:
    with open(EXAMPLE, encoding="utf-8") as f:
        return bootstrap_research_scenario(json.load(f), clock=_clock())


def _cand(state: WorkbenchState, formulation: str, temperature: int):
    return next(
        c for c in state.list_candidates()
        if c.formulation.natural_key == formulation
        and dict(c.target_context) == {"temperature_c": temperature}
    )


# -- the cell ontology: four dimensions, never collapsed ---------------------------------------------


def test_a_cell_is_material_x_property_x_condition_at_a_model_state(state: WorkbenchState):
    """Identity dimensions are distinguishable and independent: changing
    any one of the three alone changes the cell."""
    baseline_25 = _cand(state, "baseline", 25)
    modified_25 = _cand(state, "modified", 25)
    baseline_120 = _cand(state, "baseline", 120)

    def key(c):
        return resolve_model_state_key(c.formulation.id, c.property, c.target_context)

    # material identity alone distinguishes a cell
    assert baseline_25.property == modified_25.property
    assert dict(baseline_25.target_context) == dict(modified_25.target_context)
    assert key(baseline_25) != key(modified_25)

    # experimental condition alone distinguishes a cell
    assert baseline_25.formulation.id == baseline_120.formulation.id
    assert key(baseline_25) != key(baseline_120)

    # and the model state is a FOURTH, separate dimension: the same cell
    # read at two states gives two predictions with one candidate identity
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    early, late = state.session.state_history[0], state.session.state
    a = state.prediction_at(baseline_25, early)
    b = state.prediction_at(baseline_25, late)
    assert a.candidate_id == b.candidate_id
    assert a.state_id != b.state_id


# -- the one defined comparison: cell vs DECLARED criterion -------------------------------------------


def test_the_systems_only_comparison_is_against_a_declared_reference(state: WorkbenchState):
    """A Criterion is a caller-supplied (property, operator, target,
    context) record. The reference is DECLARED, never inferred from the
    other cells present."""
    criterion = make_criterion(
        property="tensile_strength", operator=">=", target=80.0,
        context={"temperature_c": 25},
    )
    assert criterion.property == "tensile_strength"
    assert criterion.target == 80.0
    # the criterion names no formulation: it is a reference VALUE, not a
    # reference MATERIAL. Nothing in it can point at another cell.
    assert not hasattr(criterion, "formulation")
    assert not hasattr(criterion, "reference_formulation")


def test_incomparable_is_a_first_class_outcome(state: WorkbenchState):
    """The vocabulary for "these cannot be compared" already exists, and
    is returned rather than guessed past."""
    assert INCOMPARABLE == "INCOMPARABLE"
    assert INCOMPARABLE not in (CONFLICTING_EVIDENCE, INSUFFICIENT_EVIDENCE)


# -- observed and predicted are never merged (sec.6) --------------------------------------------------


def test_observed_and_predicted_verdicts_are_computed_separately():
    """This discipline runs through the whole stack -- analysis keeps
    separate comparison groups, experiment keeps a SideGap per side, and
    decision keeps observed_status/predicted_status "never combined".
    A cross-cell operation may not merge them either."""
    from materials.decision import PropertyDecision
    fields = set(PropertyDecision.__dataclass_fields__)
    assert {"observed_status", "predicted_status"} <= fields
    assert {"observed_group", "predicted_group"} <= fields
    # there is deliberately no combined verdict field
    assert not any("combined" in f or f == "status" for f in fields)

    from materials.experiment import EvidenceGap
    gap_fields = set(EvidenceGap.__dataclass_fields__)
    assert {"observed", "predicted"} <= gap_fields  # one SideGap per side


def test_an_observed_difference_is_not_a_predicted_difference(state: WorkbenchState):
    """A measured contrast between two materials and a model contrast
    between two cells are different claims. The system computes neither,
    and must not let one stand in for the other."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["70"])

    baseline, modified = _cand(state, "baseline", 25), _cand(state, "modified", 25)
    observed = [a.observed_value for a in state.assessments_for(baseline)]
    other_observed = [a.observed_value for a in state.assessments_for(modified)]
    assert observed == [80.0] and other_observed == [70.0]

    # the two observations exist and are numerically subtractable; the
    # system nonetheless provides no operation that pairs them, because
    # nothing declares them a matched pair rather than two unrelated
    # measurements of two different materials.
    assessments = state.assessments
    assert all(
        a.candidate_id in (baseline.id, modified.id) for a in assessments
    )
    assert len({a.candidate_id for a in assessments}) == 2
    # no assessment references another assessment or another candidate
    for assessment in assessments:
        for field in assessment.__dataclass_fields__:
            value = getattr(assessment, field)
            if isinstance(value, str) and field.endswith("_id"):
                assert value != (modified.id if assessment.candidate_id == baseline.id
                                 else baseline.id)


# -- uncertainty: what it is, and why it cannot be propagated (sec.7) --------------------------------


def test_uncertainty_is_a_sample_variance_of_admitted_samples(state: WorkbenchState):
    """Not a standard error, not a predictive interval. A dispersion of
    measurements already taken, within ONE cell.

    THE DIVISOR CHANGED, and this test changed with it. It previously
    pinned the divisor-n form and asserted the n-1 form was NOT what was
    returned. Divisor n is biased low by (n-1)/n -- half the true
    variance at n = 2 -- and that factor varies with n, so it did not
    cancel when ranking cells with different sample counts. See
    docs/NUMERICS.md."""
    dispatch(state, "select", ["baseline", "25"])
    candidate = state.selected_candidate
    dispatch(state, "observe", ["80"])
    assert state.session.predict(candidate).uncertainty is None  # one sample: undefined
    dispatch(state, "observe", ["100"])

    values = [80.0, 100.0]
    mean = sum(values) / len(values)
    sample_variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    assert state.session.predict(candidate).uncertainty == sample_variance
    # unbiased (n-1), not the maximum-likelihood plug-in (n) -- it
    # estimates the spread of the process, not of the values in hand
    population_variance = sum((v - mean) ** 2 for v in values) / len(values)
    assert state.session.predict(candidate).uncertainty != population_variance


def test_prediction_carries_no_field_that_could_support_propagation(state: WorkbenchState):
    """No standard error, no covariance, no degrees of freedom, no
    distribution family. Propagating B - A would require inventing all
    of them."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    prediction = state.session.predict(state.selected_candidate)
    fields = set(prediction.__dataclass_fields__)
    for absent in ("standard_error", "confidence", "covariance", "degrees_of_freedom",
                   "distribution", "interval", "posterior", "prior", "likelihood"):
        assert absent not in fields, f"Prediction unexpectedly carries {absent!r}"
    assert {"predicted_value", "uncertainty", "sample_count"} <= fields


def test_no_uncertainty_propagation_machinery_exists_anywhere():
    """A structural check: if a future phase adds propagation, it must be
    a deliberate scientific decision, not an incidental helper."""
    import re
    pattern = re.compile(
        r"\b(covarianc|propagate_uncertainty|standard_error|pooled_variance|"
        r"combine_variance|error_propagation)\w*", re.IGNORECASE)
    for package in ("materials", "experiment", "evidence", "retrieval", "workbench"):
        for path in (REPO / package).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            assert not pattern.search(source), f"{path}: uncertainty propagation appeared"


# -- the missing concept, named precisely (sec.4) -----------------------------------------------------


def test_no_control_treatment_or_reference_relation_exists():
    """The exact missing scientific concept. A cross-cell comparison
    needs a DECLARED reference relation between two materials -- which is
    control, which is treatment, and what intervention separates them.
    None of that vocabulary exists anywhere in the system."""
    import re
    pattern = re.compile(
        r"\b(control_group|treatment_group|reference_formulation|control_formulation|"
        r"baseline_formulation|experimental_factor|intervention|formulation_contrast|"
        r"paired_observation)\w*", re.IGNORECASE)
    for package in ("materials", "experiment", "evidence", "retrieval", "workbench"):
        for path in (REPO / package).rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            found = pattern.search(source)
            assert not found, f"{path}: {found.group(0)!r} -- the concept now exists; re-open Phase 95"


def test_no_gap_category_concerns_a_relationship_between_formulations():
    """The six gap categories describe one material's evidence. The
    ontology never anticipated a cross-formulation gap, so there is
    nothing to compose a cross-cell comparison from."""
    assert len(ALL_GAP_CATEGORIES) == 6
    for category in ALL_GAP_CATEGORIES:
        for word in ("FORMULATION", "MATERIAL", "CONTROL", "REFERENCE", "CONTRAST", "BETWEEN"):
            assert word not in category, category


# -- what remains valid ------------------------------------------------------------------------------


def test_same_cell_comparison_across_states_remains_valid(state: WorkbenchState):
    """The comparison the system DOES define between two predictions:
    one candidate, two model states."""
    dispatch(state, "select", ["baseline", "25"])
    candidate = state.selected_candidate
    dispatch(state, "observe", ["80"])
    dispatch(state, "observe", ["100"])

    delta = state.delta_between(
        state.prediction_at(candidate, state.session.state_history[1]),
        state.prediction_at(candidate, state.session.state),
    )
    assert delta.candidate_id == candidate.id
    assert delta.from_predicted_value == 80.0
    assert delta.to_predicted_value == 90.0
    assert delta.delta_predicted_value == 10.0  # signed


def test_whole_state_enumeration_remains_valid(state: WorkbenchState):
    """Enumeration needs no cross-cell relation, which is exactly why it
    was the only thing Phase 93 was allowed to build."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    text = dispatch(state, "state", [])
    assert text.count("├ prediction") == len(state.list_candidates())
    lowered = text.lower()
    for phrase in ("better", "worse", "difference", "delta", "contrast", "effect",
                   "relative", "versus", "ranking"):
        assert phrase not in lowered


def test_candidate_threads_remain_valid(state: WorkbenchState):
    """A thread projects the global chain through one cell -- no relation
    between cells is asserted, only attribution of evidence."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["70"])

    baseline_thread = dispatch(state, "thread", ["baseline", "25"])
    assert "EVIDENCE UNCHANGED" in baseline_thread
    assert "70.0" not in baseline_thread.split("─ PROJECTION ─")[1]


def test_ranking_remains_policy_only_and_stays_out_of_the_workbench():
    """`rank_candidates` orders caller-supplied utility. It is a
    decision-policy operation, and it is still composed by nothing."""
    import ast
    imported = set()
    for path in (REPO / "workbench").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("materials"):
                    imported.update(f"{node.module}.{a.name}" for a in node.names)
    assert not any("ranking" in name for name in imported)
    assert not any(name.endswith(".rank_candidates") for name in imported)
