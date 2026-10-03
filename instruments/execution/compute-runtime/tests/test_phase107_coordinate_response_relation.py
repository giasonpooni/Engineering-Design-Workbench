"""Phase 107: the minimum scientific object required to relate a context
coordinate to an observed material property.

VERDICT: SURVIVES. The boundary between observations and cross-cell
scientific relationships is clean, and the missing structure is
identifiable without changing production.

WHAT IS ACTUALLY REPRESENTED
----------------------------
For a programme observing tensile_strength at 25, 40 and 100 C:

    THREE OBSERVATIONS. No relationship object of any kind.

`ModelState` has exactly two fields, `id` and `samples`, and `samples` is
a flat mapping from an opaque `resolve_model_state_key` hash to a tuple
of `Sample(value, observation_id)`. There is no edge between cells, no
ordering among them, and -- decisively -- THE COORDINATE IS NOT IN THE
STATE AT ALL. Given only a `ModelState` you cannot recover 25, 40 or 100,
so no function of temperature could be fitted from it even in principle.
The state is not merely missing a model; it is missing the domain.

The coordinate does survive, in the POOL, on each `Observation.content`.
Fitting y = f(T) would require re-joining the evidence layer to the model
layer, and nothing in production does that. `materials/diagnostics.py`
states the deeper reason in place: "there is no registry anywhere of
which `ActionCandidate`s exist or which cell each one names", so a
`ModelState` cannot even ENUMERATE its own coordinates.

Every multi-cell read in production was inspected. There are exactly
three, and none is scientific: a scan for the `hypothetical:` sample
marker, a monotonicity CHECK comparing the same key across two states,
and `total_sample_count`, which sums lengths. No two cells' values ever
meet in one statistic.

`predict` AT AN UNOBSERVED COORDINATE
-------------------------------------
    25 C -> 90.0   n=1        40 C -> 95.0  n=1
    60 C -> None   n=0        100 C -> 60.0 n=1

60 C was never observed and stays `None`. No neighbour is consulted, no
default, no zero. `predict` performs no statistical inference, no
interpolation, no regression, no Bayesian update, no simulation, no
temporal evolution: it is `state.samples.get(key, ())` followed by a mean
and, for 2+ samples, a sample variance (divisor n-1).
`materials/model_state.py`
already says so at length -- NOT a physical model, NOT causal, NOT a
Gaussian process, NOT a Bayesian posterior, NOT calibrated.

So: Prediction != scientific model, and Prediction != prediction of an
unobserved coordinate. It is a SUMMARY OF ADMITTED EVIDENCE at one cell.

REPLICATION vs TRANSFER -- the hard boundary
--------------------------------------------
Adding 92 and 88 at 25 C moves that cell from (90.0, uncertainty=None,
n=1) to (90.0, uncertainty=2.667, n=3) and leaves the 40 C cell
BYTE-IDENTICAL. Replication supplies dispersion about the SAME
coordinate: it needs no assumption beyond "these measure the same thing",
which is exactly what sharing a cell key asserts. Transfer would need an
assumption relating DIFFERENT coordinates, and no such assumption is
recorded anywhere. That is why within-cell statistics are free and
cross-cell inference is not.

FOUR CLAIMS THAT MUST NOT CHAIN
-------------------------------
  A ASSOCIATION  "they vary together"     -- needs repeated joint
                 observation across cells, and is already unsupported:
                 nothing joins two cells.
  B FUNCTION     "y is a function of T"   -- needs, additionally, that no
                 hidden variable varies. Two observations at ONE
                 coordinate with different values falsify functionhood,
                 and the architecture cannot distinguish that from
                 measurement scatter. Neither can anyone else without
                 naming the missing variable.
  C PREDICTION   "T = 60 predicts y"      -- needs, additionally, an
                 estimated relation plus an applicability domain
                 containing 60.
  D CAUSATION    "changing T changes y"   -- needs, additionally,
                 intervention. No observational set implies it.

A -> B -> C -> D is invalid at every arrow, and each arrow needs a NEW
EPISTEMIC OBJECT, never merely more observations.

THE SMALLEST OBJECT THAT LICENSES PREDICTION AT AN UNOBSERVED COORDINATE
------------------------------------------------------------------------
  distance d(x,y)    NO -- Phase 106: a difference gives A metric, never
                     THE metric, and all of them live on the coordinate.
  similarity s(x,y)  NO -- uninterpreted; a number, not a claim.
  kernel k(x,y)      NO by itself. A kernel IS a smoothness assumption in
                     disguise; it licenses prediction only once that
                     assumption is stated as such and admitted.
  function y = f(x)  the SMALLEST sufficient object -- but only when
                     accompanied by what estimated it, from which
                     observations, and where it applies.
  p(y | x)           sufficient, and additionally carries uncertainty.
  dy/dx = F(x,y)     stronger, and buys extrapolation the others cannot.

So the minimum is (D): an ESTIMATED FUNCTION WITH AN APPLICABILITY
DOMAIN. Everything weaker is a representation, not a relationship.

COORDINATE GEOMETRY DOES NOT DETERMINE RESPONSE GEOMETRY
--------------------------------------------------------
Four polymer counterexamples, all with well-behaved coordinates:

  glass transition   58 -> 2400 MPa, 62 -> 1900, 66 -> 45, 120 -> 12.
                     58 and 66 are 8 C apart across Tg: a 53x drop.
                     66 and 120 are 54 C apart and within 4x. Coordinate
                     proximity is ANTI-correlated with response proximity.
  cold crystallis.   25 -> 3% haze, 90 -> 41, 150 -> 4. The two FARTHEST
                     points have the two most similar responses.
  shear thinning     a perfect RATIO-scale coordinate with a true zero;
                     the response is power-law in log(shear), so equal
                     coordinate DIFFERENCES give wildly unequal response
                     differences.
  cure path          the same coordinate with two thermal histories gives
                     two conversions. Not noise -- a falsification of
                     functionhood, and evidence the coordinate is
                     INCOMPLETE.

REPRESENTATION IS NOT RELATIONSHIP
----------------------------------
learned embedding != scientific similarity; kernel value != physical
similarity; Euclidean distance != response similarity; neural prediction
!= causal explanation; graph adjacency != scientific relation. Each left
side is a choice of encoding; each right side is a claim about the world
that must be admitted with provenance and can be wrong.

PROVENANCE, AND WHY IT IS NOT OPTIONAL
--------------------------------------
An `Observation` already carries record ids, an extraction method, a
confidence and an extracted_at, and cannot enter the pool without
referential integrity. A relationship claim asserts strictly MORE than
an observation -- it speaks about coordinates never measured -- so a
relationship WITHOUT source observations, method, assumptions,
parameterisation, validation and applicability domain would be
epistemically WEAKER than the observations it was built from while
claiming more. That asymmetry is the argument: provenance is not
decoration on such an object, it is the whole of its warrant.

IS A NEW OBJECT MISSING?
------------------------
Yes, and it is genuinely missing -- but the audit is what identifies it,
not what builds it. `DerivedValue` is the near miss: it has
`derived_from`, a `method`, a `confidence`, and content, and it is
admitted with referential integrity. What it cannot express is a claim
whose SUBJECT is a coordinate nobody observed, together with the domain
over which the claim is asserted to hold. `DerivedValue.content` is a
mapping and could carry those as keys -- which is exactly why writing
them there would be wrong: they would be invisible to every guard, and
`materials/` would gain a fitted model no layer had approved.

CONSEQUENCE FOR PRODUCTION: none. Zero production changes in this phase.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from materials.model_state import (
    ModelState,
    Prediction,
    Sample,
    make_model_state,
    predict,
    resolve_model_state_key,
)
from workbench import theme
from workbench.interaction import bootstrap_research_scenario

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("evidence", "retrieval", "materials", "experiment", "workbench")

OBSERVED = {25: 90.0, 40: 95.0, 100: 60.0}


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _clock():
    n = [0]

    def c():
        n[0] += 1
        return f"2026-01-01T00:00:{n[0]:02d}Z"

    return c


@pytest.fixture
def programme():
    """tensile_strength at 25, 40 and 100 C, each observed once."""
    state = bootstrap_research_scenario({
        "name": "phase 107", "process": "process-std-190c",
        "formulations": ["formulation-a"],
        "property": "tensile_strength",
        "criterion": {"operator": ">=", "target": 75.0},
        "contexts": [{"temperature_c": t} for t in sorted(OBSERVED)],
    }, clock=_clock())
    for temperature, value in OBSERVED.items():
        matches = [
            c for c in state.candidates.candidates
            if c.target_context.get("temperature_c") == temperature
        ]
        assert len(matches) == 1
        state.selected_candidate = matches[0]
        state.observe(value, unit="MPa")
    return state


class _Probe:
    """A candidate-shaped object at an arbitrary coordinate. The
    formulation must be the REAL `Referent`, whose id is a content hash
    -- not the scenario's literal formulation key."""

    def __init__(self, formulation, context):
        self.formulation = formulation
        self.property = "tensile_strength"
        self.target_context = dict(context)
        self.id = "probe"


