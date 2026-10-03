"""Phase 73: proves a user-supplied, plain-JSON SCENARIO DEFINITION
(never scientific state) can drive the existing candidate-generation
machinery end to end, through `workbench.interaction.
bootstrap_research_scenario` and the real `workbench.cli` interaction
layer -- no new domain type, no new identity mechanism, no persistence.

Uses the actual committed example, `examples/polymer_tensile_strength.
json` (three formulations x three experimental contexts, one shared
property) -- the exact file `python -m workbench --scenario
examples/polymer_tensile_strength.json` loads, parsed with nothing
beyond the standard library `json` module.
"""

import dataclasses
import io
import json
from pathlib import Path

import pytest

from materials.model_state import HYPOTHETICAL_SAMPLE_PREFIX, resolve_model_state_key, update
from workbench.cli import _load_scenario_state, dispatch, format_scenario_banner, main
from workbench.interaction import (
    DEFAULT_CRITERION_TARGET, DEFAULT_PROCESS_KEY, ResearchScenario, WorkbenchState,
    bootstrap_research_scenario,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_SCENARIO_PATH = REPO_ROOT / "examples" / "polymer_tensile_strength.json"


def _fixed_clock():
    counter = {"n": 0}

    def clock() -> str:
        n = counter["n"]
        counter["n"] += 1
        return f"2026-08-24T06:{n:02d}:00Z"

    return clock


def _load_example_config() -> dict:
    with open(EXAMPLE_SCENARIO_PATH, encoding="utf-8") as f:
        return json.load(f)


def _find(state: WorkbenchState, formulation_key: str, context: dict):
    return next(
        c for c in state.list_candidates()
        if c.formulation.natural_key == formulation_key and dict(c.target_context) == context
    )


def _display_index(state: WorkbenchState, candidate) -> int:
    return state.list_candidates().index(candidate) + 1


def _sample_count(state: WorkbenchState, candidate) -> int:
    key = resolve_model_state_key(candidate.formulation.id, candidate.property, candidate.target_context)
    return len(state.session.state.samples.get(key, ()))


@pytest.fixture()
def state() -> WorkbenchState:
    config = _load_example_config()
    return bootstrap_research_scenario(config, clock=_fixed_clock())


# -- (1)(2)(3) scenario configuration creates N candidates, using existing identity machinery --------


def test_scenario_json_produces_nine_distinct_candidates_with_unique_identity(state: WorkbenchState):
    candidates = state.list_candidates()
    assert len(candidates) == 9  # 3 formulations x 3 contexts, exactly the committed example's shape
    assert len({c.id for c in candidates}) == 9  # distinct ids -- ActionCandidate's own existing identity

    keys = {resolve_model_state_key(c.formulation.id, c.property, c.target_context) for c in candidates}
    assert len(keys) == 9  # (3) distinct model-state keys, one per (formulation, property, context) cell

    formulations = {c.formulation.natural_key for c in candidates}
    assert formulations == {"baseline", "modified", "high_filler"}
    contexts = {tuple(sorted(c.target_context.items())) for c in candidates}
    assert contexts == {
        (("temperature_c", 25),), (("temperature_c", 80),), (("temperature_c", 120),),
    }


# -- (4) contexts remain isolated; (5)(6) initial state contains no observations, honestly undetermined --


def test_initial_state_has_no_observations_and_honest_predictions(state: WorkbenchState):
    for candidate in state.list_candidates():
        prediction = state.session.predict(candidate)
        assert prediction.predicted_value is None
        assert prediction.uncertainty is None
        assert prediction.sample_count == 0
        assert _sample_count(state, candidate) == 0


# -- (7)(8) a real observation updates only its own candidate/cell --------------------------------------


def test_real_observation_updates_only_the_selected_candidate(state: WorkbenchState):
    baseline_25 = _find(state, "baseline", {"temperature_c": 25})
    baseline_80 = _find(state, "baseline", {"temperature_c": 80})
    modified_25 = _find(state, "modified", {"temperature_c": 25})

    dispatch(state, "select", [str(_display_index(state, baseline_25))])
    dispatch(state, "observe", ["82"])

    assert _sample_count(state, baseline_25) == 1
    # every other candidate, including the SAME formulation at a different context, is untouched
    assert _sample_count(state, baseline_80) == 0
    assert _sample_count(state, modified_25) == 0
    for candidate in state.list_candidates():
        if candidate.id != baseline_25.id:
            assert _sample_count(state, candidate) == 0


# -- (11) residuals remain signed, both directions ----------------------------------------------------


def test_signed_residuals_both_directions(state: WorkbenchState):
    baseline_25 = _find(state, "baseline", {"temperature_c": 25})
    dispatch(state, "select", [str(_display_index(state, baseline_25))])
    dispatch(state, "observe", ["80"])

    positive_output = dispatch(state, "observe", ["100"])
    assert "+20.0" in positive_output
    assert state.assessments[-1].residual == 20.0

    negative_output = dispatch(state, "observe", ["60"])
    assert "-30.0" in negative_output  # 60 - mean([80, 100]) = 60 - 90
    assert state.assessments[-1].residual == -30.0


# -- (9) decide recomputes from current state; (10) explore never mutates real state -------------------


def test_decide_recomputes_and_explore_never_mutates(state: WorkbenchState):
    baseline_25 = _find(state, "baseline", {"temperature_c": 25})
    modified_80 = _find(state, "modified", {"temperature_c": 80})

    decision_before = state.decide()
    utility_before = next(
        o for o in decision_before.optimizations if o.candidate_id == baseline_25.id
    ).utility.utility

    dispatch(state, "select", [str(_display_index(state, baseline_25))])
    dispatch(state, "observe", ["80"])
    decision_after = state.decide()
    utility_after = next(
        o for o in decision_after.optimizations if o.candidate_id == baseline_25.id
    ).utility.utility
    assert utility_after != utility_before  # recomputed from the real, changed ModelState

    # explore against a candidate that already has evidence: hypothetical only, never mutates
    real_state_id = state.session.state.id
    pre_fingerprint = state.pool.fingerprint()
    dispatch(state, "select", [str(_display_index(state, baseline_25))])
    explore_output = dispatch(state, "explore", ["150"])
    assert "This branch is hypothetical." in explore_output
    outcome = state.last_counterfactual
    assert outcome is not None
    assert outcome.projected_state.id != real_state_id
    assert state.session.state.id == real_state_id
    assert state.pool.fingerprint() == pre_fingerprint

    # a wholly untouched candidate is unaffected by any of this
    assert _sample_count(state, modified_80) == 0


# -- counterfactual isolation, in full (Phase 72's own checklist, re-verified under a user scenario) ---


def test_counterfactual_isolation_under_user_scenario(state: WorkbenchState):
    baseline_25 = _find(state, "baseline", {"temperature_c": 25})
    dispatch(state, "select", [str(_display_index(state, baseline_25))])
    dispatch(state, "observe", ["80"])

    real_assessment = state.assessments[-1]
    outcome = state.explore(500.0)
    sample = next(
        s for s in outcome.projected_state.samples[
            resolve_model_state_key(baseline_25.formulation.id, baseline_25.property, baseline_25.target_context)
        ]
        if s.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)
    )
    assert sample.value == 500.0
    with pytest.raises(AssertionError, match="hypothetical"):
        update(outcome.projected_state, baseline_25, real_assessment.result, real_assessment.observation)


