"""Phase 102: property-specific research criteria -- schema investigation.

RECOMMENDED CONTRACT: a scenario declares a FLAT COLLECTION of criteria,
    criteria: [Criterion(property, operator, target, context), ...]
because that collection is ALREADY what the materials layer consumes and
ALREADY what determines the programme's shape. Everything else the
workbench currently exposes (`property` + `criterion_operator` +
`criterion_target` + `contexts`) is a convenience constructor that
happens to build the Cartesian case of that collection.

WHY NOT THE ALTERNATIVES

  A  one global criterion over several properties -- INVALID. A target
     is a magnitude on one property's scale. 75 means MPa for tensile
     strength and percent for elongation; those are two engineering
     criteria, not one.

  B  property -> target -- LOSSY. It drops operator (density needs <=,
     strength needs >=) and context (the same property is criticised
     differently at 25 C and 100 C). Both are per-criterion in the
     materials layer.

  C  property -> Criterion -- INSUFFICIENT. Verified below: the algebra
     accepts SEVERAL criteria per property and returns one independent
     verdict for each. A single-valued mapping cannot express a band
     (>= 75 AND <= 120), which the algebra already evaluates today.

  D  Criterion[] -- CORRECT. It is exactly what `evaluate_program` takes,
     order is preserved and never normalised, and the collection itself
     determines which cells the programme contains.

  E  property -> Criterion[] -- redundant. It is D plus a grouping key
     already present inside each Criterion, so it adds a second place
     for the property to live and a way for the two to disagree.

KEY FINDINGS

  Criterion has NO unit field -- but its `context` is open, and its own
  docstring's example is `{"temperature": 25, "temperature_unit": "C"}`.
  Since `_comparison_context` already includes `unit` from observation
  content, a criterion disambiguates units by NAMING one in its context.
  That resolves the open question Phases 99-101 left: units need no new
  field and no conversion.

  The criteria collection IS the programme shape: dropping one criterion
  drops exactly one candidate cell. Sparse programmes are expressible
  today.

  TRAP for Phase 103: candidate generation follows the CRITERIA, while
  evidence retrieval follows `MaterialProgramQuery.properties`. A
  criterion for a property the query omits is silently accepted and
  reads INSUFFICIENT_EVIDENCE even when the pool holds that evidence.
  The two must be kept in sync by construction.
"""

import pytest

from materials.decision import Criterion, make_criterion
from materials.iteration import reevaluate_program
from materials.model_state import resolve_model_state_key
from materials.program import make_material_program_query

pytest.register_assert_rewrite("tests.test_phase101_fiber_architecture")
from tests.test_phase101_fiber_architecture import _Programme  # noqa: E402


def _verdicts(programme, criteria, formulation="baseline", query=None):
    decision = reevaluate_program(
        programme.pool, programme.engine, query or programme.query, criteria).decision
    return [
        (p.criterion.property, p.criterion.operator, p.criterion.target, p.observed_status)
        for f in decision.formulations if f.formulation.natural_key == formulation
        for p in f.properties
    ]


# -- 1. the Criterion contract ---------------------------------------------------------------------------


def test_the_criterion_contract_is_four_fields_and_no_identity():
    """It is a plain frozen value object: no id, no hash, no unit."""
    import dataclasses
    fields = {f.name: f.type for f in dataclasses.fields(Criterion)}
    assert set(fields) == {"property", "operator", "target", "context"}
    for absent in ("id", "unit", "tolerance", "priority", "weight"):
        assert absent not in fields
    criterion = make_criterion("tensile_strength", ">=", 75.0, context={"temperature_c": 25})
    assert criterion.target == 75.0 and isinstance(criterion.target, float)
    assert dict(criterion.context) == {"temperature_c": 25}


def test_an_unsupported_operator_is_refused_at_construction():
    with pytest.raises(ValueError, match="unsupported operator"):
        make_criterion("tensile_strength", "≈", 75.0)


def test_criteria_form_a_collection_the_algebra_consumes_directly():
    """`evaluate_program(program_answer, criteria)` takes a tuple, keeps
    its order, and never deduplicates or sorts it."""
    import inspect

    from materials.decision import evaluate_program
    parameters = list(inspect.signature(evaluate_program).parameters)
    assert parameters == ["program_answer", "criteria"]


