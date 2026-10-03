"""Phase 99: evidence-semantics consolidation audit.

Phase 98 changed what an admitted Observation contains. This module
encodes the architectural invariants that must hold AFTERWARDS, so a
later change cannot quietly undo the coherence the change established.

These are semantic contracts, not implementation details: "context
survives admission unchanged", "the three state concepts stay separate",
"the workbench transports context but never defines it".
"""

import ast
import re
from pathlib import Path

import pytest

from materials.analysis import _comparison_context
from materials.decision import make_criterion
from materials.iteration import reevaluate_program
from materials.model_state import HYPOTHETICAL_SAMPLE_PREFIX, resolve_model_state_key
from workbench import theme
from workbench.cli import dispatch
from workbench.interaction import WorkbenchState, bootstrap_research_scenario

REPO = Path(__file__).resolve().parent.parent


def _clock():
    n = {"i": 0}

    def clock() -> str:
        n["i"] += 1
        return f"2026-08-26T05:{n['i']:02d}:00Z"

    return clock


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _scenario(contexts, formulations=("baseline",), target=75.0) -> WorkbenchState:
    return bootstrap_research_scenario({
        "name": "phase 99", "process": "process-std-190c",
        "formulations": list(formulations), "property": "tensile_strength",
        "criterion": {"operator": ">=", "target": target},
        "contexts": list(contexts),
    }, clock=_clock())


def _observed(state: WorkbenchState, formulation="baseline", target=75.0, context=None):
    iteration = state.session.iteration
    criterion = make_criterion("tensile_strength", ">=", target, context=context)
    decision = reevaluate_program(
        state.pool, state.engine, iteration.query, (criterion,)).decision
    verdict = next(p for f in decision.formulations
                   for p in f.properties if f.formulation.natural_key == formulation)
    return verdict, (verdict.evidence.observed_comparison_groups if verdict.evidence else ())


# -- the three state concepts stay separate (sec.2) ----------------------------------------------------


def test_evidence_model_and_decision_state_are_three_distinct_things():
    """Each has its own identity, its own substrate, and its own moment
    of change. No view may substitute one for another."""
    state = _scenario([{"temperature_c": 25}])
    dispatch(state, "select", ["baseline", "25"])

    evidence_before = state.pool.fingerprint()
    model_before = state.session.state.id
    dispatch(state, "decide", [])
    decision = state.last_decision
    decision_state = state.last_decision_state_id

    # a decision changes neither evidence nor model state
    assert state.pool.fingerprint() == evidence_before
    assert state.session.state.id == model_before
    assert decision_state == model_before  # but it RECORDS which model state it read

    # an observation changes evidence AND model state, and stales the decision
    dispatch(state, "observe", ["90", "MPa"])
    assert state.pool.fingerprint() != evidence_before
    assert state.session.state.id != model_before
    assert state.last_decision is None
    assert state.previous_decision is decision


def test_a_model_prediction_is_never_evidence_and_evidence_is_never_a_prediction():
    state = _scenario([{"temperature_c": 25}])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])

    # the ModelState has a prediction
    assert state.session.predict(state.selected_candidate).predicted_value == 90.0
    # the pool has an observation, and NO derived value
    assert len(list(state.pool.all_observations())) == 1
    verdict, _ = _observed(state)
    assert verdict.observed_status == "PASS"
    assert verdict.predicted_status == "INSUFFICIENT_EVIDENCE"


def test_no_production_code_turns_a_prediction_into_evidence():
    for package in ("materials", "experiment", "evidence", "retrieval", "workbench"):
        directory = REPO / package
        if not directory.exists():
            continue
        for path in directory.rglob("*.py"):
            if path.name == "types.py" and package == "evidence":
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    assert node.func.id != "make_derived_value", f"{path}"


# -- context has one source of truth (sec.3) -----------------------------------------------------------


def test_the_workbench_transports_context_but_never_defines_it():
    """`_observation_content` must name no context key. If a key name
    appears in the admission path, the workbench has begun defining
    scientific semantics that belong to the scenario and materials."""
    import inspect

    from workbench import interaction

    body = inspect.getsource(interaction._observation_content)
    code = body.split('"""')[-1]  # the executable part, excluding the docstring
    for key in ("temperature", "pressure", "shear", "atmosphere", "anneal", "grade"):
        assert key not in code, f"admission path names a context key: {key!r}"
    assert "candidate.target_context" in code  # it transports the declared mapping