# -- (12)(13) history and diagnostics remain correct under the user scenario ----------------------------


def test_history_and_diagnostics_correct_under_user_scenario(state: WorkbenchState):
    baseline_25 = _find(state, "baseline", {"temperature_c": 25})
    modified_120 = _find(state, "modified", {"temperature_c": 120})

    dispatch(state, "select", [str(_display_index(state, baseline_25))])
    dispatch(state, "observe", ["80"])
    dispatch(state, "select", [str(_display_index(state, modified_120))])
    dispatch(state, "observe", ["60"])
    dispatch(state, "select", [str(_display_index(state, baseline_25))])
    dispatch(state, "observe", ["100"])

    diagnostic_set = state.history()
    assert diagnostic_set.candidate_id == baseline_25.id
    assert len(diagnostic_set.diagnostics) == 3
    first, middle, last = diagnostic_set.diagnostics
    assert middle.assessment is None  # modified_120's own transition, not baseline_25's
    assert middle.delta_predicted_value == 0.0
    assert last.residual_against_previous_prediction == 20.0

    history_output = dispatch(state, "history", [])
    diagnostics_output = dispatch(state, "diagnostics", [])
    assert "+20.0" in history_output and "+20.0" in diagnostics_output
    assert "model_state_key" in diagnostics_output and "model_state_key" not in history_output


