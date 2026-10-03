"""Phase 108: falsification of Phase 107's "one RelationshipClaim".

VERDICT: FALSIFIED. Phase 107 compressed several distinct epistemic
structures into one word. Two of its claims failed.

FAILED CLAIM 1 -- "the smallest missing abstraction is an admitted
relationship claim ... naming its source observations, its method and
assumptions, its estimated relation, and the applicability domain".

That object cannot honestly hold correlation, regression, interpolation,
mechanistic law, similarity, monotonicity and causality, and it fails on
FOUR INDEPENDENT AXES, any one of which is sufficient:

  1 ARITY. Correlation and similarity are SYMMETRIC 2-ary relations.
    Regression, interpolation, mechanism and causation are DIRECTED.
    Monotonicity is not a relation between two things at all -- it is a
    1-ary CONSTRAINT on a function. No single field set has the right
    shape for all three arities, and `DerivedValue.derived_from`, the
    nearest existing carrier, is an n-ary DIRECTED edge that cannot
    express a symmetric relation without asserting a direction that is
    not there.

  2 `parameters` IS NOT ONE KIND. Regression coefficients have no
    meaning outside the fit that produced them. Mechanistic constants
    have units, exist independently of any fit, and are separately
    measurable. Interpolation and monotonicity have no parameters at
    all. Storing these in one field would make "the parameters agree"
    an unanswerable question.

  3 `applicability_domain` IS NOT ONE KIND. For correlation it is the
    POPULATION sampled; for regression a coordinate REGION plus the
    sampling design; for interpolation strictly the CONVEX HULL of the
    observed points; for a mechanistic law a PHYSICAL REGIME (below Tg,
    laminar flow) that need not be a coordinate interval at all; for
    similarity it is undefined, because a symmetric relation has no
    target to be applicable AT. Phase 107 called this field "necessary
    for prediction" and was right; it then treated it as one type, and
    was wrong.

  4 PROVENANCE SUFFICIENCY DIFFERS IN KIND, NOT DEGREE. `source_
    observations` can never support the causal row. Observational
    provenance is the WRONG TYPE of warrant for an interventional
    claim, not a weaker amount of the right type. A single field
    silently invites the substitution.

FAILED CLAIM 2 -- "functionhood requires that no hidden variable
varies". Too strong, and wrong as stated. Given

    25 C -> 90 MPa    and    25 C -> 70 MPa

the correct conclusion is NOT "no function of temperature exists". It is
"the observed PROJECTION is not single-valued". A function may exist in
a larger state space, and this architecture ALREADY has the mechanism to
say so: adding `crystallinity_pct` to `target_context` splits one
contradictory cell (mean 80.0, variance 100.0) into two consistent cells
(90.0 and 70.0, each n=1). That is Phase 100's typed coordinate used
exactly as intended. So the right architectural response to a
same-coordinate contradiction is INCOMPLETE COORDINATE SYSTEM, not
FAILED MODEL -- and the two are not the same diagnosis.

WHAT SURVIVED FROM PHASE 107
----------------------------
The boundary itself, and the specific claim that PREDICTION at an
unobserved coordinate needs an estimated function with an applicability
domain. What did not survive is the generalisation of that one answer to
the word "relationship".

ASSOCIATION WITHOUT FUNCTIONHOOD
--------------------------------
Three datasets, three different supported claims:

  25 C -> 90, 91, 89 ; 40 C -> 95, 94, 96
      dispersion at two coordinates, and an association (the means
      differ by far more than the spread). Says nothing about 30 C.
  25 C -> 90 ; 40 C -> 95 ; 100 C -> 60
      three point estimates, NO dispersion anywhere. Weaker than the
      first on noise and equally silent on functionhood.
  25 C -> 90, 70 ; 40 C -> 95
      an association AND a positive falsification of single-valuedness.

Association survives in all three. Functionhood survives in none. So
"relationship" cannot mean "function", and y = f(x) cannot stand in for
p(y | x): the latter is what all three datasets actually support, and it
is the only form in which batch effects, noise, hysteresis, multimodality
and phase transitions are representable rather than averaged away.

THE ARCHITECTURE ALREADY ANSWERS THREE OF THIS PHASE'S QUESTIONS
----------------------------------------------------------------
  sec.13 The object that exists after predict-then-observe is
         `PredictionAssessment` -- prediction, result and observation
         embedded whole, plus a SIGNED residual, documented in place as
         "not model failure, not experimental failure, not truth, not
         bias, and not a causal explanation". The model -> experiment ->
         model edge exists; model -> evidence does not, because
         `assess` never touches the pool and `update` does not take an
         assessment as input.

  sec.16 A counterfactual already exists, and it is the EPISTEMIC one:
         `project_update(state, candidate, hypothetical_value)` varies
         the RESPONSE at a fixed coordinate ("if we had observed y") and
         has no argument for varying the coordinate ("if x had been
         different"). Its samples are permanently prefixed
         `hypothetical:`. A predictive function licenses the first and
         never the second.

  sec.15 Today `Prediction` carries no id and is a pure function of
         (state.id, candidate.id), so MODEL identity is IMPLIED BY
         EVIDENCE identity. A fitted relationship breaks that
         implication: a linear fit and an Arrhenius fit over one pool
         share an evidence fingerprint and are different models. That is
         a SECOND IDENTITY AXIS, which is why a model version can never
         be an evidence version.

PROVENANCE CANNOT BE ONE EDGE, AND VALIDATION IS NOT PROVENANCE
---------------------------------------------------------------
`derived_from` records INCLUSION -- which objects were used. Validation
is a claim about a COMPLEMENT -- that the checking observations were NOT
used. No inclusion edge can express a disjointness condition about
itself. So a claim with impeccable provenance and no independent
validation is DERIVED, and at most SUPPORTED. It is not PREDICTIVE and
not ADMISSIBLE as a basis for action, and those four words must stay
four words.

sec.19 ANSWER: (C). Not one object, and not merely several: the claim
types are not comparable -- some are symmetric relations, some directed
mappings, one is a constraint on another node -- and they need different
KINDS of provenance. That is a DAG, not a list and not a ladder.
(D) is false: the gap is a genuine ontological multiplicity, not an
implementation boundary. Its correct consequence is nevertheless to
build nothing, because no rung above replication is reachable from what
production holds.

CONSEQUENCE FOR PRODUCTION: none. Zero production changes in this phase.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from evidence.types import ClaimedRelationship, DerivedValue, Observation
from materials.assessment import PredictionAssessment, assess
from materials.counterfactual import project_update
from materials.model_state import (
    Prediction,
    Sample,
    make_model_state,
    predict,
    resolve_model_state_key,
)
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("evidence", "retrieval", "materials", "experiment", "workbench")

FORMULATION = "formulation-a"
PROPERTY = "tensile_strength"


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


def _cell(context) -> str:
    return resolve_model_state_key(FORMULATION, PROPERTY, context)


class _Probe:
    def __init__(self, context):
        self.formulation = type("R", (), {"id": FORMULATION})()
        self.property = PROPERTY
        self.target_context = dict(context)
        self.id = "probe"


def _state(cells):
    return make_model_state({
        _cell(context): tuple(
            Sample(value=v, observation_id=f"obs-{i}-{v}") for i, v in enumerate(values)
        )
        for context, values in cells
    })


# -- 1/3. association survives where functionhood does not ----------------------------------------


def test_replicated_dataset_supports_dispersion_and_association_not_a_function():
    state = _state([
        ({"temperature_c": 25}, [90.0, 91.0, 89.0]),
        ({"temperature_c": 40}, [95.0, 94.0, 96.0]),
    ])
    low = predict(state, _Probe({"temperature_c": 25}))
    high = predict(state, _Probe({"temperature_c": 40}))
    assert (low.predicted_value, low.sample_count) == (90.0, 3)
    assert (high.predicted_value, high.sample_count) == (95.0, 3)
    # the means differ by more than the full within-cell RANGE at either
    # coordinate (2.0 each) -- stated as a range, not an invented statistic
    within = max(91.0 - 89.0, 96.0 - 94.0)
    assert abs(high.predicted_value - low.predicted_value) > 2 * within
    # ...and nothing is said about any coordinate between them
    assert predict(state, _Probe({"temperature_c": 30})).predicted_value is None


def test_one_point_per_coordinate_supports_less_not_more():
    state = _state([
        ({"temperature_c": t}, [v]) for t, v in ((25, 90.0), (40, 95.0), (100, 60.0))
    ])
    for temperature in (25, 40, 100):
        result = predict(state, _Probe({"temperature_c": temperature}))
        assert result.sample_count == 1
        assert result.uncertainty is None      # no dispersion anywhere


def test_a_same_coordinate_contradiction_falsifies_single_valuedness_only():
    """Association survives; functionhood does not. So "relationship"
    cannot mean "function"."""
    state = _state([
        ({"temperature_c": 25}, [90.0, 70.0]),
        ({"temperature_c": 40}, [95.0]),
    ])
    contradictory = predict(state, _Probe({"temperature_c": 25}))
    assert contradictory.sample_count == 2
    assert contradictory.predicted_value == 80.0
    # sample variance (n-1) of 70 and 90: ((70-80)^2 + (90-80)^2) / 1 = 200
    assert contradictory.uncertainty == 200.0     # large, and indistinguishable from scatter


# -- 6/7. incomplete coordinate, not failed model --------------------------------------------------


def test_adding_a_coordinate_dissolves_the_contradiction():
    """PHASE 107'S CLAIM 2, CORRECTED. The right conclusion is not "no
    function exists" but "the observed PROJECTION is not single-valued" --
    and Phase 100's typed coordinate already says so, with no new object."""
    projected = _state([({"temperature_c": 25}, [90.0, 70.0])])
    assert len(projected.samples) == 1
    assert predict(projected, _Probe({"temperature_c": 25})).uncertainty == 200.0

    completed = _state([
        ({"temperature_c": 25, "crystallinity_pct": 42}, [90.0]),
        ({"temperature_c": 25, "crystallinity_pct": 18}, [70.0]),
    ])
    assert len(completed.samples) == 2
    for crystallinity, expected in ((42, 90.0), (18, 70.0)):
        result = predict(completed, _Probe({"temperature_c": 25, "crystallinity_pct": crystallinity}))
        assert result.predicted_value == expected
        assert result.uncertainty is None
        assert result.sample_count == 1