def test_the_workbench_defines_no_second_context_representation():
    """`theme.context` renders and `_context_tokens` selects; neither
    normalises, converts or re-keys a context."""
    from workbench import cli, theme as theme_module
    import inspect

    for function in (theme_module.context, cli._context_tokens):
        code = inspect.getsource(function)
        for forbidden in ("float(", "int(", "round(", "convert", "normalis", "normaliz"):
            assert forbidden not in code, f"{function.__name__} transforms context: {forbidden}"


# -- context round-trips unchanged (sec.4) --------------------------------------------------------------


@pytest.mark.parametrize("context", [
    {},
    {"temperature_c": 25},
    {"temperature_c": 25, "pressure_kpa": 101},
    {"grade": "A2"},
    {"annealed": True},
    {"temperature_c": 25, "grade": "A2", "annealed": False},
    {"shear_rate_per_s": 500},          # a key this project has never seen
])
def test_context_survives_admission_with_values_and_types_intact(context):
    state = _scenario([context])
    state.selected_candidate = state.list_candidates()[0]
    state.observe(90.0, "MPa")

    observation = list(state.pool.all_observations())[0]
    group_context = _comparison_context(observation.content, "value")
    for key, value in context.items():
        assert observation.content[key] == value
        assert type(observation.content[key]) is type(value)
        assert group_context[key] == value
        assert type(group_context[key]) is type(value)
    # nothing beyond the measurement and the declared context is invented
    assert set(observation.content) == {"property", "value", "unit"} | set(context)


# -- hash dependency graph (sec.5) ----------------------------------------------------------------------


def test_evidence_content_flows_into_evidence_identity_only():
    """context -> content -> Observation.id -> Sample -> ModelState.id
    and pool fingerprint. It must NOT flow into candidate identity."""
    state = _scenario([{"temperature_c": 25}])
    candidate = state.list_candidates()[0]
    candidate_id = candidate.id
    cell = resolve_model_state_key(candidate.formulation.id, candidate.property,
                                   candidate.target_context)

    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])

    observation = list(state.pool.all_observations())[0]
    sample = next(iter(state.session.state.samples.values()))[0]
    assert sample.observation_id == observation.id
    assert observation.content["temperature_c"] == 25
    # candidate identity and cell key are untouched by admitting evidence
    assert state.list_candidates()[0].id == candidate_id
    assert resolve_model_state_key(candidate.formulation.id, candidate.property,
                                   candidate.target_context) == cell


# -- grouping is by context, not magnitude (sec.6) -------------------------------------------------------


@pytest.mark.parametrize("values,conflicting,solitary", [
    ((("25", "90"), ("100", "60"), ("25", "60")), 25, 100),
    ((("25", "60"), ("100", "90"), ("25", "90")), 25, 100),   # magnitudes reversed
])
def test_group_structure_follows_context_not_value(values, conflicting, solitary):
    state = _scenario([{"temperature_c": 25}, {"temperature_c": 100}])
    for temperature, value in values:
        dispatch(state, "select", ["baseline", temperature])
        dispatch(state, "observe", [value, "MPa"])

    _, groups = _observed(state)
    by_temperature = {g.context["temperature_c"]: g for g in groups}
    assert len(by_temperature[conflicting].values) == 2
    assert by_temperature[conflicting].disagreement.spread == 30.0
    assert len(by_temperature[solitary].values) == 1
    assert by_temperature[solitary].disagreement is None


# -- the context-free criterion consequence (sec.7) -------------------------------------------------------


def test_a_context_free_criterion_is_meaningful_only_over_one_context():
    """Documented, not fixed. With one context it selects uniquely; with
    two it selects neither, and the materials layer says INCOMPARABLE
    rather than choosing. The workbench exposes that, never resolves it."""
    state = _scenario([{"temperature_c": 25}, {"temperature_c": 100}])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])
    verdict, _ = _observed(state)
    assert verdict.observed_status == "PASS"

    dispatch(state, "select", ["baseline", "100"])
    dispatch(state, "observe", ["60", "MPa"])
    verdict, groups = _observed(state)
    assert verdict.observed_status == "INCOMPARABLE"
    assert verdict.observed_group is None
    assert len(groups) == 2      # both exist; neither was chosen


# -- units are distinct and never converted (sec.13) --------------------------------------------------------


def test_the_same_magnitude_in_three_units_forms_three_groups():
    state = _scenario([{"temperature_c": 25}])
    dispatch(state, "select", ["baseline", "25"])
    for value, unit in (("90", "MPa"), ("0.09", "GPa"), ("90000", "kPa")):
        dispatch(state, "observe", [value, unit])

    verdict, groups = _observed(state)
    assert len(groups) == 3
    assert {g.context["unit"] for g in groups} == {"MPa", "GPa", "kPa"}
    assert all(g.disagreement is None for g in groups)
    # no conversion happened, so no criterion can select among them
    assert verdict.observed_status == "INCOMPARABLE"