# -- (14) EvidencePool changes only on real admission --------------------------------------------------


def test_evidence_pool_changes_only_on_real_admission(state: WorkbenchState):
    baseline_25 = _find(state, "baseline", {"temperature_c": 25})
    fp0 = state.pool.fingerprint()

    dispatch(state, "candidates", [])
    dispatch(state, "select", [str(_display_index(state, baseline_25))])
    dispatch(state, "predict", [])
    dispatch(state, "decide", [])
    dispatch(state, "explore", ["999"])
    assert state.pool.fingerprint() == fp0

    dispatch(state, "observe", ["80"])
    assert state.pool.fingerprint() != fp0


# -- (15) historical sessions remain immutable ----------------------------------------------------------


def test_historical_sessions_remain_immutable(state: WorkbenchState):
    baseline_25 = _find(state, "baseline", {"temperature_c": 25})
    modified_120 = _find(state, "modified", {"temperature_c": 120})

    dispatch(state, "select", [str(_display_index(state, baseline_25))])
    dispatch(state, "observe", ["80"])
    session_after_first = state.session
    prediction_after_first = session_after_first.predict(baseline_25).predicted_value

    dispatch(state, "select", [str(_display_index(state, modified_120))])
    dispatch(state, "observe", ["60"])
    dispatch(state, "select", [str(_display_index(state, baseline_25))])
    dispatch(state, "observe", ["100"])

    assert session_after_first.predict(baseline_25).predicted_value == prediction_after_first == 80.0
    assert len(session_after_first.state_history) == 2
    assert state.session.predict(baseline_25).predicted_value == 90.0


# -- the JSON file itself: a scenario definition, never scientific state --------------------------------


def test_scenario_json_contains_no_scientific_state():
    config = _load_example_config()
    forbidden_keys = {"observations", "predictions", "residuals", "samples", "model_state", "session"}
    assert forbidden_keys.isdisjoint(config.keys())
    assert set(config.keys()) == {"name", "process", "formulations", "property", "criterion", "contexts"}


# -- (9 of the re-spec) scenario METADATA never becomes scientific state --------------------------------


def test_scenario_metadata_does_not_become_scientific_state(state: WorkbenchState):
    """The `ResearchScenario` carried on `WorkbenchState` is configuration
    only: it holds no observation/prediction/residual/state field, and
    observing real evidence never mutates it (it is frozen) nor lets it
    leak into `ModelState`."""
    scenario = state.scenario
    assert scenario is not None
    assert scenario.name == "polymer tensile strength study"

    # PHASE 103: `criteria` replaced the single-property fields as the sole
    # STORED declaration; property/contexts/criterion_* are now derived views
    # over it, so they cannot drift from what is actually evaluated. The
    # invariant this test protects is unchanged: engineering configuration
    # only, never scientific state.
    scenario_fields = set(vars(scenario).keys())
    assert scenario_fields == {"name", "formulations", "criteria", "process"}
    assert scenario.property == "tensile_strength"          # derived, still readable
    assert len(scenario.contexts) == 3                       # derived from the criteria
    for forbidden in ("samples", "observations", "predictions", "residuals", "session", "state"):
        assert not hasattr(scenario, forbidden)

    baseline_25 = _find(state, "baseline", {"temperature_c": 25})
    dispatch(state, "select", [str(_display_index(state, baseline_25))])
    dispatch(state, "observe", ["80"])

    # the scenario is unchanged by real evidence, and is frozen against mutation
    assert state.scenario is scenario
    assert scenario.name == "polymer tensile strength study"
    with pytest.raises(dataclasses.FrozenInstanceError):
        scenario.name = "tampered"  # type: ignore[misc]

    # and the scenario's own configuration never appears inside ModelState
    for samples in state.session.state.samples.values():
        for sample in samples:
            assert "polymer" not in sample.observation_id


# -- (2 of the re-spec) malformed scenarios are rejected clearly ----------------------------------------