# -- 1. three observations, and nothing else ------------------------------------------------------


def test_the_state_holds_three_observations_and_no_relationship(programme):
    state = programme.session.state
    assert {f.name for f in ModelState.__dataclass_fields__.values()} == {"id", "samples"}
    assert len(state.samples) == 3
    assert sorted(s.value for samples in state.samples.values() for s in samples) == [60.0, 90.0, 95.0]
    # every cell holds exactly one sample, and nothing connects them
    assert all(len(samples) == 1 for samples in state.samples.values())


def test_the_coordinate_is_not_in_the_state_at_all(programme):
    """So no function of temperature could be fitted from a ModelState
    even in principle -- the domain itself is absent."""
    state = programme.session.state
    assert all(len(key) == 64 for key in state.samples)          # opaque hashes
    flattened = repr(sorted(state.samples.items()))
    for temperature in OBSERVED:
        assert f"temperature_c" not in flattened
        assert f": {temperature}" not in flattened
    assert {f.name for f in Sample.__dataclass_fields__.values()} == {"value", "observation_id"}


def test_the_coordinate_survives_only_in_the_pool(programme):
    """Evidence layer holds the conditions; model layer holds values
    indexed by opaque cells. Nothing in production re-joins them."""
    state = programme.session.state
    recovered = set()
    for samples in state.samples.values():
        for sample in samples:
            content = programme.pool.get_observation(sample.observation_id).content
            recovered.add(content["temperature_c"])
    assert recovered == set(OBSERVED)