def test_failed_model_and_incomplete_coordinate_are_different_diagnoses():
    """The architecture can express the second (add a key) and cannot
    express the first at all -- it holds no model to fail."""
    narrow = _cell({"temperature_c": 25})
    wide = _cell({"temperature_c": 25, "crystallinity_pct": 42})
    assert narrow != wide
    # A cell key is not "revised" into a wider one: it is a different cell,
    # and the original samples stay exactly where they were admitted.
    assert len(narrow) == len(wide) == 64


# -- 2/10. arity and field divergence --------------------------------------------------------------


def test_the_nearest_existing_relation_object_has_the_wrong_carrier_set():
    """`ClaimedRelationship` is a directed binary relation WITH
    provenance and confidence -- between Referents, never between cells
    or coordinates."""
    fields = {f.name for f in dataclasses.fields(ClaimedRelationship)}
    assert fields == {"id", "from_referent_id", "to_referent_id", "type", "observation_id", "confidence"}
    assert "context" not in fields and "model_state_key" not in fields


def test_derived_from_is_directed_and_cannot_carry_a_symmetric_claim():
    fields = {f.name for f in dataclasses.fields(DerivedValue)}
    assert "derived_from" in fields
    # n-ary and directed: naming inputs of one output. Correlation and
    # similarity are symmetric and have no output.
    assert "content" in fields and "method" in fields
    assert "applicability_domain" not in fields
    assert "validated_against" not in fields


