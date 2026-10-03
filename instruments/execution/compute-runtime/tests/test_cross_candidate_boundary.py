"""Phase 92: semantic lock on the cross-candidate boundary.

Phases 89, 90 and 91 each independently reached the same wall: there is
no defined operation between two DIFFERENT candidate cells occupying the
same global state. This module records what the investigation found and
locks it, so a later phase cannot quietly manufacture the missing
relation by noticing that two numbers happen to be available.

WHAT THE ALGEBRA ACTUALLY DEFINES
---------------------------------
DEFINED, at the DECISION layer, over caller-supplied utility only:

  materials.ranking.rank_candidates(utility_set, policy)
      A total ordering of candidates by `CandidateUtility.utility`,
      ties broken by ActionCandidate.id. Its own docstring is explicit
      that a rank number under RANKED_LAST reflects "placed last by
      policy," never "determined to be worse than rank N-1."

  materials.optimization.optimize_candidates(utility_set, policy)
      Which SUBSET maximizes summed utility under a count constraint.
      Its own docstring: "The optimizer never claims its result is
      scientifically optimal. It is optimal only with respect to the
      caller-supplied `utility` values and `OptimizationPolicy`."

  Utility itself is `benefit - cost`, BOTH caller-supplied, in whatever
  units the caller's judgment uses. It is a decision quantity. It is
  comparable across candidates only because one caller supplied all of
  them on one convention -- which in this workbench is
  `interaction._utility_input_for`, an explicit exploration policy.

NOT DEFINED, at the MATERIALS layer:

  Any relation between two candidates' PREDICTIONS, UNCERTAINTIES or
  INFORMATION VALUES. Every comparison primitive in the algebra guards
  on candidate identity and refuses a mixed pair:

    materials.trajectory.compare_predictions   same candidate_id
    materials.assessment.assess                same candidate_id
    materials.ensemble.make_counterfactual_set same candidate_id

  And `materials.analysis` -- which is where this project already
  settled the question of when two values are comparable at all
  (its own "Phase 29 COMPARABILITY" section) -- resolves exactly ONE
  Referent and groups by `_comparison_context` within it. Two
  formulations are two Referents. The system has never treated them as
  measurements of one quantity, and `resolve_model_state_key` puts
  `formulation.id` in the cell key, so they are different cells by
  construction.

THE CANDIDATE-CELL SEMANTIC
---------------------------
    (candidate, property, context, model_state) -> Prediction

is a reading of ONE cell. Two candidates differing in formulation are
TWO INDEPENDENTLY PREDICTED QUANTITIES about two different materials --
not one scientific quantity under two conditions. Their predictions
share a unit; that is numerical compatibility, not comparability.

WHAT IS THEREFORE SAFE TO BUILD
-------------------------------
Lossless ENUMERATION only: every candidate cell of a state, side by
side, in the registry's existing id-sorted order, with no difference,
ordering-by-value, or aggregate computed between them. That is Outcome
B of the phase's own three outcomes, and this module proves the two
facts it depends on -- losslessness and a pre-existing authoritative
ordering.
"""

import json
from pathlib import Path

import pytest

from materials.assessment import assess
from materials.ensemble import make_counterfactual_set
from materials.model_state import resolve_model_state_key
from materials.optimization import optimize_candidates
from materials.ranking import (
    ASCENDING, DESCENDING, RANKED_LAST, UNRANKED, RankingPolicy, rank_candidates,
)
from materials.trajectory import compare_predictions
from workbench import theme
from workbench.cli import dispatch
from workbench.interaction import DECISION_POLICY, WorkbenchState, bootstrap_research_scenario

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "polymer_tensile_strength.json"


def _clock():
    n = {"i": 0}

    def clock() -> str:
        n["i"] += 1
        return f"2026-08-24T21:{n['i']:02d}:00Z"

    return clock


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _start() -> WorkbenchState:
    with open(EXAMPLE, encoding="utf-8") as f:
        return bootstrap_research_scenario(json.load(f), clock=_clock())


@pytest.fixture()
def state() -> WorkbenchState:
    return _start()


def _multi(state: WorkbenchState) -> WorkbenchState:
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["70"])
    dispatch(state, "select", ["high_filler", "120"])
    dispatch(state, "observe", ["55"])
    return state