def test_every_multi_cell_read_in_production_is_non_scientific():
    """Three exist: the hypothetical-marker scan, the trajectory
    monotonicity CHECK (same key, two states), and a sample count."""
    # ANCHORED ON THE ENCLOSING FUNCTION, NOT ON A LINE NUMBER. This
    # guard pinned `path:lineno`, so editing a COMMENT anywhere above a
    # listed site broke it -- which happened, and the failure said only
    # that 271 != 269. A line number is not what this test is about; the
    # question is which functions read across cells, and that answer
    # survives every edit that does not move the read.
    def _enclosing(tree):
        """node -> the def that contains it, or '<module>'."""
        owner = {}
        for parent in ast.walk(tree):
            if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for child in ast.walk(parent):
                    owner.setdefault(child, parent.name)
        return owner

    multi_cell = []
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            tree = ast.parse(path.read_text())
            owner = _enclosing(tree)
            for node in ast.walk(tree):
                # `.samples.values()` or `.samples.items()` -- iterating ACROSS cells
                if (isinstance(node, ast.Attribute) and node.attr in ("values", "items")
                        and isinstance(node.value, ast.Attribute)
                        and node.value.attr == "samples"):
                    where = owner.get(node, "<module>")
                    multi_cell.append(f"{path.relative_to(REPO)}::{where}")
    assert multi_cell == [
        "materials/model_state.py::__post_init__",              # normalisation
        "materials/model_state.py::_contains_hypothetical_sample",
        "materials/trajectory.py::make_model_state_trajectory",  # successor check, same key across states
        "workbench/interaction.py::total_sample_count",
    ], multi_cell


