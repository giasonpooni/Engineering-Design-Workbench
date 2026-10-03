"""Phase 106: what separates "this context has an ORDER" from
"differences between these contexts are scientifically MEANINGFUL".

VERDICT: SURVIVES -- a measurement-scale distinction can be held
externally without touching evidence identity, and it bounds exactly one
thing: which arithmetic on the COORDINATE is invariant. It authorizes
nothing about the response.

THE ANSWER, IN ONE LINE
-----------------------
The additional information is not a richer value type. It is a declared
GROUP OF ADMISSIBLE TRANSFORMATIONS, plus the operational definition of
the measurement that justifies choosing that group.

    nominal   any bijection            equality survives, nothing else
    ordinal   any strictly monotone f  order and the SIGN of a difference
    interval  x' = a*x + b, a > 0      + the RATIO OF DIFFERENCES
    ratio     x' = a*x,     a > 0      + the RATIO OF VALUES

Computed, not assumed (see the parametrised tests below). Two results
are worth stating because they are usually got wrong:

  * `|b-a| < |c-b|` -- merely COMPARING two differences -- is already an
    INTERVAL statement. `x**3` and `ln x` happen to preserve it for
    25/40/100, but the strictly increasing piecewise-linear map sending
    (25, 40, 100) to (0, 100, 101) reverses it. Ordinal admissibility
    gives no guarantee.

  * NO scale makes the NUMBER `b - a` invariant. C -> K preserves 15 only
    because its scale factor is 1; C -> F sends it to 27, and MPa -> kPa
    to 15000. At interval scale the invariant content of "difference" is
    the RATIO of differences; at ratio scale, additionally the ratio of
    values. "dT = 15" is never a fact on its own.

THE LADDER, CORRECTED
---------------------
The proposed ladder is not a chain of valid implications. What holds:

    equality -> nominal distinction        VALID (the same thing)
    nominal  -> order                      INVALID
    order    -> difference                 INVALID (the counterexample above)
    difference -> ratio                    INVALID (Celsius: x-y yes, x/y no)
    ratio    -> a metric on the coordinate VALID -- but not a UNIQUE one:
                |x-y|, sqrt|x-y| and |x-y|/(1+|x-y|) are all metrics.
    distance -> metric                     INVALID: (x-y)**2 is non-negative,
                symmetric, zero iff equal, and FAILS the triangle inequality.
    metric   -> topology                   VALID but FORGETFUL: |x-y| and
                |x-y|/(1+|x-y|) are different functions inducing the same
                topology, so the topology cannot recover the metric.
    topology -> geometry                   INVALID: no lengths, no angles.

And the rung that matters most is not on the list at all: every rung
above lives on the COORDINATE. None of them reaches the RESPONSE.

COORDINATE SEMANTICS vs RESPONSE SEMANTICS
------------------------------------------
`Observation.content` is one flat mapping holding both:

    {"property": "tensile_strength", "value": 90.0, "unit": "MPa",
     "temperature_c": 25}

`_comparison_context` splits it by ROLE -- everything except `property`
and the value key -- never by scale. `unit` (a RESPONSE descriptor) and
`temperature_c` (a COORDINATE) sit side by side with nothing marking
which is which, and the record asserts neither that tensile_strength is
ratio-scale nor that temperature_c is interval-scale. Those are two
INDEPENDENT facts and the architecture records neither.

So even granting temperature a full metric, the architecture may NOT
infer that 40 C is "closer" to 25 C than 100 C for aggregation,
prediction transfer, ranking or interpolation. Phase 104 already
falsified that on the response side (a cure peak reverses it). What
would be required is a further object: an admitted CLAIM that the
property is, say, Lipschitz-continuous in the coordinate with a stated
modulus, carrying its own provenance -- i.e. scientific evidence, of the
kind `materials/` already demands. Not created here.

WHAT IS IDENTITY-BEARING, AND WHY THE LINE FALLS THERE
------------------------------------------------------
`unit` IS part of identity: MPa, GPa and no-unit give three different
`Observation.id`s, and `unit` survives into the comparison context, so
three encodings of one physical fact never pool. Likewise 25 C and
298.15 K are different cells -- and so, sharply, are `25` and `25.0`,
because canonical JSON encodes int and float differently.

That is the line: the ENCODING is evidence -- "we recorded 90 MPa at
25 C" is a fact about the measurement event, and changing it changes the
record. The LICENSED ALGEBRA is not evidence -- declaring temperature_c
interval-scale changes no record and must change no id. Were a scale
declaration identity-bearing, re-declaring a coordinate from ordinal to
interval, with no experiment performed, would mint new cell keys and
orphan every existing sample. Immutability of evidence REQUIRES
interpretation to be non-identity-bearing -- and that is exactly why it
can authorize nothing: having no evidential standing and having no
identity are the same property.

UNITS ARE NOT SCALE
-------------------
Four things this phase keeps apart, and production already keeps apart:

    scale type    which transformations preserve meaning
    unit          the recorded encoding of a magnitude
    conversion    a claimed equivalence between two encodings
    comparability whether two values may enter one statistic

A scale declaration would justify NO conversion. "Ratio-scale" says
x' = a*x preserves meaning; it does not say which `a` maps MPa to kPa.
That number is a separate physical claim. Today a criterion silent about
`unit` matches every unit group and `_status_for_groups` returns
INCOMPARABLE rather than a false PASS -- the honest outcome, already
implemented.

FOUR SENSES OF "RANK", KEPT APART
---------------------------------
    ordinal rank        position in a declared order over context values
                        (Phase 104). Lossy: ranking IS the canonical
                        strictly-monotone map, so applying it to an
                        interval quantity DESTROYS the ratio of
                        differences that was legitimately there.
    measurement magnitude the interval/ratio value itself. Not recoverable
                        from rank.
    authority rank      Phase 105: does not exist, and should not.
    execution priority  `CandidateRanking.rank`, recomputed from utility.

CONSEQUENCE FOR PRODUCTION: none. Zero production changes in this phase.
The smallest future abstraction is a RELATION, not a type: a
scenario-level declaration naming, per context key, the group of
transformations the author asserts preserve that coordinate's meaning --
consulted only to REFUSE an operation, never to enable one, and never
reachable from any hash.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

from evidence.identity import content_hash
from evidence.types import make_observation
from materials.analysis import _comparison_context, _group_by_comparison_context
from materials.decision import INCOMPARABLE, PASS, Criterion, _matching_groups, _status_for_groups
from materials.model_state import resolve_model_state_key
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("evidence", "retrieval", "materials", "experiment", "workbench")

V = (25.0, 40.0, 100.0)


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


# -- the admissible-transformation groups ---------------------------------------------------------

NOMINAL = lambda x: {25.0: 7.0, 40.0: 2.0, 100.0: 5.0}[x]          # a bijection
ORDINAL_CUBE = lambda x: x ** 3                                     # strictly monotone
ORDINAL_LOG = math.log                                              # strictly monotone


def ORDINAL_KINK(x):
    """Strictly increasing, piecewise linear: (25, 40, 100) -> (0, 100, 101).
    Ordinal-admissible, and it REVERSES the comparison of differences."""
    return (x - 25.0) * (100.0 / 15.0) if x <= 40.0 else 100.0 + (x - 40.0) / 60.0


INTERVAL_F = lambda x: 1.8 * x + 32                                 # Celsius -> Fahrenheit
INTERVAL_K = lambda x: x + 273.15                                   # Celsius -> Kelvin
RATIO_SCALE = lambda x: 1000.0 * x                                  # MPa -> kPa


def _ops(values):
    a, b, c = values
    return {
        "order": a < b < c,
        "sign_of_difference": (b - a) > 0,
        "value_of_difference": round(b - a, 6),
        "ratio_of_differences": round((b - a) / (c - b), 6),
        # None when the denominator is zero -- NOT_DETERMINABLE, never 0.
        # That a ratio can be undefined is itself the point: a ratio needs a
        # meaningful, non-arbitrary zero, which is exactly what ratio scale
        # supplies and interval scale does not.
        "ratio_of_values": round(b / a, 6) if a != 0 else None,
        "comparison_of_differences": abs(b - a) < abs(c - b),
    }


BASE = _ops(V)


def _survives(transform, operation) -> bool:
    return _ops(tuple(transform(x) for x in V))[operation] == BASE[operation]


# -- 1/11. what each scale's transformations preserve ---------------------------------------------


@pytest.mark.parametrize("operation", sorted(BASE))
def test_nominal_relabelling_destroys_everything_but_equality(operation):
    assert not _survives(NOMINAL, operation)


@pytest.mark.parametrize("transform", [ORDINAL_CUBE, ORDINAL_LOG, ORDINAL_KINK])
@pytest.mark.parametrize("operation", ["order", "sign_of_difference"])
def test_ordinal_preserves_order_and_the_sign_of_a_difference(transform, operation):
    assert _survives(transform, operation)


@pytest.mark.parametrize("transform", [ORDINAL_CUBE, ORDINAL_LOG, ORDINAL_KINK])
@pytest.mark.parametrize("operation", ["value_of_difference", "ratio_of_differences", "ratio_of_values"])
def test_ordinal_destroys_every_magnitude_statement(transform, operation):
    assert not _survives(transform, operation)


def test_comparing_two_differences_is_already_an_interval_statement():
    """THE key correction. `x**3` and `ln x` preserve `|b-a| < |c-b|` by
    accident of their curvature; a strictly increasing piecewise-linear
    map reverses it. Ordinal admissibility guarantees nothing here."""
    assert _survives(ORDINAL_CUBE, "comparison_of_differences")
    assert _survives(ORDINAL_LOG, "comparison_of_differences")
    assert not _survives(ORDINAL_KINK, "comparison_of_differences")
    kinked = tuple(ORDINAL_KINK(x) for x in V)
    assert kinked[0] < kinked[1] < kinked[2]        # genuinely monotone
    assert _survives(INTERVAL_F, "comparison_of_differences")
    assert _survives(RATIO_SCALE, "comparison_of_differences")


@pytest.mark.parametrize("transform", [INTERVAL_F, INTERVAL_K, RATIO_SCALE])
def test_interval_and_ratio_preserve_the_ratio_of_differences(transform):
    assert _survives(transform, "ratio_of_differences")


@pytest.mark.parametrize("transform", [INTERVAL_F, INTERVAL_K])
def test_interval_destroys_the_ratio_of_values(transform):
    """40/25 = 1.6 in Celsius, 1.35 in Fahrenheit, 1.05 in Kelvin.
    x - y is meaningful; x / y is not."""
    assert not _survives(transform, "ratio_of_values")


def test_ratio_scale_is_exactly_what_preserves_the_ratio_of_values():
    assert _survives(RATIO_SCALE, "ratio_of_values")
    assert not _survives(INTERVAL_F, "ratio_of_values")


def test_no_scale_makes_the_number_of_a_difference_invariant():
    """C -> K preserves 15 only because its scale factor is 1."""
    assert _survives(INTERVAL_K, "value_of_difference")          # a = 1
    assert not _survives(INTERVAL_F, "value_of_difference")      # a = 1.8
    assert not _survives(RATIO_SCALE, "value_of_difference")     # a = 1000
    assert BASE["value_of_difference"] == 15.0
    assert round(INTERVAL_F(40.0) - INTERVAL_F(25.0), 6) == 27.0


# -- 7. difference, distance, metric --------------------------------------------------------------


def _metric_axioms(d, points):
    return {
        "non_negativity": all(d(x, y) >= 0 for x in points for y in points),
        "identity": all((d(x, y) == 0) == (x == y) for x in points for y in points),
        "symmetry": all(d(x, y) == d(y, x) for x in points for y in points),
        "triangle": all(
            d(x, z) <= d(x, y) + d(y, z) + 1e-12
            for x in points for y in points for z in points
        ),
    }


@pytest.mark.parametrize("d", [
    lambda x, y: abs(x - y),
    lambda x, y: math.sqrt(abs(x - y)),
    lambda x, y: abs(x - y) / (1 + abs(x - y)),
])
def test_a_meaningful_difference_yields_A_metric_but_never_THE_metric(d):
    assert all(_metric_axioms(d, V).values())


def test_a_distance_like_function_need_not_be_a_metric():
    """(x-y)**2 is non-negative, symmetric and zero iff equal -- and fails
    the triangle inequality. distance != metric, verified."""
    axioms = _metric_axioms(lambda x, y: (x - y) ** 2, V)
    assert axioms["non_negativity"] and axioms["identity"] and axioms["symmetry"]
    assert not axioms["triangle"]


def test_different_metrics_are_different_functions():
    """|x-y| and |x-y|/(1+|x-y|) induce the SAME topology on the line, so
    a topology cannot recover the metric that produced it. metric ->
    topology is valid and forgetful."""
    a, b = V[0], V[2]
    assert abs(a - b) != abs(a - b) / (1 + abs(a - b))


# -- 3. numeric representation is not measurement ------------------------------------------------


ADVERSARIAL = [
    ("batch_id", 100, 200),
    ("sample_id", 100, 200),
    ("reactor_number", 1, 2),
    ("material_grade_index", 1, 2),
    ("temperature_c", 25, 40),
]


@pytest.mark.parametrize("key,low,high", ADVERSARIAL)
def test_every_numeric_context_is_structurally_identical(key, low, high):
    """Four of these five support no difference at all; one supports an
    interval difference. The coordinate function cannot tell them apart,
    and nothing in the record distinguishes them."""
    a = resolve_model_state_key("formulation-a", "viscosity", {key: low})
    b = resolve_model_state_key("formulation-a", "viscosity", {key: high})
    assert a != b
    assert len(a) == len(b) == 64
    assert isinstance(low, int) and isinstance(high, int)


def test_representation_is_insufficient_because_it_is_transformation_blind():
    """`batch_id` is nominal: relabelling batches 100/200 as 7/2 changes
    nothing scientific. Applying that same relabelling to temperature
    destroys a real fact. The numbers are indistinguishable; the
    admissible transformations are not."""
    assert not _survives(NOMINAL, "order")
    assert BASE["order"] is True


# -- 5. coordinate semantics vs response semantics ------------------------------------------------


CONTENT = {"property": "tensile_strength", "value": 90.0, "unit": "MPa", "temperature_c": 25}


def test_coordinate_and_response_share_one_flat_mapping_with_no_scale_marker():
    context = _comparison_context(CONTENT, "value")
    assert dict(context) == {"unit": "MPa", "temperature_c": 25}
    # `unit` describes the RESPONSE; `temperature_c` is a COORDINATE.
    # Nothing marks which is which, and neither carries a scale.
    assert not any("scale" in k for k in CONTENT)


def test_no_scale_vocabulary_exists_anywhere_in_production():
    forbidden = {"nominal", "ordinal", "interval_scale", "ratio_scale",
                 "measurement_scale", "ContextMeasurementSemantics"}
    hits = []
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                name = None
                if isinstance(node, ast.Name):
                    name = node.id
                elif isinstance(node, ast.Attribute):
                    name = node.attr
                elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    name = node.name
                if name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {name}")
    assert hits == [], hits


# -- 6/14. scale authorizes nothing about the response --------------------------------------------


def test_coordinate_metric_does_not_license_response_closeness():
    """tensile_strength 90 @ 25, 95 @ 40, 60 @ 100. The coordinate metric
    says 40 is nearer to 25, and here the response agrees -- which is the
    trap. A cure peak (Phase 104) reverses it with the same coordinates."""
    response = {25: 90.0, 40: 95.0, 100: 60.0}
    assert abs(25 - 40) < abs(25 - 100)                       # coordinate
    assert abs(response[25] - response[40]) < abs(response[25] - response[100])
    cure_peak = {25: 90.0, 40: 30.0, 100: 88.0}               # same coordinates
    assert abs(cure_peak[25] - cure_peak[40]) > abs(cure_peak[25] - cure_peak[100])


def test_production_still_offers_no_cross_cell_operation():
    """The strong negative requirement: nothing a scale declaration could
    attach to already exists."""
    forbidden = {"interpolate", "aggregate_cells", "transfer_prediction",
                 "similarity", "nearest_cell", "compare_cells", "convert_unit"}
    hits = []
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {node.name}")
    assert hits == [], hits


# -- 8. units ------------------------------------------------------------------------------------


UNIT_CONTENTS = (
    ({"property": "tensile_strength", "value": 90.0, "unit": "MPa", "temperature_c": 25}, 90.0),
    ({"property": "tensile_strength", "value": 0.095, "unit": "GPa", "temperature_c": 25}, 0.095),
    ({"property": "tensile_strength", "value": 92000.0, "unit": "kPa", "temperature_c": 25}, 92000.0),
)


def _unit_groups():
    return _group_by_comparison_context(
        tuple((_comparison_context(c, "value"), v) for c, v in UNIT_CONTENTS)
    )


def test_three_encodings_of_one_fact_never_pool():
    groups = _unit_groups()
    assert len(groups) == 3
    assert all(len(g.values) == 1 and g.disagreement is None for g in groups)


def test_a_criterion_silent_about_unit_yields_incomparable_not_a_false_pass():
    groups = _unit_groups()
    silent = Criterion(property="tensile_strength", operator=">=", target=75.0,
                       context={"temperature_c": 25})
    assert len(_matching_groups(groups, silent)) == 3
    assert _status_for_groups(groups, silent)[0] == INCOMPARABLE

    explicit = Criterion(property="tensile_strength", operator=">=", target=75.0,
                         context={"temperature_c": 25, "unit": "MPa"})
    assert len(_matching_groups(groups, explicit)) == 1
    assert _status_for_groups(groups, explicit)[0] == PASS


def test_scale_would_justify_no_conversion():
    """Ratio-scale says x' = a*x preserves meaning. It does not say which
    `a` carries MPa to kPa -- that is a separate physical claim. Scale
    type, unit, conversion and comparability are four different things."""
    assert _survives(RATIO_SCALE, "ratio_of_values")     # the scale statement
    assert RATIO_SCALE(1.0) == 1000.0                    # the conversion factor
    # The first does not imply the second: any a > 0 satisfies the scale.
    other = lambda x: 7.0 * x
    assert _ops(tuple(other(x) for x in V))["ratio_of_values"] == BASE["ratio_of_values"]


# -- 10. identity invariance ----------------------------------------------------------------------


def _obs_id(content):
    return make_observation(
        record_ids=("rec-1",), extraction_method="regex:x", content=content,
        confidence=1.0, extracted_at="2026-01-01T00:00:00Z",
    ).id


def test_unit_is_identity_bearing_because_it_is_part_of_the_record():
    mpa = _obs_id({"property": "tensile_strength", "value": 90.0, "unit": "MPa"})
    gpa = _obs_id({"property": "tensile_strength", "value": 90.0, "unit": "GPa"})
    bare = _obs_id({"property": "tensile_strength", "value": 90.0})
    assert len({mpa, gpa, bare}) == 3


def test_the_coordinate_is_the_recorded_encoding_not_the_physical_state():
    """25 C and 298.15 K are the same temperature and different cells --
    and so, sharply, are `25` and `25.0`, because canonical JSON encodes
    int and float differently. Worth knowing before editing a scenario
    file: changing `25` to `25.0` silently re-cells the study."""
    celsius = resolve_model_state_key("formulation-a", "viscosity", {"temperature_c": 25})
    kelvin = resolve_model_state_key("formulation-a", "viscosity", {"temperature_c": 298.15})
    as_float = resolve_model_state_key("formulation-a", "viscosity", {"temperature_c": 25.0})
    assert len({celsius, kelvin, as_float}) == 3
    assert content_hash({"t": 25}) != content_hash({"t": 25.0})


def test_a_scale_declaration_changes_no_record_and_so_must_change_no_id():
    """Held externally, a scale declaration is not reachable from any
    hashed structure -- the same proof shape as Phase 104's order."""
    declaration = {"temperature_c": "interval", "material_grade": "nominal"}
    before = resolve_model_state_key("formulation-a", "viscosity", {"temperature_c": 25})
    _ = declaration
    after = resolve_model_state_key("formulation-a", "viscosity", {"temperature_c": 25})
    assert before == after
    # ...and it WOULD move if smuggled into the coordinate:
    smuggled = resolve_model_state_key(
        "formulation-a", "viscosity", {"temperature_c": 25, "scale": "interval"}
    )
    assert smuggled != before


