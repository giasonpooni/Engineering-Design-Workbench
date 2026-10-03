"""Phase 98: context-preserving observation admission.

The workbench now carries the candidate's declared `target_context` into
the admitted `Observation.content`, implementing the decision Phase 29
already made and Phase 97 proved the workbench was violating.

The change is generic: no context key is named in the workbench, no
value is normalised, and an empty target_context adds nothing. The
workbench supplies content; `materials.analysis` retains sole authority
over what that content means.
"""

import pytest

from materials.analysis import _comparison_context
from materials.decision import make_criterion
from materials.iteration import reevaluate_program
from materials.model_state import HYPOTHETICAL_SAMPLE_PREFIX, update
from workbench import theme
from workbench.cli import dispatch
from workbench.interaction import WorkbenchState, bootstrap_research_scenario


def _clock():
    n = {"i": 0}

    def clock() -> str:
        n["i"] += 1
        return f"2026-08-25T19:{n['i']:02d}:00Z"

    return clock


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _scenario(contexts, formulations=("baseline",), target=75.0) -> WorkbenchState:
    return bootstrap_research_scenario({
        "name": "phase 98", "process": "process-std-190c",
        "formulations": list(formulations), "property": "tensile_strength",
        "criterion": {"operator": ">=", "target": target},
        "contexts": list(contexts),
    }, clock=_clock())


def _groups(state: WorkbenchState, formulation="baseline", target=75.0):
    iteration = state.session.iteration
    decision = reevaluate_program(
        state.pool, state.engine, iteration.query,
        (make_criterion("tensile_strength", ">=", target),)).decision
    verdict = next(p for f in decision.formulations
                   for p in f.properties if f.formulation.natural_key == formulation)
    return verdict, (verdict.evidence.observed_comparison_groups if verdict.evidence else ())


# -- four-cell separation ------------------------------------------------------------------------------


def test_four_cells_produce_four_distinct_context_bearing_observations():
    state = _scenario([{"temperature_c": 25}, {"temperature_c": 100}],
                      formulations=("baseline", "modified"))
    for formulation in ("baseline", "modified"):
        for temperature in ("25", "100"):
            dispatch(state, "select", [formulation, temperature])
            dispatch(state, "observe", ["80", "MPa"])

    assert len({c.id for c in state.list_candidates()}) == 4
    observations = list(state.pool.all_observations())
    assert len(observations) == 4
    assert len({o.id for o in observations}) == 4
    # the same value admitted four times, now four DISTINCT facts
    contents = [tuple(sorted(o.content.items())) for o in observations]
    assert len(set(contents)) == 2  # two contexts; formulation is not in content
    assert len(state.session.state.samples) == 4  # ModelState still keeps all four apart


def test_the_pool_fingerprint_moves_only_on_admission():
    state = _scenario([{"temperature_c": 25}])
    before = state.pool.fingerprint()
    dispatch(state, "select", ["baseline", "25"])
    for command, args in (("predict", []), ("decide", []), ("explore", ["70"]),
                          ("criterion", []), ("state", []), ("timeline", [])):
        dispatch(state, command, args)
        assert state.pool.fingerprint() == before, command
    dispatch(state, "observe", ["90", "MPa"])
    assert state.pool.fingerprint() != before


# -- cross-context separation, and same-context conflict ------------------------------------------------


def test_two_conditions_do_not_form_one_group():
    state = _scenario([{"temperature_c": 25}, {"temperature_c": 100}])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])
    dispatch(state, "select", ["baseline", "100"])
    dispatch(state, "observe", ["60", "MPa"])

    _, groups = _groups(state)
    assert len(groups) == 2
    by_temperature = {g.context["temperature_c"]: g for g in groups}
    assert by_temperature[25].values == (90.0,)
    assert by_temperature[100].values == (60.0,)
    assert by_temperature[25].disagreement is None
    assert by_temperature[100].disagreement is None


def test_same_context_conflict_is_still_detected():
    """The fix must not have suppressed conflict detection -- it repaired
    the grouping. Two values at ONE condition genuinely disagree."""
    state = _scenario([{"temperature_c": 25}])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])
    dispatch(state, "observe", ["60", "MPa"])

    verdict, groups = _groups(state)
    assert len(groups) == 1
    assert sorted(groups[0].values) == [60.0, 90.0]
    assert groups[0].disagreement.spread == 30.0
    assert verdict.observed_status == "CONFLICTING_EVIDENCE"