def _cand(state: WorkbenchState, formulation: str, temperature: int):
    return next(
        c for c in state.list_candidates()
        if c.formulation.natural_key == formulation
        and dict(c.target_context) == {"temperature_c": temperature}
    )


# -- B. prediction difference: NOT DEFINED -----------------------------------------------------------


def test_compare_predictions_refuses_two_different_candidates(state: WorkbenchState):
    """The only prediction-difference primitive in the algebra requires
    one candidate. Two formulations are not two readings of one
    quantity, and this is the guard that says so."""
    _multi(state)
    baseline = _cand(state, "baseline", 25)
    modified = _cand(state, "modified", 25)
    current = state.session.state

    a = state.prediction_at(baseline, current)
    b = state.prediction_at(modified, current)
    # both are numerically available -- 80.0 and 70.0, same unit
    assert a.predicted_value == 80.0 and b.predicted_value == 70.0
    # and the algebra still refuses to subtract them
    with pytest.raises(AssertionError, match="same ActionCandidate"):
        compare_predictions(a, b)


def test_two_formulations_occupy_different_cells_by_construction(state: WorkbenchState):
    """`formulation.id` is part of the model-state key, so the cells are
    distinct before any value is ever read from them."""
    baseline = _cand(state, "baseline", 25)
    modified = _cand(state, "modified", 25)
    assert baseline.property == modified.property
    assert dict(baseline.target_context) == dict(modified.target_context)
    assert baseline.formulation.id != modified.formulation.id

    key_a = resolve_model_state_key(baseline.formulation.id, baseline.property, baseline.target_context)
    key_b = resolve_model_state_key(modified.formulation.id, modified.property, modified.target_context)
    assert key_a != key_b


def test_the_assessment_primitive_also_refuses_a_mixed_pair(state: WorkbenchState):
    _multi(state)
    baseline = _cand(state, "baseline", 25)
    other = state.assessments_for(_cand(state, "modified", 25))[0]
    with pytest.raises(AssertionError, match="same ActionCandidate"):
        assess(state.prediction_at(baseline, state.session.state_history[0]),
               other.result, other.observation)


# -- I. cross-candidate counterfactual: NOT DEFINED --------------------------------------------------


def test_a_counterfactual_set_refuses_to_mix_candidates(state: WorkbenchState):
    """Two hypothetical branches on two candidates are not a set of
    possible futures for one quantity."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "explore", ["90"])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "explore", ["90"])
    a, b = state.branches
    assert a.candidate_id != b.candidate_id
    with pytest.raises(ValueError, match="same source_state_id"):
        make_counterfactual_set((a, b))


def test_the_workbench_already_refuses_the_same_pair_at_the_surface(state: WorkbenchState):
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "explore", ["90"])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "explore", ["90"])
    text = dispatch(state, "compare", ["branch", "1", "branch", "2"])
    assert "INCOMPARABLE BRANCHES" in text


# -- C/D. utility comparison and ranking: DEFINED, at the decision layer ------------------------------


def test_ranking_is_defined_but_only_over_utility(state: WorkbenchState):
    """`rank_candidates` DOES define a cross-candidate ordering. It
    orders `CandidateUtility.utility` and nothing else -- no prediction,
    uncertainty or information value participates."""
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["80"])
    optimization = state.decide()
    utility_set = optimization.utility_set

    ranked = rank_candidates(utility_set, RankingPolicy(
        direction=DESCENDING, unknown_utility_policy=UNRANKED))
    utilities = [r.utility.utility for r in ranked.rankings if r.utility.utility is not None]
    assert utilities == sorted(utilities, reverse=True)
    # the ordering is a function of utility alone: reversing direction
    # reverses it, which no scientific quantity would permit.
    ascending = rank_candidates(utility_set, RankingPolicy(
        direction=ASCENDING, unknown_utility_policy=UNRANKED))
    ascending_utilities = [r.utility.utility for r in ascending.rankings if r.utility.utility is not None]
    assert ascending_utilities == sorted(utilities)


def test_a_rank_number_never_implies_a_utility_comparison(state: WorkbenchState):
    """Under RANKED_LAST an indeterminate-utility candidate still gets a
    rank NUMBER, but its ranking_status stays NOT_DETERMINABLE -- the
    number means "placed last by policy", never "worse than rank N-1"."""
    optimization = state.decide()
    ranked = rank_candidates(optimization.utility_set, RankingPolicy(
        direction=DESCENDING, unknown_utility_policy=RANKED_LAST))
    for ranking in ranked.rankings:
        if ranking.utility.utility is None:
            assert ranking.ranking_status == "NOT_DETERMINABLE"


def test_utility_is_caller_supplied_not_a_retrieved_fact(state: WorkbenchState):
    """Utility is comparable across candidates only because ONE caller
    supplied all of them on one convention. That convention is the
    workbench's explicit exploration policy, not a measurement."""
    optimization = state.decide()
    for option in optimization.optimizations:
        assert option.utility.information_value.expected_information_gain == "NOT_DETERMINABLE"
    # every candidate is scored on the same explicitly-stated policy
    assert DECISION_POLICY.allow_indeterminate_utility is False