# -- 12. four senses of rank ----------------------------------------------------------------------


def test_rank_is_the_canonical_monotone_map_and_therefore_lossy():
    """Ranking IS an ordinal transformation. Applied to an ordinal
    quantity it loses nothing; applied to an interval quantity it
    destroys the ratio of differences that was legitimately there."""
    ranks = (0.0, 1.0, 2.0)
    assert _ops(ranks)["order"] == BASE["order"]
    assert _ops(ranks)["ratio_of_differences"] == 1.0
    assert BASE["ratio_of_differences"] == 0.25
    assert _ops(ranks)["ratio_of_differences"] != BASE["ratio_of_differences"]


def test_the_only_rank_in_production_is_execution_priority():
    """Ordinal rank (Phase 104, not built), measurement magnitude,
    authority rank (Phase 105, does not exist) and execution priority are
    four different concepts. Exactly one is implemented."""
    import dataclasses
    from materials.ranking import CandidateRanking

    assert {f.name for f in dataclasses.fields(CandidateRanking)} == {
        "candidate_id", "utility", "rank", "ranking_status",
    }


# -- 13/16. nothing was added ---------------------------------------------------------------------


def test_phase_106_added_no_measurement_machinery():
    forbidden = (
        "ContextMeasurementSemantics", "MeasurementScale", "ScaleType",
        "admissible_transformation", "unit_conversion", "convert_units",
    )
    hits = []
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            text = path.read_text()
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert hits == [], hits
