"""Phase 103: criteria-driven research scenario.

`ResearchScenario.criteria` is now the SOLE stored declaration. The
single-property fields it used to store -- `property`, `contexts`,
`criterion_operator`, `criterion_target` -- became derived views over
the criteria, so they cannot drift from what is actually evaluated, and
they raise rather than guess when the scenario is richer than the
convenience form can express.

The evidence query's property set is DERIVED from the criteria. That
derivation is the point of the phase: Phase 102 demonstrated that
letting the two declarations drift turns a real PASS into
INSUFFICIENT_EVIDENCE with the same pool, evidence and criterion.
"""

import json
from pathlib import Path

import pytest

from materials.model_state import resolve_model_state_key
from workbench import theme
from workbench.cli import dispatch
from workbench.interaction import (
    DEFAULT_CRITERION_TARGET, ResearchScenario, WorkbenchState, bootstrap_research_scenario,
)

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
LEGACY = EXAMPLES / "polymer_tensile_strength.json"
MULTI = EXAMPLES / "polymer_multi_property.json"


def _clock():
    n = {"i": 0}

    def clock() -> str:
        n["i"] += 1
        return f"2026-08-27T01:{n['i']:02d}:00Z"

    return clock


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _load(path) -> WorkbenchState:
    with open(path, encoding="utf-8") as f:
        return bootstrap_research_scenario(json.load(f), clock=_clock())


def _criteria(*specs):
    return [{"property": p, "operator": o, "target": t, "context": dict(c)} for p, o, t, c in specs]


def _scenario(specs, formulations=("baseline",), name="phase 103"):
    return ResearchScenario.from_config({
        "name": name, "process": "process-std-190c",
        "formulations": list(formulations), "criteria": specs,
    })


# -- canonical representation ------------------------------------------------------------------------------


def test_criteria_are_the_only_stored_declaration():
    scenario = _scenario(_criteria(("tensile_strength", ">=", 75.0, {"temperature_c": 25})))
    assert set(vars(scenario)) == {"name", "formulations", "criteria", "process"}
    assert len(scenario.criteria) == 1


def test_the_convenience_views_are_derived_not_stored():
    scenario = _scenario(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}),
        ("tensile_strength", ">=", 60.0, {"temperature_c": 100})))
    assert scenario.property == "tensile_strength"
    assert scenario.properties == ("tensile_strength",)
    assert [dict(c) for c in scenario.contexts] == [{"temperature_c": 25}, {"temperature_c": 100}]
    assert scenario.criterion_operator == ">="
    # the targets differ, so the single-target view refuses rather than guessing
    with pytest.raises(ValueError, match="read `.criteria`"):
        _ = scenario.criterion_target


def test_a_multi_property_scenario_refuses_the_single_property_view():
    scenario = _scenario(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}),
        ("density", "<=", 1.2, {"temperature_c": 25})))
    assert scenario.properties == ("tensile_strength", "density")   # author order
    with pytest.raises(ValueError, match="read `.criteria`"):
        _ = scenario.property


# -- query derivation, the central invariant ----------------------------------------------------------------


def test_the_query_property_set_is_derived_from_the_criteria():
    built = bootstrap_research_scenario(_scenario(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}),
        ("elongation_at_break", ">=", 10.0, {"temperature_c": 25}),
        ("density", "<=", 1.2, {"temperature_c": 25}))), clock=_clock())
    assert set(built.session.iteration.query.properties) == {
        "tensile_strength", "elongation_at_break", "density"}


def test_changing_the_criteria_changes_the_query():
    def properties_for(specs):
        built = bootstrap_research_scenario(_scenario(specs), clock=_clock())
        return set(built.session.iteration.query.properties)

    assert properties_for(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}))) == {"tensile_strength"}
    assert properties_for(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}),
        ("density", "<=", 1.2, {"temperature_c": 25}))) == {"tensile_strength", "density"}


def test_there_is_no_second_property_list_to_maintain():
    """The scenario has no independently configurable property field, so
    the Phase 102 drift trap is unreachable through normal construction."""
    with pytest.raises(ValueError, match="either 'criteria' or the single-property form"):
        ResearchScenario.from_config({
            "name": "x", "process": "process-std-190c", "formulations": ["baseline"]})
    with pytest.raises(ValueError, match="declares both"):
        ResearchScenario.from_config({
            "name": "x", "formulations": ["baseline"], "property": "tensile_strength",
            "contexts": [{"temperature_c": 25}],
            "criteria": _criteria(("density", "<=", 1.2, {}))})