# -- real vs hypothetical (sec.9) --------------------------------------------------------------------------


def test_context_preservation_did_not_weaken_the_hypothetical_boundary():
    state = _scenario([{"temperature_c": 25}])
    dispatch(state, "select", ["baseline", "25"])
    candidate = state.selected_candidate

    fingerprint = state.pool.fingerprint()
    history = [s.id for s in state.session.state_history]
    dispatch(state, "explore", ["999"])

    assert state.pool.fingerprint() == fingerprint
    assert [s.id for s in state.session.state_history] == history
    branch = state.branches[0]
    sample = next(iter(branch.projected_state.samples.values()))[0]
    assert sample.observation_id.startswith(HYPOTHETICAL_SAMPLE_PREFIX)
    assert all(o.id != sample.observation_id for o in state.pool.all_observations())
    assert branch.projected_state_id not in set(history)

    from materials.model_state import update
    dispatch(state, "observe", ["90", "MPa"])
    assessment = state.assessments[-1]
    with pytest.raises(AssertionError, match="hypothetical"):
        update(branch.projected_state, candidate, assessment.result, assessment.observation)


# -- historical immutability reads history, not the registry (sec.10) ---------------------------------------


def test_a_historical_view_reads_historical_evidence_not_the_current_registry():
    """The strongest form: an observation admitted at 25 C must still
    report 25 C after later evidence exists at another context."""
    state = _scenario([{"temperature_c": 25}, {"temperature_c": 100}])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])
    first = list(state.pool.all_observations())[0]
    first_content = dict(first.content)
    held_session = state.session
    held_state_id = held_session.state.id

    dispatch(state, "select", ["baseline", "100"])
    dispatch(state, "observe", ["60", "MPa"])

    same = next(o for o in state.pool.all_observations() if o.id == first.id)
    assert dict(same.content) == first_content
    assert same.content["temperature_c"] == 25
    assert held_session.state.id == held_state_id
    # and every historical view still renders without disturbing anything
    fingerprint = state.pool.fingerprint()
    for command, args in (("timeline", []), ("timeline", ["1"]), ("thread", []),
                          ("state", ["1"]), ("diagnostics", []), ("history", [])):
        dispatch(state, command, args)
    assert state.pool.fingerprint() == fingerprint


# -- multi-candidate isolation (sec.11) ----------------------------------------------------------------------


def test_observing_one_cell_leaves_every_other_cell_untouched():
    state = _scenario([{"temperature_c": 25}, {"temperature_c": 100}],
                      formulations=("baseline", "modified"))
    before = {c.id: state.prediction_at(c, state.session.state).sample_count
              for c in state.list_candidates()}

    dispatch(state, "select", ["baseline", "25"])
    target = state.selected_candidate
    dispatch(state, "observe", ["90", "MPa"])

    after = {c.id: state.prediction_at(c, state.session.state).sample_count
             for c in state.list_candidates()}
    assert after[target.id] == before[target.id] + 1
    for candidate_id, count in before.items():
        if candidate_id != target.id:
            assert after[candidate_id] == count

    # a second cell at another context: global state advances, cells stay isolated
    global_before = state.session.state.id
    dispatch(state, "select", ["modified", "100"])
    dispatch(state, "observe", ["60", "MPa"])
    assert state.session.state.id != global_before
    assert state.prediction_at(target, state.session.state).predicted_value == 90.0


# -- the criterion surface asserts no comparison (sec.12) -----------------------------------------------------


def test_no_view_implies_a_relation_between_two_candidates():
    state = _scenario([{"temperature_c": 25}], formulations=("baseline", "modified"))
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])
    dispatch(state, "select", ["modified", "25"])
    dispatch(state, "observe", ["60", "MPa"])
    dispatch(state, "decide", [])

    for command, args in (("criterion", []), ("criterion", ["baseline", "25"]),
                          ("inspect", []), ("state", []), ("thread", []),
                          ("timeline", []), ("explain", []), ("candidates", [])):
        lowered = dispatch(state, command, args).lower()
        for phrase in ("better", "worse", "superior", "outperform", "improvement",
                       "treatment", "control group", "more likely", "probability",
                       "confidence interval", "standard error"):
            assert phrase not in lowered, f"{command}: {phrase!r}"