@pytest.mark.parametrize(
    "mutate, expected_fragment",
    [
        (lambda c: c.pop("name"), "name"),
        (lambda c: c.pop("formulations"), "formulations"),
        (lambda c: c.pop("property"), "property"),
        (lambda c: c.pop("contexts"), "contexts"),
        (lambda c: c.update(name=""), "name"),
        (lambda c: c.update(formulations=[]), "formulations"),
        (lambda c: c.update(formulations="baseline"), "formulations"),
        (lambda c: c.update(formulations=["baseline", 7]), "formulations"),
        (lambda c: c.update(property=123), "property"),
        (lambda c: c.update(contexts=[]), "contexts"),
        (lambda c: c.update(contexts=["25C"]), "contexts"),
        (lambda c: c.update(process=""), "process"),
        (lambda c: c.update(criterion="at least 80"), "criterion"),
        (lambda c: c.update(criterion={"operator": ">=", "target": "eighty"}), "target"),
        (lambda c: c.update(criterion={"operator": "", "target": 80}), "operator"),
    ],
)
def test_malformed_scenario_is_rejected_clearly(mutate, expected_fragment):
    config = _load_example_config()
    mutate(config)
    with pytest.raises(ValueError) as excinfo:
        ResearchScenario.from_config(config)
    assert expected_fragment in str(excinfo.value)


def test_optional_fields_default_so_the_minimal_scenario_shape_loads():
    """The re-spec's own illustrative JSON omits `process` and
    `criterion`; both default rather than failing."""
    minimal = {
        "name": "minimal study",
        "formulations": ["baseline", "modified"],
        "property": "tensile_strength",
        "contexts": [{"temperature_c": 25}, {"temperature_c": 80}],
    }
    scenario = ResearchScenario.from_config(minimal)
    assert scenario.process == DEFAULT_PROCESS_KEY
    assert scenario.criterion_operator == ">="
    assert scenario.criterion_target == DEFAULT_CRITERION_TARGET
    # PHASE 103: the second factor is criteria, which equals the context count
    # in this single-property case but is the figure that actually drives
    # candidate generation.
    assert scenario.describe_candidate_space() == "2 formulation(s) x 2 criteria"

    built = bootstrap_research_scenario(scenario, clock=_fixed_clock())
    assert len(built.list_candidates()) == 4


# -- the startup banner: the roster a researcher sees before typing anything ----------------------------


def test_startup_banner_lists_the_scenario_and_every_candidate(state: WorkbenchState):
    banner = format_scenario_banner(state)
    assert "RESEARCH SCENARIO" in banner
    assert "polymer tensile strength study" in banner
    assert "OBSERVATIONS" in banner
    assert "9 CANDIDATES" in banner
    for formulation in ("baseline", "modified", "high_filler"):
        assert f"{formulation} \u00b7 tensile_strength \u00b7" in banner
    for temperature in ("25 C", "80 C", "120 C"):
        assert temperature in banner
    # every candidate is listed, zero-padded to match `select <n>`
    for i in range(1, 10):
        assert f"{i:02d}  " in banner


# -- the --scenario CLI flag itself: the smallest natural extension over run_repl's state parameter -----


def test_load_scenario_state_from_the_committed_example_file():
    loaded = _load_scenario_state(str(EXAMPLE_SCENARIO_PATH))
    assert len(loaded.list_candidates()) == 9
    assert loaded.session.state.samples == {}


def test_main_with_scenario_flag_starts_the_real_repl_against_it(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("status\nquit\n"))
    exit_code = main(["--scenario", str(EXAMPLE_SCENARIO_PATH)])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "polymer tensile strength study" in output  # the banner announced the loaded study
    assert "9 CANDIDATES" in output


def test_main_with_missing_scenario_file_fails_cleanly(capsys):
    exit_code = main(["--scenario", "/nonexistent/path/does-not-exist.json"])
    assert exit_code == 1
    assert "SCENARIO NOT LOADED" in capsys.readouterr().err


def test_main_with_no_scenario_flag_uses_the_unchanged_default(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("status\nquit\n"))
    exit_code = main([])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "2 CANDIDATES" in output  # bootstrap_multi_candidate_scenario, unchanged