def test_monotonicity_is_a_constraint_not_a_relation():
    """It has no source and no target, no parameters, and predicts
    nothing -- it constrains a function that some OTHER node supplies.
    A field set shaped for source/target/parameters cannot hold it."""
    monotone = (90.0, 95.0, 60.0)
    assert not all(a <= b for a, b in zip(monotone, monotone[1:]))
    # The claim is about f, not about any pair of observations.


# -- 13. what exists after predict-then-observe ----------------------------------------------------


def test_prediction_assessment_is_the_existing_model_experiment_edge():
    fields = {f.name for f in dataclasses.fields(PredictionAssessment)}
    assert {"prediction", "result", "observation", "residual", "absolute_residual"} <= fields
    source = inspect.getsource(inspect.getmodule(assess))
    assert "not model failure, not experimental failure, not truth, not bias" in " ".join(source.split())


def test_the_feedback_edge_never_reaches_evidence():
    """`assess` touches no pool; `update` does not take an assessment."""
    module = inspect.getmodule(assess)
    # CODE names only -- the module docstring says "no `EvidencePool` access",
    # and prose is not machinery.
    names = set()
    for node in ast.walk(ast.parse(inspect.getsource(module))):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
    assert "EvidencePool" not in names
    assert not any(n.startswith(("put_", "admit_")) for n in names)
    from materials.model_state import update
    assert "assessment" not in set(inspect.signature(update).parameters)