def test_every_criterion_property_is_retrieved_by_the_query():
    built = _load(MULTI)
    declared = {c.property for c in built.scenario.criteria}
    assert declared <= set(built.session.iteration.query.properties)


# -- legacy compatibility ------------------------------------------------------------------------------------


def test_the_legacy_scenario_still_loads_and_behaves_identically():
    built = _load(LEGACY)
    scenario = built.scenario
    assert scenario.property == "tensile_strength"
    assert scenario.criterion_operator == ">="
    assert len(scenario.criteria) == 3            # one per declared context
    assert len(built.list_candidates()) == 9      # 3 formulations x 3 criteria
    assert {c.property for c in scenario.criteria} == {"tensile_strength"}


def test_legacy_and_canonical_forms_produce_identical_programmes():
    """The legacy form IS the single-property Cartesian case, so the two
    must agree on every identity, not merely on counts."""
    legacy = bootstrap_research_scenario({
        "name": "same", "process": "process-std-190c", "formulations": ["baseline", "modified"],
        "property": "tensile_strength", "criterion": {"operator": ">=", "target": 80.0},
        "contexts": [{"temperature_c": 25}, {"temperature_c": 80}],
    }, clock=_clock())
    canonical = bootstrap_research_scenario({
        "name": "same", "process": "process-std-190c", "formulations": ["baseline", "modified"],
        "criteria": _criteria(
            ("tensile_strength", ">=", 80.0, {"temperature_c": 25}),
            ("tensile_strength", ">=", 80.0, {"temperature_c": 80})),
    }, clock=_clock())

    assert [c.id for c in legacy.list_candidates()] == [c.id for c in canonical.list_candidates()]
    assert legacy.session.state.id == canonical.session.state.id
    assert legacy.pool.fingerprint() == canonical.pool.fingerprint()
    assert legacy.scenario.criteria == canonical.scenario.criteria


def test_a_defaulted_legacy_scenario_still_defaults():
    scenario = ResearchScenario.from_config({
        "name": "minimal", "formulations": ["baseline"], "property": "tensile_strength",
        "contexts": [{"temperature_c": 25}]})
    assert scenario.criterion_operator == ">="
    assert scenario.criterion_target == DEFAULT_CRITERION_TARGET


# -- duplicates, order, contexts (falsification A-L) ---------------------------------------------------------


def test_two_criteria_for_one_property_are_both_kept():
    """(C, I) Phase 102 proved a band is legitimate. Nothing may collapse
    it -- not the schema, not a dict, not the candidate layer."""
    scenario = _scenario(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}),
        ("tensile_strength", "<=", 120.0, {"temperature_c": 25})))
    assert len(scenario.criteria) == 2
    assert scenario.properties == ("tensile_strength",)
    built = bootstrap_research_scenario(scenario, clock=_clock())
    decision, _ = built.evaluate_criteria()
    statuses = [p.observed_status for f in decision.formulations for p in f.properties]
    assert len(statuses) == 2       # one verdict per criterion, not per property


def test_criterion_order_is_the_authors_order():
    """(J) order is preserved, never sorted."""
    forward = _scenario(_criteria(
        ("density", "<=", 1.2, {"temperature_c": 25}),
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25})))
    assert [c.property for c in forward.criteria] == ["density", "tensile_strength"]
    assert forward.properties == ("density", "tensile_strength")
    reverse = _scenario(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}),
        ("density", "<=", 1.2, {"temperature_c": 25})))
    assert reverse.properties == ("tensile_strength", "density")


def test_two_contexts_for_one_property_stay_distinct_coordinates():
    """(D) and context never leaks between criteria."""
    built = bootstrap_research_scenario(_scenario(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}),
        ("tensile_strength", ">=", 60.0, {"temperature_c": 100}))), clock=_clock())
    cells = {resolve_model_state_key(c.formulation.id, c.property, c.target_context)
             for c in built.list_candidates()}
    assert len(cells) == 2

    dispatch(built, "select", ["baseline", "25"])
    dispatch(built, "observe", ["90", "MPa"])
    decision, _ = built.evaluate_criteria()
    verdicts = {p.criterion.context["temperature_c"]: p.observed_status
                for f in decision.formulations for p in f.properties}
    assert verdicts == {25: "PASS", 100: "INCOMPARABLE"}