# -- 2. falsifying the schema candidates -------------------------------------------------------------------


def test_A_one_global_target_across_properties_is_invalid():
    """Where it breaks: the target is a magnitude on ONE property's
    scale. The same number applied to two properties makes one of them
    meaningless, and the algebra cannot detect that."""
    programme = _Programme(properties=("tensile_strength", "elongation_at_break"),
                           contexts=({"temperature_c": 25},))
    programme.observe(
        programme.cell("baseline", "tensile_strength", {"temperature_c": 25}), 90.0, "MPa")
    programme.observe(
        programme.cell("baseline", "elongation_at_break", {"temperature_c": 25}), 12.0, "percent")

    shared = tuple(
        make_criterion(p, ">=", 75.0, context={"temperature_c": 25, "unit": u})
        for p, u in (("tensile_strength", "MPa"), ("elongation_at_break", "percent")))
    verdicts = {v[0]: v[3] for v in _verdicts(programme, shared)}
    assert verdicts["tensile_strength"] == "PASS"        # 90 >= 75 MPa, meaningful
    assert verdicts["elongation_at_break"] == "FAIL"     # 12 >= 75 percent, meaningless
    # the algebra reports it honestly and cannot know the target was nonsense:
    # nothing in Criterion records which scale 75.0 belongs to.


def test_B_a_property_to_target_mapping_loses_operator_and_context():
    """Both are genuinely per-criterion: density wants <=, strength wants
    >=, and the same property is criticised differently per context."""
    programme = _Programme(properties=("tensile_strength",),
                           contexts=({"temperature_c": 25}, {"temperature_c": 100}))
    programme.observe(
        programme.cell("baseline", "tensile_strength", {"temperature_c": 25}), 90.0, "MPa")
    programme.observe(
        programme.cell("baseline", "tensile_strength", {"temperature_c": 100}), 60.0, "MPa")

    per_context = (
        make_criterion("tensile_strength", ">=", 75.0,
                       context={"temperature_c": 25, "unit": "MPa"}),
        make_criterion("tensile_strength", ">=", 50.0,
                       context={"temperature_c": 100, "unit": "MPa"}),
    )
    statuses = [v[3] for v in _verdicts(programme, per_context)]
    assert statuses == ["PASS", "PASS"]   # different targets per context, both satisfied
    # a property -> target mapping could express neither the second target
    # nor the operator difference a density criterion would need.
    assert per_context[0].target != per_context[1].target


def test_C_one_criterion_per_property_cannot_express_a_band():
    """FALSIFIES candidate C. The algebra accepts several criteria for
    one property and returns an INDEPENDENT verdict for each."""
    programme = _Programme(properties=("tensile_strength",), contexts=({"temperature_c": 25},))
    programme.observe(
        programme.cell("baseline", "tensile_strength", {"temperature_c": 25}), 90.0, "MPa")

    band = (
        make_criterion("tensile_strength", ">=", 75.0,
                       context={"temperature_c": 25, "unit": "MPa"}),
        make_criterion("tensile_strength", "<=", 120.0,
                       context={"temperature_c": 25, "unit": "MPa"}),
        make_criterion("tensile_strength", ">=", 200.0,
                       context={"temperature_c": 25, "unit": "MPa"}),
    )
    statuses = [v[3] for v in _verdicts(programme, band)]
    assert statuses == ["PASS", "PASS", "FAIL"]
    assert len(statuses) == 3     # three criteria, three verdicts, same property


def test_multiple_criteria_are_independent_never_aggregated():
    """No conjunction, disjunction or combined verdict is produced. The
    caller composes; the algebra reports."""
    programme = _Programme(properties=("tensile_strength",), contexts=({"temperature_c": 25},))
    programme.observe(
        programme.cell("baseline", "tensile_strength", {"temperature_c": 25}), 90.0, "MPa")
    mixed = (
        make_criterion("tensile_strength", ">=", 75.0,
                       context={"temperature_c": 25, "unit": "MPa"}),
        make_criterion("tensile_strength", ">=", 200.0,
                       context={"temperature_c": 25, "unit": "MPa"}),
    )
    decision = reevaluate_program(
        programme.pool, programme.engine, programme.query, mixed).decision
    formulation = next(f for f in decision.formulations
                       if f.formulation.natural_key == "baseline")
    assert len(formulation.properties) == 2
    assert {p.observed_status for p in formulation.properties} == {"PASS", "FAIL"}
    # there is no combined field anywhere on the result
    import dataclasses
    names = {f.name for f in dataclasses.fields(type(formulation))}
    assert not {"status", "overall", "combined", "result"} & names