def test_a_conflict_in_one_context_leaves_the_other_untouched():
    """The decisive proof: adding a conflicting value at 25 C must not
    disturb the 100 C group."""
    state = _scenario([{"temperature_c": 25}, {"temperature_c": 100}])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])
    dispatch(state, "select", ["baseline", "100"])
    dispatch(state, "observe", ["60", "MPa"])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["60", "MPa"])

    _, groups = _groups(state)
    by_temperature = {g.context["temperature_c"]: g for g in groups}
    assert sorted(by_temperature[25].values) == [60.0, 90.0]
    assert by_temperature[25].disagreement.spread == 30.0
    assert by_temperature[100].values == (60.0,)          # unchanged
    assert by_temperature[100].disagreement is None

    # and the per-context criterion verdicts follow suit
    decision, _ = state.evaluate_criteria()
    verdicts = {p.criterion.context["temperature_c"]: p.observed_status
                for f in decision.formulations if f.formulation.natural_key == "baseline"
                for p in f.properties}
    assert verdicts == {25: "CONFLICTING_EVIDENCE", 100: "FAIL"}


# -- context-free behaviour is preserved ----------------------------------------------------------------


def test_an_empty_target_context_adds_nothing():
    """No artificial context field is invented for a candidate that
    declares none."""
    state = _scenario([{}])
    dispatch(state, "select", ["baseline"])
    dispatch(state, "observe", ["90", "MPa"])
    observation = list(state.pool.all_observations())[0]
    assert set(observation.content) == {"property", "value", "unit"}
    assert "context" not in observation.content
    assert dict(_comparison_context(observation.content, "value")) == {"unit": "MPa"}


def test_a_context_free_scenario_still_reaches_a_verdict():
    state = _scenario([{}])
    dispatch(state, "select", ["baseline"])
    dispatch(state, "observe", ["90", "MPa"])
    verdict, groups = _groups(state)
    assert len(groups) == 1
    assert verdict.observed_status == "PASS"


# -- multiple context keys, handled generically ---------------------------------------------------------


def test_two_context_keys_separate_on_either_dimension():
    state = _scenario([
        {"temperature_c": 25, "pressure_kpa": 101},
        {"temperature_c": 25, "pressure_kpa": 200},
        {"temperature_c": 80, "pressure_kpa": 101},
    ])
    for candidate in state.list_candidates():
        state.selected_candidate = candidate
        state.observe(90.0, "MPa")

    _, groups = _groups(state)
    assert len(groups) == 3
    keys = {(g.context["temperature_c"], g.context["pressure_kpa"]) for g in groups}
    assert keys == {(25, 101), (25, 200), (80, 101)}
    # varying ONLY pressure separates; varying ONLY temperature separates
    assert (25, 101) in keys and (25, 200) in keys      # pressure alone
    assert (25, 101) in keys and (80, 101) in keys      # temperature alone


def test_no_context_key_is_named_in_the_workbench():
    """The implementation must be generic. A scenario using a key this
    project has never seen before must work identically."""
    state = _scenario([{"shear_rate_per_s": 500, "atmosphere": "nitrogen"}])
    dispatch(state, "select", ["baseline"])
    dispatch(state, "observe", ["90", "MPa"])
    observation = list(state.pool.all_observations())[0]
    assert observation.content["shear_rate_per_s"] == 500
    assert observation.content["atmosphere"] == "nitrogen"


def test_context_values_keep_their_types():
    """Values are carried verbatim -- never stringified or normalised."""
    state = _scenario([{"temperature_c": 25, "annealed": True, "grade": "A2"}])
    dispatch(state, "select", ["baseline"])
    dispatch(state, "observe", ["90", "MPa"])
    content = list(state.pool.all_observations())[0].content
    assert content["temperature_c"] == 25 and isinstance(content["temperature_c"], int)
    assert content["annealed"] is True
    assert content["grade"] == "A2"


def test_a_context_key_colliding_with_a_measurement_key_is_refused():
    """Silently overwriting `value` or `unit` would corrupt the
    measurement, so it is refused rather than accepted."""
    state = _scenario([{"unit": "bogus"}])
    dispatch(state, "select", ["baseline"])
    with pytest.raises(ValueError, match="measurement key"):
        state.observe(90.0, "MPa")


# -- units are untouched (sec.15) -----------------------------------------------------------------------


def test_different_units_remain_separate_and_are_never_converted():
    state = _scenario([{"temperature_c": 25}])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])
    dispatch(state, "observe", ["90000", "kPa"])   # numerically equivalent, NOT converted

    _, groups = _groups(state)
    assert len(groups) == 2
    assert {g.context["unit"] for g in groups} == {"MPa", "kPa"}
    assert all(g.disagreement is None for g in groups)


# -- provenance and identity ----------------------------------------------------------------------------


def test_the_observation_remains_traceable_through_the_whole_chain():
    state = _scenario([{"temperature_c": 25}])
    dispatch(state, "select", ["baseline", "25"])
    candidate = state.selected_candidate
    dispatch(state, "observe", ["90", "MPa"])

    assessment = state.assessments[-1]
    observation = list(state.pool.all_observations())[0]
    assert assessment.candidate_id == candidate.id
    assert assessment.result.candidate_id == candidate.id
    assert assessment.observation.id == observation.id
    sample = next(iter(state.session.state.samples.values()))[0]
    assert sample.observation_id == observation.id
    # context entered as part of the measured fact -- not as a foreign key
    assert "candidate_id" not in observation.content
    assert "formulation" not in observation.content