def test_different_operators_per_property_are_preserved():
    """(B) density wants <=, strength wants >=."""
    built = bootstrap_research_scenario(_scenario(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}),
        ("density", "<=", 1.2, {"temperature_c": 25}))), clock=_clock())
    dispatch(built, "select", ["baseline", "tensile_strength", "25"])
    dispatch(built, "observe", ["90", "MPa"])
    dispatch(built, "select", ["baseline", "density", "25"])
    dispatch(built, "observe", ["1.1", "g_per_cm3"])
    decision, _ = built.evaluate_criteria()
    verdicts = {p.criterion.property: p.observed_status
                for f in decision.formulations for p in f.properties}
    assert verdicts == {"tensile_strength": "PASS", "density": "PASS"}


def test_a_shared_numeric_target_never_crosses_properties():
    """(A) 75 must mean 75 on each property's own scale."""
    built = bootstrap_research_scenario(_scenario(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}),
        ("elongation_at_break", ">=", 75.0, {"temperature_c": 25}))), clock=_clock())
    dispatch(built, "select", ["baseline", "tensile_strength", "25"])
    dispatch(built, "observe", ["90", "MPa"])
    dispatch(built, "select", ["baseline", "elongation_at_break", "25"])
    dispatch(built, "observe", ["12", "percent"])
    decision, _ = built.evaluate_criteria()
    verdicts = {p.criterion.property: p.observed_status
                for f in decision.formulations for p in f.properties}
    assert verdicts == {"tensile_strength": "PASS", "elongation_at_break": "FAIL"}


def test_a_context_free_criterion_is_accepted():
    """(F)"""
    scenario = _scenario([{"property": "tensile_strength", "operator": ">=", "target": 75.0}])
    assert dict(scenario.criteria[0].context) == {}
    assert len(bootstrap_research_scenario(scenario, clock=_clock()).list_candidates()) == 1


def test_multiple_formulations_multiply_the_criteria():
    """(H) candidates = formulations x criteria."""
    built = bootstrap_research_scenario(_scenario(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}),
        ("density", "<=", 1.2, {"temperature_c": 25})),
        formulations=("baseline", "modified", "high_filler")), clock=_clock())
    assert len(built.list_candidates()) == 6
    assert built.scenario.describe_candidate_space() == "3 formulation(s) x 2 criteria"


# -- sparse programmes -----------------------------------------------------------------------------------------


def test_a_sparse_programme_creates_no_absent_coordinate():
    """(E) tensile at both contexts, elongation at one only."""
    built = bootstrap_research_scenario(_scenario(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}),
        ("tensile_strength", ">=", 60.0, {"temperature_c": 100}),
        ("elongation_at_break", ">=", 10.0, {"temperature_c": 25}))), clock=_clock())
    declared = {(c.property, dict(c.target_context)["temperature_c"])
                for c in built.list_candidates()}
    assert declared == {("tensile_strength", 25), ("tensile_strength", 100),
                        ("elongation_at_break", 25)}
    assert ("elongation_at_break", 100) not in declared
    # and `state` enumerates exactly the declared cells
    assert dispatch(built, "state", []).count("├ prediction") == 3


# -- invalid criteria ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("entry,message", [
    ({"operator": ">=", "target": 1.0}, "missing required field 'property'"),
    ({"property": "p", "target": 1.0}, "missing required field 'operator'"),
    ({"property": "p", "operator": ">="}, "missing required field 'target'"),
    ({"property": "", "operator": ">=", "target": 1.0}, "'property' must be a non-empty string"),
    ({"property": "p", "operator": "", "target": 1.0}, "'operator' must be a non-empty string"),
    ({"property": "p", "operator": ">=", "target": "high"}, "'target' must be a number"),
    ({"property": "p", "operator": ">=", "target": True}, "'target' must be a number"),
    ({"property": "p", "operator": ">=", "target": 1.0, "context": 25}, "'context' must be a mapping"),
])
def test_a_malformed_criterion_is_rejected_with_its_index(entry, message):
    with pytest.raises(ValueError, match="criteria\\[0\\]"):
        _scenario([entry])
    with pytest.raises(ValueError, match=message.replace("[", "\\[").replace("]", "\\]")):
        _scenario([entry])