def test_D_the_collection_order_is_preserved_and_never_normalised():
    programme = _Programme(properties=("tensile_strength",), contexts=({"temperature_c": 25},))
    programme.observe(
        programme.cell("baseline", "tensile_strength", {"temperature_c": 25}), 90.0, "MPa")
    forward = (make_criterion("tensile_strength", ">=", 75.0, context={"temperature_c": 25, "unit": "MPa"}),
               make_criterion("tensile_strength", ">=", 200.0, context={"temperature_c": 25, "unit": "MPa"}))
    assert [v[3] for v in _verdicts(programme, forward)] == ["PASS", "FAIL"]
    assert [v[3] for v in _verdicts(programme, tuple(reversed(forward)))] == ["FAIL", "PASS"]


# -- 3/4. context and unit semantics ------------------------------------------------------------------------


def test_a_criterion_naming_its_unit_disambiguates_without_conversion():
    """The resolution of the Phases 99-101 unit question: no new field,
    no conversion. The criterion names the unit it means."""
    programme = _Programme(properties=("tensile_strength",), contexts=({"temperature_c": 25},))
    cell = programme.cell("baseline", "tensile_strength", {"temperature_c": 25})
    programme.observe(cell, 90.0, "MPa")
    programme.observe(cell, 0.09, "GPa")

    def status(context):
        return _verdicts(programme,
                         (make_criterion("tensile_strength", ">=", 75.0, context=context),))[0][3]

    assert status({"temperature_c": 25}) == "INCOMPARABLE"            # two unit groups
    assert status({"temperature_c": 25, "unit": "MPa"}) == "PASS"     # 90 >= 75 MPa
    assert status({"temperature_c": 25, "unit": "GPa"}) == "FAIL"     # 0.09 < 75 GPa
    assert status({"temperature_c": 25, "unit": "kPa"}) == "INCOMPARABLE"  # nothing in kPa


def test_a_context_free_criterion_over_several_contexts_stays_incomparable():
    programme = _Programme(properties=("tensile_strength",),
                           contexts=({"temperature_c": 25}, {"temperature_c": 100}))
    programme.observe(
        programme.cell("baseline", "tensile_strength", {"temperature_c": 25}), 90.0, "MPa")
    assert _verdicts(programme, (make_criterion("tensile_strength", ">=", 75.0),))[0][3] == "PASS"
    programme.observe(
        programme.cell("baseline", "tensile_strength", {"temperature_c": 100}), 60.0, "MPa")
    assert _verdicts(programme,
                     (make_criterion("tensile_strength", ">=", 75.0),))[0][3] == "INCOMPARABLE"


# -- 5. the property x context matrix -----------------------------------------------------------------------




# -- 5. the property x context matrix -----------------------------------------------------------------------


def _three_property_programme():
    programme = _Programme(
        properties=("tensile_strength", "elongation_at_break", "density"),
        contexts=({"temperature_c": 25}, {"temperature_c": 100}),
        formulations=("baseline", "modified"))
    programme.observe(
        programme.cell("baseline", "tensile_strength", {"temperature_c": 25}), 90.0, "MPa")
    programme.observe(
        programme.cell("baseline", "elongation_at_break", {"temperature_c": 25}), 12.0, "percent")
    programme.observe(
        programme.cell("baseline", "density", {"temperature_c": 25}), 1.2, "g_per_cm3")
    return programme


PROPERTY_SPECIFIC = (
    make_criterion("tensile_strength", ">=", 75.0,
                   context={"temperature_c": 25, "unit": "MPa"}),
    make_criterion("elongation_at_break", ">=", 8.0,
                   context={"temperature_c": 25, "unit": "percent"}),
    make_criterion("density", "<=", 1.4,
                   context={"temperature_c": 25, "unit": "g_per_cm3"}),
)