def test_selection_is_not_a_claim_of_scientific_superiority(state: WorkbenchState):
    """`optimize_candidates` is optimal only w.r.t. supplied utility. The
    workbench's own explanation must never upgrade that into a claim
    about a material."""
    _multi(state)
    dispatch(state, "decide", [])
    explanation = dispatch(state, "explain", [])
    lowered = explanation.lower()
    for phrase in ("scientifically", "superior", "is better", "better than", "outperform",
                   "proved", "proves", "confirms", "validates"):
        assert phrase not in lowered, f"explanation claims superiority: {phrase!r}"
    assert "highest determinate utility among eligible candidates" in explanation


def test_the_optimizer_selects_the_highest_supplied_utility_only(state: WorkbenchState):
    _multi(state)
    optimization = optimize_candidates(state.decide().utility_set, DECISION_POLICY)
    selected = [o for o in optimization.optimizations if o.status == "SELECTED"]
    determinate = [
        o.utility.utility for o in optimization.optimizations if o.utility.utility is not None
    ]
    if selected:
        assert selected[0].utility.utility == max(determinate)


# -- E/F. uncertainty and information value across candidates: NOT DEFINED ---------------------------


def test_uncertainty_is_a_within_cell_quantity(state: WorkbenchState):
    """`ModelStateInformationValueModel` reports the sample variance of
    ONE cell, and its own docstring sanctions comparing that number
    across STATES for one candidate -- never across candidates."""
    _multi(state)
    baseline = _cand(state, "baseline", 25)
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["100"])

    early = state.prediction_at(baseline, state.session.state_history[1])
    late = state.prediction_at(baseline, state.session.state)
    # across states, for one candidate: a defined before/after reading
    assert early.uncertainty is None      # one sample: no defined variance
    assert late.uncertainty == 200.0      # two samples: sample variance (n-1)

    # across candidates, at one state: two variances of two different
    # physical quantities. The algebra offers no operation combining them.
    modified = _cand(state, "modified", 25)
    assert state.prediction_at(modified, state.session.state).uncertainty is None
    with pytest.raises(AssertionError):
        compare_predictions(
            state.prediction_at(baseline, state.session.state),
            state.prediction_at(modified, state.session.state),
        )


def test_structural_information_value_is_categorical_not_a_score(state: WorkbenchState):
    """`materials.value` never produces a number to order candidates by:
    expected_information_gain is always NOT_DETERMINABLE."""
    _multi(state)
    optimization = state.decide()
    kinds = {o.utility.information_value.value_kind for o in optimization.optimizations}
    assert kinds  # a categorical kind per candidate
    for option in optimization.optimizations:
        assert option.utility.information_value.expected_information_gain == "NOT_DETERMINABLE"


# -- A/G. enumeration: VALID and LOSSLESS ------------------------------------------------------------


def test_enumerating_the_candidate_registry_covers_every_occupied_cell(state: WorkbenchState):
    """The fact a whole-state view would depend on: no cell can exist in
    a ModelState that the candidate registry cannot name. If this ever
    fails, an enumeration would be silently lossy and must not be built."""
    _multi(state)
    for model_state in state.session.state_history:
        occupied = set(model_state.samples.keys())
        derivable = {
            resolve_model_state_key(c.formulation.id, c.property, c.target_context)
            for c in state.list_candidates()
        }
        assert occupied <= derivable, occupied - derivable