# -- identity sweep (sec.14) -------------------------------------------------------------------------------


def test_every_displayed_identity_resolves_to_an_existing_object():
    state = _scenario([{"temperature_c": 25}, {"temperature_c": 100}],
                      formulations=("baseline", "modified"))
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "decide", [])
    dispatch(state, "explore", ["70"])
    dispatch(state, "observe", ["90", "MPa"])
    dispatch(state, "select", ["modified", "100"])
    dispatch(state, "observe", ["60", "MPa"])
    dispatch(state, "decide", [])

    known = {theme.ident(s.id) for s in state.session.state_history}
    known |= {theme.ident(c.id) for c in state.list_candidates()}
    known |= {theme.ident(b.projected_state_id) for b in state.branches}
    known |= {theme.ident(b.model_state_key) for b in state.branches}
    # a candidate's own cell key -- `diagnostics` shows which model-state cell
    # a transition concerned, which is an existing content-addressed identity.
    known |= {theme.ident(resolve_model_state_key(c.formulation.id, c.property,
                                                  c.target_context))
              for c in state.list_candidates()}
    known |= {theme.ident(a.observation.id) for a in state.assessments}
    known |= {theme.ident(a.result.id) for a in state.assessments}
    known |= {theme.ident(state.pool.fingerprint()), theme.ident(state.document_id)}
    known |= {theme.ident(o.id) for o in state.pool.all_observations()}

    for command, args in (
        ("scenario", []), ("status", []), ("candidates", []), ("predict", []),
        ("history", []), ("diagnostics", []), ("inspect", []), ("explain", []),
        ("branches", []), ("branch", ["1"]), ("compare", []), ("compare", ["branch", "1"]),
        ("timeline", []), ("timeline", ["0"]), ("thread", []), ("state", []),
        ("criterion", []), ("criterion", ["baseline", "25"]),
    ):
        text = dispatch(state, command, args)
        for token in re.findall(r"·[0-9a-f]{12}", text):
            assert token in known, f"{command} {args}: unresolvable identity {token}"


def test_no_view_renders_a_uuid_or_a_timestamp_as_identity():
    state = _scenario([{"temperature_c": 25}])
    dispatch(state, "select", ["baseline", "25"])
    dispatch(state, "observe", ["90", "MPa"])
    uuid_like = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}")
    for command, args in (("timeline", []), ("state", []), ("criterion", []),
                          ("inspect", []), ("history", []), ("thread", [])):
        text = dispatch(state, command, args)
        assert not uuid_like.search(text), command
        assert "·2026-" not in text  # a timestamp never appears as an identity


# -- import boundaries (sec.15) ------------------------------------------------------------------------------


def test_no_layer_beneath_the_workbench_imports_it():
    for package in ("materials", "experiment", "core", "evidence", "retrieval"):
        directory = REPO / package
        if not directory.exists():
            continue
        for path in directory.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                modules = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    modules = [node.module]
                elif isinstance(node, ast.Import):
                    modules = [a.name for a in node.names]
                for module in modules:
                    assert not module.startswith("workbench"), f"{path} imports {module}"


def test_the_cli_admits_nothing_and_computes_no_evidence_semantics():
    """Admission stays in the interaction layer; the CLI renders."""
    source = (REPO / "workbench" / "cli.py").read_text(encoding="utf-8")
    for forbidden in ("make_observation", "admit_observation", "admit_experimental_result",
                      "make_experimental_result", "put_observation", "put_record",
                      "_comparison_context", "make_derived_value"):
        assert forbidden not in source, f"cli.py performs {forbidden}"


# -- determinism (sec.17) ------------------------------------------------------------------------------------


def test_the_whole_path_is_deterministic():
    def run():
        state = _scenario([{"temperature_c": 25}, {"temperature_c": 100}],
                          formulations=("baseline", "modified"))
        for formulation in ("baseline", "modified"):
            for temperature in ("25", "100"):
                dispatch(state, "select", [formulation, temperature])
                dispatch(state, "observe", ["90", "MPa"])
        dispatch(state, "decide", [])
        return (
            tuple(sorted(o.id for o in state.pool.all_observations())),
            tuple(sorted(tuple(sorted(o.content.items()))
                         for o in state.pool.all_observations())),
            state.pool.fingerprint(),
            tuple(s.id for s in state.session.state_history),
            tuple(dispatch(state, c, a) for c, a in
                  (("criterion", []), ("state", []), ("timeline", []), ("candidates", []))),
        )

    assert run() == run()