# -- 4. what "prediction" currently means ---------------------------------------------------------


def test_predict_is_a_summary_of_admitted_evidence(programme):
    source = inspect.getsource(predict)
    assert "state.samples.get(key, ())" in source
    for absent in ("interp", "fit", "regress", "prior", "likelihood", "neighbour", "neighbor"):
        assert absent not in source.lower()


def test_predict_at_an_unobserved_coordinate_stays_none(programme):
    formulation = programme.candidates.candidates[0].formulation
    state = programme.session.state
    for temperature, expected in OBSERVED.items():
        result = predict(state, _Probe(formulation, {"temperature_c": temperature}))
        assert result.predicted_value == expected
        assert result.sample_count == 1
        assert result.uncertainty is None          # one sample has no variance
    unobserved = predict(state, _Probe(formulation, {"temperature_c": 60}))
    assert unobserved.predicted_value is None
    assert unobserved.sample_count == 0
    assert unobserved.uncertainty is None


def test_prediction_carries_no_field_implying_a_model():
    fields = {f.name for f in Prediction.__dataclass_fields__.values()}
    assert fields == {
        "candidate_id", "formulation", "property", "context",
        "predicted_value", "uncertainty", "sample_count", "state_id", "model_state_key",
    }
    for absent in ("confidence", "interval", "calibration", "likelihood", "method", "model"):
        assert absent not in fields


# -- 5/6. replication versus transfer -------------------------------------------------------------


def test_replication_sharpens_one_cell_and_reaches_no_other(programme):
    formulation = programme.candidates.candidates[0].formulation
    before_forty = programme.session.state.samples[
        resolve_model_state_key(formulation.id, "tensile_strength", {"temperature_c": 40})
    ]

    at_twenty_five = [
        c for c in programme.candidates.candidates
        if c.target_context.get("temperature_c") == 25
    ][0]
    programme.selected_candidate = at_twenty_five
    programme.observe(92.0, unit="MPa")
    programme.observe(88.0, unit="MPa")

    state = programme.session.state
    replicated = predict(state, _Probe(formulation, {"temperature_c": 25}))
    assert replicated.sample_count == 3
    assert replicated.predicted_value == 90.0
    assert replicated.uncertainty == pytest.approx(8.0 / 2.0)   # sample variance (n-1) of 90/92/88

    untouched = predict(state, _Probe(formulation, {"temperature_c": 40}))
    assert untouched.sample_count == 1
    assert untouched.uncertainty is None
    after_forty = state.samples[
        resolve_model_state_key(formulation.id, "tensile_strength", {"temperature_c": 40})
    ]
    assert after_forty == before_forty      # byte-identical


def test_sharing_a_cell_key_is_the_only_sameness_assumption_replication_needs():
    """Two samples in one cell assert 'these measure the same thing',
    which is exactly what an equal `resolve_model_state_key` says.
    Transfer would need an assumption relating DIFFERENT keys, and no
    such assumption is recorded anywhere."""
    key = resolve_model_state_key("f", "tensile_strength", {"temperature_c": 25})
    other = resolve_model_state_key("f", "tensile_strength", {"temperature_c": 40})
    state = make_model_state({
        key: (Sample(value=90.0, observation_id="a"), Sample(value=92.0, observation_id="b")),
        other: (Sample(value=95.0, observation_id="c"),),
    })
    assert len(state.samples[key]) == 2
    assert len(state.samples[other]) == 1


# -- 8/12. coordinate geometry does not determine response geometry --------------------------------