def test_the_registry_already_has_an_authoritative_deterministic_order(state: WorkbenchState):
    """`generate_candidates` returns candidates sorted by ActionCandidate.id,
    and every existing view -- candidates, decide, select <n>, timeline,
    thread -- uses that same tuple. A whole-state enumeration needs NO
    new ordering convention."""
    candidates = state.list_candidates()
    assert [c.id for c in candidates] == sorted(c.id for c in candidates)
    assert _start().list_candidates()[0].id == candidates[0].id  # stable across sessions

    # the rendered registry walks that same tuple: display index N is
    # candidates[N-1], so the indices appear in ascending order.
    listing = dispatch(state, "candidates", [])
    shown = [listing.index(f"{i:02d}  ") for i in range(1, len(candidates) + 1)]
    assert shown == sorted(shown)


def test_enumeration_needs_no_aggregate_to_be_complete(state: WorkbenchState):
    """Every cell can be read independently at any state. Nothing about
    presenting them side by side requires a quantity spanning them."""
    _multi(state)
    current = state.session.state
    rows = [(c.id, state.prediction_at(c, current)) for c in state.list_candidates()]
    assert len(rows) == len(state.list_candidates())
    for candidate_id, prediction in rows:
        assert prediction.candidate_id == candidate_id
        assert prediction.state_id == current.id
        # each row is a complete, self-contained reading -- no row's value
        # depends on any other row.
        assert prediction.predicted_value is None or isinstance(prediction.predicted_value, float)


# -- regression lock: existing semantics must not drift ----------------------------------------------


def test_existing_commands_retain_their_semantics(state: WorkbenchState):
    """Phase 92 changes no production code. These are the guarantees the
    previous phases established, re-asserted here so a later phase that
    reaches for a cross-candidate relation cannot erode them quietly."""
    _multi(state)
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "decide", [])
    dispatch(state, "explore", ["90"])

    session = state.session
    fingerprint = state.pool.fingerprint()
    history = [s.id for s in state.session.state_history]
    branches = list(state.branches)
    decisions = list(state.decision_log)

    views = {
        "timeline": dispatch(state, "timeline", []),
        "thread": dispatch(state, "thread", ["baseline", "25"]),
        "compare": dispatch(state, "compare", []),
        "inspect": dispatch(state, "inspect", ["baseline", "25"]),
        "explain": dispatch(state, "explain", []),
        "candidates": dispatch(state, "candidates", []),
        "branches": dispatch(state, "branches", []),
    }

    # every view is observational
    assert state.session is session
    assert state.pool.fingerprint() == fingerprint
    assert [s.id for s in state.session.state_history] == history
    assert state.branches == branches
    assert state.decision_log == decisions

    # and none of them states a difference between two candidates
    for name, text in views.items():
        lowered = text.lower()
        for phrase in ("higher than", "lower than", "greater than", "less than",
                       "compared to", "versus", "difference between candidates",
                       "outperform", "superior", "scientifically"):
            assert phrase not in lowered, f"{name} implies a cross-candidate relation: {phrase!r}"


def test_no_view_places_two_candidates_predictions_in_one_comparison(state: WorkbenchState):
    """`candidates` legitimately TABULATES every candidate -- that is
    enumeration. What must never appear is a computed relation between
    two of those rows: a delta, a ratio, or an ordering by predicted
    value."""
    _multi(state)
    listing = dispatch(state, "candidates", [])
    # the table carries no delta column and no value-ordering language
    assert "Δ" not in listing
    for phrase in ("BEST", "WORST", "RANK", "LEADER", "TOP CANDIDATE"):
        assert phrase not in listing.upper()


def test_the_algebra_exposes_no_two_candidate_function():
    """A structural check: nothing in the comparison surface of
    `materials` accepts two candidates. If a future phase adds one, this
    test should be updated deliberately -- with a semantic definition --
    rather than the function appearing by accident."""
    import inspect

    from materials import assessment, ensemble, trajectory

    for module in (trajectory, assessment, ensemble):
        for name, function in inspect.getmembers(module, inspect.isfunction):
            if function.__module__ != module.__name__:
                continue
            parameters = list(inspect.signature(function).parameters)
            candidate_parameters = [p for p in parameters if "candidate" in p]
            assert len(candidate_parameters) <= 1, (
                f"{module.__name__}.{name} takes {candidate_parameters} -- a two-candidate "
                "operation would need a semantic definition first"
            )