def test_three_properties_evaluate_on_their_own_incommensurate_scales():
    """75 MPa, 8 percent and 1.4 g/cm3 are three engineering criteria.
    Each is satisfied on its own scale; none is compared with another."""
    programme = _three_property_programme()
    assert len(programme.candidates.candidates) == 12         # 2 x 3 x 2
    verdicts = {v[0]: v[3] for v in _verdicts(programme, PROPERTY_SPECIFIC)}
    assert verdicts == {"tensile_strength": "PASS",
                        "elongation_at_break": "PASS",
                        "density": "PASS"}
    # and the operators genuinely differ per property
    assert {c.operator for c in PROPERTY_SPECIFIC} == {">=", "<="}


def test_a_criterion_never_evaluates_another_property():
    programme = _three_property_programme()
    for criterion in PROPERTY_SPECIFIC:
        results = _verdicts(programme, (criterion,))
        assert len(results) == 1
        assert results[0][0] == criterion.property


def test_declaring_a_further_property_leaves_existing_verdicts_unchanged():
    before = _verdicts(_three_property_programme(), (PROPERTY_SPECIFIC[0],))
    wider = _Programme(
        properties=("tensile_strength", "elongation_at_break", "density", "melt_index"),
        contexts=({"temperature_c": 25}, {"temperature_c": 100}),
        formulations=("baseline", "modified"))
    wider.observe(
        wider.cell("baseline", "tensile_strength", {"temperature_c": 25}), 90.0, "MPa")
    assert _verdicts(wider, (PROPERTY_SPECIFIC[0],))[0][3] == before[0][3] == "PASS"


# -- 9. sparse programmes ------------------------------------------------------------------------------------


def test_the_criteria_collection_is_the_programme_shape():
    """Dropping one criterion drops exactly one candidate cell. Sparse,
    non-Cartesian programmes are expressible today."""
    full = (
        make_criterion("tensile_strength", ">=", 75.0, context={"temperature_c": 25}),
        make_criterion("tensile_strength", ">=", 75.0, context={"temperature_c": 100}),
        make_criterion("elongation_at_break", ">=", 8.0, context={"temperature_c": 25}),
        make_criterion("elongation_at_break", ">=", 8.0, context={"temperature_c": 100}),
    )
    programme = _Programme(properties=("tensile_strength", "elongation_at_break"),
                           contexts=({"temperature_c": 25}, {"temperature_c": 100}),
                           formulations=("baseline",))
    assert len(programme.candidates.candidates) == 4

    from materials.candidates import generate_candidates
    sparse_iteration = reevaluate_program(
        programme.pool, programme.engine, programme.query, full[:3])
    sparse = generate_candidates(sparse_iteration.specification)
    assert len(sparse.candidates) == 3
    cells = {(c.property, tuple(sorted(c.target_context.items()))) for c in sparse.candidates}
    assert ("elongation_at_break", (("temperature_c", 100),)) not in cells


def test_an_unoccupied_coordinate_distinguishes_two_kinds_of_absence():
    """A three-way distinction the schema must not blur:

      occupied coordinate            -> PASS / FAIL
      property has evidence, but NOT
        at this criterion's context   -> INCOMPARABLE
      property has no evidence at all -> INSUFFICIENT_EVIDENCE
    """
    programme = _Programme(properties=("tensile_strength", "elongation_at_break"),
                           contexts=({"temperature_c": 25}, {"temperature_c": 100}))
    programme.observe(
        programme.cell("baseline", "tensile_strength", {"temperature_c": 25}), 90.0, "MPa")

    occupied = make_criterion("tensile_strength", ">=", 75.0,
                              context={"temperature_c": 25, "unit": "MPa"})
    other_context = make_criterion("tensile_strength", ">=", 75.0,
                                   context={"temperature_c": 100, "unit": "MPa"})
    untouched_property = make_criterion("elongation_at_break", ">=", 8.0,
                                        context={"temperature_c": 25, "unit": "percent"})

    assert _verdicts(programme, (occupied,))[0][3] == "PASS"
    assert _verdicts(programme, (other_context,))[0][3] == "INCOMPARABLE"
    assert _verdicts(programme, (untouched_property,))[0][3] == "INSUFFICIENT_EVIDENCE"