def test_glass_transition_inverts_coordinate_proximity():
    modulus = {58: 2400.0, 62: 1900.0, 66: 45.0, 120: 12.0}
    near = abs(modulus[58] - modulus[66])       # 8 C apart, across Tg
    far = abs(modulus[66] - modulus[120])       # 54 C apart, same phase
    assert abs(58 - 66) < abs(66 - 120)         # nearer in the coordinate
    assert near > far                           # further in the response


def test_non_monotone_response_defeats_nearest_neighbour_transfer():
    haze = {25: 3.0, 90: 41.0, 150: 4.0}
    assert abs(25 - 150) > abs(25 - 90)                       # farthest coordinates
    assert abs(haze[25] - haze[150]) < abs(haze[25] - haze[90])   # closest responses


def test_a_ratio_scale_coordinate_still_licenses_nothing():
    """Shear rate has a true zero and a full metric. The response is
    power-law, so equal coordinate DIFFERENCES give wildly unequal
    response differences."""
    viscosity = {0.1: 5200.0, 1.0: 4900.0, 10.0: 900.0, 100.0: 120.0}
    first = abs(viscosity[1.0] - viscosity[10.0]) / (10.0 - 1.0)
    second = abs(viscosity[10.0] - viscosity[100.0]) / (100.0 - 10.0)
    assert first > 50 * second


def test_path_dependence_falsifies_functionhood_not_just_smoothness():
    """Same coordinate, two thermal histories, two conversions. Not
    noise: evidence that the declared coordinate is INCOMPLETE. The
    architecture records it within one cell and cannot tell it from
    measurement scatter."""
    ramped, isothermal = 94.0, 81.0
    key = resolve_model_state_key("f", "conversion", {"cure_time_min": 60})
    state = make_model_state({key: (
        Sample(value=ramped, observation_id="a"),
        Sample(value=isothermal, observation_id="b"),
    )})
    assert len(state.samples[key]) == 2
    # one cell, two irreconcilable values -- indistinguishable from scatter
    assert {s.value for s in state.samples[key]} == {ramped, isothermal}


# -- 13/14. no cell graph, and no relationship object ----------------------------------------------


def test_no_cell_adjacency_similarity_or_neighbourhood_exists():
    forbidden = {
        "cell_adjacency", "cell_similarity", "cell_neighbourhood", "cell_neighborhood",
        "neighbours_of", "neighbors_of", "cell_graph", "RelationshipClaim",
        "applicability_domain", "fit_relation", "estimate_relation",
    }
    hits = []
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                name = None
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    name = node.name
                elif isinstance(node, ast.Name):
                    name = node.id
                elif isinstance(node, ast.Attribute):
                    name = node.attr
                if name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {name}")
    assert hits == [], hits


def test_derived_value_is_the_near_miss_and_still_cannot_express_the_claim():
    """It has derived_from, method, confidence and content, and is
    admitted with referential integrity -- but nothing in it names a
    coordinate nobody observed, or the domain the claim covers. That
    those could be smuggled into `content` as keys is exactly why they
    must not be: they would be invisible to every guard."""
    import dataclasses

    from evidence.types import DerivedValue

    fields = {f.name for f in dataclasses.fields(DerivedValue)}
    assert {"derived_from", "method", "confidence", "content"} <= fields
    assert "applicability_domain" not in fields
    assert "target_coordinate" not in fields


def test_a_model_state_cannot_enumerate_its_own_coordinates():
    """`materials/diagnostics.py` states the reason in place: no registry
    exists of which candidates exist or which cell each one names."""
    text = " ".join((REPO / "materials" / "diagnostics.py").read_text().split())
    assert "there is no registry anywhere of which `ActionCandidate`s exist" in text


# -- 18. nothing was added --------------------------------------------------------------------------


def test_phase_107_added_no_cross_cell_machinery():
    forbidden = (
        "def interpolate", "def extrapolate", "def transfer", "def kernel",
        "class RelationshipClaim", "class ResponseModel", "def fit(",
    )
    hits = []
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            text = path.read_text()
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert hits == [], hits