def test_identity_stays_content_derived():
    import re
    state = _scenario([{"temperature_c": 25}, {"temperature_c": 100}])
    for temperature in ("25", "100"):
        dispatch(state, "select", ["baseline", temperature])
        dispatch(state, "observe", ["90", "MPa"])
    hexadecimal = re.compile(r"^[0-9a-f]{64}$")
    for observation in state.pool.all_observations():
        assert hexadecimal.match(observation.id)
    for model_state in state.session.state_history:
        assert hexadecimal.match(model_state.id)


def test_candidate_and_cell_identity_are_unaffected_by_the_change():
    """Candidate ids and model-state keys derive from the candidate's own
    declared target_context, never from evidence content."""
    from materials.model_state import resolve_model_state_key
    state = _scenario([{"temperature_c": 25}])
    candidate = state.list_candidates()[0]
    before = (candidate.id,
              resolve_model_state_key(candidate.formulation.id, candidate.property,
                                      candidate.target_context))
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])
    after = (state.list_candidates()[0].id,
             resolve_model_state_key(candidate.formulation.id, candidate.property,
                                     candidate.target_context))
    assert before == after


# -- isolation invariants preserved ---------------------------------------------------------------------


def test_historical_states_remain_immutable_with_context_attached():
    state = _scenario([{"temperature_c": 25}, {"temperature_c": 100}])
    dispatch(state, "select", ["baseline", "25"])
    candidate = state.selected_candidate
    dispatch(state, "observe", ["90", "MPa"])
    held = state.session
    held_id = held.state.id
    held_value = held.predict(candidate).predicted_value
    held_observation = list(state.pool.all_observations())[0]
    held_content = dict(held_observation.content)

    dispatch(state, "select", ["baseline", "100"])
    dispatch(state, "observe", ["60", "MPa"])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["70", "MPa"])

    assert held.state.id == held_id
    assert held.predict(candidate).predicted_value == held_value
    # the historical observation, and its context, are unchanged
    same = next(o for o in state.pool.all_observations() if o.id == held_observation.id)
    assert dict(same.content) == held_content


def test_counterfactual_isolation_is_unchanged():
    state = _scenario([{"temperature_c": 25}])
    dispatch(state, "select", ["baseline", "25"])
    candidate = state.selected_candidate
    fingerprint = state.pool.fingerprint()
    observations = len(state.pool.all_observations())

    dispatch(state, "explore", ["999"])
    assert state.pool.fingerprint() == fingerprint
    assert len(state.pool.all_observations()) == observations

    branch = state.branches[0]
    sample = next(iter(branch.projected_state.samples.values()))[0]
    assert sample.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)

    dispatch(state, "observe", ["90", "MPa"])
    assessment = state.assessments[-1]
    with pytest.raises(AssertionError, match="hypothetical"):
        update(branch.projected_state, candidate, assessment.result, assessment.observation)


def test_the_predicted_side_is_unchanged_by_the_fix():
    """The observed side becoming evaluable does not justify changing the
    predicted side: the pool still holds no DerivedValues."""
    state = _scenario([{"temperature_c": 25}])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])
    decision, _ = state.evaluate_criteria()
    predicted = {p.predicted_status for f in decision.formulations for p in f.properties}
    assert predicted == {"INSUFFICIENT_EVIDENCE"}


def test_candidate_isolation_holds_across_formulations():
    state = _scenario([{"temperature_c": 25}], formulations=("baseline", "modified"))
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["60", "MPa"])

    baseline_verdict, baseline_groups = _groups(state, "baseline")
    modified_verdict, modified_groups = _groups(state, "modified")
    assert baseline_groups[0].values == (90.0,)
    assert modified_groups[0].values == (60.0,)
    assert baseline_verdict.observed_status == "PASS"
    assert modified_verdict.observed_status == "FAIL"


# -- determinism ----------------------------------------------------------------------------------------


def test_admission_is_deterministic():
    def run():
        state = _scenario([{"temperature_c": 25}, {"temperature_c": 100}])
        for temperature in ("25", "100"):
            dispatch(state, "select", ["baseline", temperature])
            dispatch(state, "observe", ["90", "MPa"])
        return (tuple(sorted(o.id for o in state.pool.all_observations())),
                state.pool.fingerprint(),
                tuple(s.id for s in state.session.state_history),
                tuple(sorted(tuple(sorted(o.content.items()))
                             for o in state.pool.all_observations())))

    assert run() == run()