def test_no_candidate_is_created_for_a_coordinate_nobody_declared():
    programme = _Programme(properties=("tensile_strength",), contexts=({"temperature_c": 25},))
    declared = {(c.property, tuple(sorted(c.target_context.items())))
                for c in programme.candidates.candidates}
    assert declared == {("tensile_strength", (("temperature_c", 25),))}


# -- the Phase 103 trap --------------------------------------------------------------------------------------


def test_query_properties_and_criteria_properties_must_be_kept_in_sync():
    """TRAP. Candidate generation follows the CRITERIA; evidence
    retrieval follows `MaterialProgramQuery.properties`. With the SAME
    pool, the SAME evidence and the SAME criterion, the verdict changes
    depending on whether the query retrieved that property."""
    programme = _Programme(properties=("tensile_strength", "elongation_at_break"),
                           contexts=({"temperature_c": 25},))
    programme.observe(
        programme.cell("baseline", "elongation_at_break", {"temperature_c": 25}), 12.0, "percent")
    criterion = (make_criterion("elongation_at_break", ">=", 8.0,
                                context={"temperature_c": 25, "unit": "percent"}),)

    assert _verdicts(programme, criterion)[0][3] == "PASS"

    narrow = make_material_program_query(
        list(("baseline", "modified")), "process-std-190c", ("tensile_strength",))
    assert _verdicts(programme, criterion, query=narrow)[0][3] == "INSUFFICIENT_EVIDENCE"


# -- 7. scenario identity ------------------------------------------------------------------------------------


def test_changing_only_the_target_moves_the_action_never_the_coordinate():
    """`ResearchScenario` is configuration. The target participates in
    candidate (action) identity but never in the cell coordinate."""
    from materials.candidates import generate_candidates

    def candidates_for(target):
        programme = _Programme(properties=("tensile_strength",),
                               contexts=({"temperature_c": 25},), formulations=("baseline",))
        iteration = reevaluate_program(
            programme.pool, programme.engine, programme.query,
            (make_criterion("tensile_strength", ">=", target, context={"temperature_c": 25}),))
        return generate_candidates(iteration.specification).candidates

    lenient, strict = candidates_for(75.0), candidates_for(999.0)
    assert [c.id for c in lenient] != [c.id for c in strict]
    cells = lambda cs: {resolve_model_state_key(c.formulation.id, c.property, c.target_context)  # noqa: E731
                        for c in cs}
    assert cells(lenient) == cells(strict)


# -- 8. decision separation ----------------------------------------------------------------------------------


def test_decide_ranks_actions_across_properties_and_never_the_properties():
    """Utility orders WHICH EXPERIMENT TO RUN. It is a policy quantity
    over actions; it never asserts that one property beats another."""
    from workbench.interaction import evaluate_decision

    programme = _three_property_programme()
    result = evaluate_decision(
        programme.candidates, programme.session.state, programme.session.iteration)
    assert len(result.optimizations) == 12
    selected = [o for o in result.optimizations if o.status == "SELECTED"]
    assert len(selected) == 1

    # the selection is an ACTION on one cell, and its utility came from the
    # workbench's explicit exploration policy, not from any property's scale
    chosen = next(c for c in programme.candidates.candidates
                  if c.id == selected[0].candidate_id)
    assert chosen.property in ("tensile_strength", "elongation_at_break", "density")
    for option in result.optimizations:
        assert option.utility.information_value.expected_information_gain == "NOT_DETERMINABLE"


def test_no_cross_property_comparison_appears_anywhere_in_the_decision():
    from materials.trajectory import compare_predictions

    programme = _three_property_programme()
    tensile = programme.cell("baseline", "tensile_strength", {"temperature_c": 25})
    density = programme.cell("baseline", "density", {"temperature_c": 25})
    with pytest.raises(AssertionError, match="same ActionCandidate"):
        compare_predictions(programme.session.predict(tensile),
                            programme.session.predict(density))