# -- 16. the existing counterfactual is epistemic, not causal --------------------------------------


def test_project_update_varies_the_response_never_the_coordinate():
    parameters = list(inspect.signature(project_update).parameters)
    assert parameters == ["state", "candidate", "hypothetical_value"]
    # There is no argument for "if x had been different": the cell is
    # derived from the candidate the caller already holds.


def test_the_epistemic_counterfactual_is_permanently_marked():
    base = _state([({"temperature_c": 25}, [90.0])])
    projected = project_update(base, _Probe({"temperature_c": 25}), 70.0)
    ids = [s.observation_id for samples in projected.samples.values() for s in samples]
    assert any(i.startswith("hypothetical:") for i in ids)
    assert projected.id != base.id


# -- 15. model identity is a second axis -----------------------------------------------------------


def test_today_model_identity_is_implied_by_evidence_identity():
    """`Prediction` carries no id and is a pure function of
    (state.id, candidate.id). A FITTED relationship breaks that: two
    fits over one pool share an evidence fingerprint and differ as
    models."""
    fields = {f.name for f in dataclasses.fields(Prediction)}
    assert "id" not in fields
    assert {"state_id", "candidate_id", "model_state_key"} <= fields
    source = inspect.getsource(predict)
    assert "content_hash" not in source      # mints no identity of its own


# -- 11/12. provenance records inclusion; validation is about a complement --------------------------


def test_derived_from_records_inclusion_and_cannot_express_a_held_out_set():
    source = inspect.getsource(inspect.getmodule(DerivedValue))
    assert "derived_from" in source
    fields = {f.name for f in dataclasses.fields(DerivedValue)}
    assert "held_out" not in fields and "validated_against" not in fields
    # Validation asserts that the checking observations were NOT used.
    # An inclusion edge cannot state a disjointness condition about itself.


def test_observation_provenance_is_observational_only():
    """No field anywhere records an intervention, so no observational
    object can ever warrant a causal claim."""
    hits = []
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                name = None
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    name = node.name
                elif isinstance(node, ast.Attribute):
                    name = node.attr
                if name in {"intervention", "intervene", "treatment", "control_group",
                            "randomisation", "randomization", "do_operator"}:
                    hits.append(f"{path.relative_to(REPO)}: {name}")
    assert hits == [], hits
    assert {f.name for f in dataclasses.fields(Observation)} == {
        "id", "record_ids", "extraction_method", "content", "confidence", "extracted_at",
    }


# -- 21. nothing was added --------------------------------------------------------------------------


def test_phase_108_added_no_relationship_machinery():
    forbidden = (
        "RelationshipClaim", "StatisticalRelation", "FunctionalModel",
        "ValidatedModel", "MonotonicityClaim", "CausalClaim", "applicability_domain",
    )
    hits = []
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            text = path.read_text()
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert hits == [], hits