def test_an_unsupported_operator_is_rejected_by_the_materials_validator():
    """The CLI never duplicates operator validation; `make_criterion`
    owns it and the scenario boundary only names the offending index."""
    with pytest.raises(ValueError, match="unsupported operator"):
        _scenario([{"property": "p", "operator": "≈", "target": 1.0}])


def test_an_empty_criteria_collection_is_rejected():
    with pytest.raises(ValueError, match="non-empty list of criterion mappings"):
        _scenario([])
    with pytest.raises(ValueError, match="at least one criterion"):
        ResearchScenario(name="x", formulations=("baseline",), criteria=())


# -- the criterion-context collision with the measurement keys ---------------------------------------------------


def test_a_criterion_context_may_not_use_a_measurement_key():
    """A criterion context serves TWO roles in the workbench path: it is
    the cell coordinate AND the evidence-matching context. Phase 102
    showed that naming `unit` in a criterion context disambiguates mixed
    units; Phase 98's guard forbids a target_context that would overwrite
    the measurement. Both are right, and they collide here -- so the
    collision is refused loudly rather than silently corrupting a value."""
    built = bootstrap_research_scenario(_scenario(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25, "unit": "MPa"}))), clock=_clock())
    dispatch(built, "select", ["1"])
    text = dispatch(built, "observe", ["90", "MPa"])
    assert "may not use the measurement key" in text


# -- presentation ------------------------------------------------------------------------------------------------


def test_the_scenario_view_enumerates_every_criterion():
    built = _load(MULTI)
    text = dispatch(built, "scenario", [])
    assert "DECLARED CRITERIA" in text
    for criterion in built.scenario.criteria:
        assert criterion.property in text
    assert "evaluated independently" in text
    assert "None is compared with another." in text


def test_dense_tables_name_the_property_when_several_are_declared():
    multi = _load(MULTI)
    single = _load(LEGACY)
    assert "tensile_strength" in dispatch(multi, "criterion", [])
    assert "density" in dispatch(multi, "criterion", [])
    # a single-property scenario keeps the compact form
    listing = dispatch(single, "decide", [])
    assert "baseline · 25 C" in listing


def test_the_no_match_guidance_names_the_properties():
    built = _load(MULTI)
    text = dispatch(built, "select", ["baseline", "elongation", "25"])
    assert "PROPERTIES" in text
    assert "elongation_at_break" in text
    assert "select <formulation> <property> <context>" in text


# -- decision layer ------------------------------------------------------------------------------------------------


def test_decide_over_several_properties_selects_one_action():
    built = _load(MULTI)
    dispatch(built, "select", ["baseline", "tensile_strength", "25"])
    dispatch(built, "observe", ["90", "MPa"])
    text = dispatch(built, "decide", [])
    assert built.last_decision is not None
    selected = [o for o in built.last_decision.optimizations if o.status == "SELECTED"]
    assert len(selected) == 1
    lowered = text.lower()
    for phrase in ("better", "worse", "superior", "ranking", "outperform"):
        assert phrase not in lowered
    assert "ADVISORY ONLY" in text


def test_explain_remains_valid_across_properties():
    built = _load(MULTI)
    dispatch(built, "decide", [])
    text = dispatch(built, "explain", [])
    assert "highest determinate utility among eligible candidates" in text
    assert "exploration policy" in text


# -- determinism -----------------------------------------------------------------------------------------------------


def test_the_multi_property_scenario_is_deterministic():
    def run():
        built = _load(MULTI)
        dispatch(built, "select", ["baseline", "tensile_strength", "25"])
        dispatch(built, "observe", ["90", "MPa"])
        return (tuple(c.id for c in built.list_candidates()),
                built.pool.fingerprint(), built.session.state.id,
                dispatch(built, "criterion", []), dispatch(built, "scenario", []))

    assert run() == run()


def test_criteria_order_determines_candidate_order_deterministically():
    a = bootstrap_research_scenario(_scenario(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}),
        ("density", "<=", 1.2, {"temperature_c": 25}))), clock=_clock())
    b = bootstrap_research_scenario(_scenario(_criteria(
        ("tensile_strength", ">=", 75.0, {"temperature_c": 25}),
        ("density", "<=", 1.2, {"temperature_c": 25}))), clock=_clock())
    assert [c.id for c in a.list_candidates()] == [c.id for c in b.list_candidates()]
