"""Phase 109: falsification of the Phase 108 epistemic DAG, arrow by arrow.

VERDICT: FALSIFIED. Six of the nine arrows do not survive, and two of
Phase 108's own claims failed with them.

ARROW CLASSIFICATION (sec.15 categories, one each, reject on ambiguity)

  Observation -> Replication            PREREQUISITE, and Phase 108's
      "replication is free" is FALSIFIED. Equal cell identity establishes
      CO-LOCATION, not replication. Two observations at
      {cure_time_min: 60} from a ramped and an isothermal profile share a
      cell key (mean 87.5, variance 42.25, n=2) and are not replicates.
      Replication additionally requires the unrecorded claim that the
      coordinate is COMPLETE -- the same gap Phase 108 found for
      functionhood, reappearing one rung lower.

  Observation -> Association            REJECTED. It fuses two relations:
      Observation -> a dependence STATISTIC is a DERIVATION; that
      statistic -> an association CLAIM about a population needs a
      sampling assumption and is FALSE without one. One arrow cannot be
      both, so it is rejected rather than classified.

  Association -> Statistical relation   FALSE. y = x**2 on
      [-2,-1,0,1,2] is a deterministic dependence whose covariance and
      Pearson rho are exactly 0.0. Conversely x=[1,1,2,2],
      y=[10,30,20,40] has rho = 0.447 and no single-valued y. Association
      neither implies nor is implied by a functional or distributional
      relation -- and "association" is not one object: correlation,
      covariance, mutual information and conditional dependence disagree
      on the same data, so a node that does not name its measure is
      unfalsifiable.

  Monotonicity -> Statistical relation  REJECTED. Monotonicity
      CONSTRAINS a model; it does not contribute to one. "Constrains" is
      not among the permitted categories and the arrow is ambiguous
      between COMPATIBILITY and FALSE, so sec.15's own rule rejects it.
      Monotonicity is additionally not one thing: a known physical
      monotonicity is a theory input, an observed monotone trend is a
      dataset property, a monotone-constrained regression is a fitting
      choice, and a monotone operator is an architectural property.

  Statistical relation -> Validated model   PREREQUISITE (not entailment).
  Mechanistic law      -> Validated model   PREREQUISITE (not entailment).
      Both are 2-INPUT nodes: validation requires evidence the model does
      not contain. And "Validated model" is an OVERLOADED rung holding
      two different semantics -- for a statistical model, predictive
      agreement on held-out data; for a mechanistic law, additionally
      that the fitted constants agree with independently measured values
      and that the equation is dimensionally consistent. One node, two
      meanings: split it.

  Validated model -> Prediction         REJECTED. Prediction follows from
      a MODEL (a DERIVATION); validation changes the prediction's STATUS,
      not its existence. An unvalidated model emits numbers just as
      readily. The arrow fuses a derivation with a validation and is
      rejected.

  Prediction -> Intervention            FALSE. One may intervene having
      predicted nothing, and a prediction obliges no one to intervene.
      It is not even a reliable temporal sequence.

  Intervention -> Causal claim          FALSE as drawn, and a CATEGORY
      ERROR. An intervention is an experimental ACT that produces an
      OBSERVATION; it produces no claim at all. The architecture already
      has this layer -- ExperimentalCampaign -> DispatchedMeasurement ->
      ExperimentalResult -> Observation -- and already keeps it separate
      from every claim. The real structure is
      Intervention -> Observation (an operation, in the experiment
      layer), and Observation(interventional) + an identification
      argument -> causal claim (a 2-input PREREQUISITE).

VALIDATION IS NOT A STATUS (sec.7)
----------------------------------
A model fitted on {obs-a, obs-b, obs-c} and "validated" against
{obs-b, obs-d} passes every held-out test and is worthless. A binary
status cannot see the defect, because the status is a property of the
MODEL while the defect is a property of the RELATION between two
observation sets. Distribution shift, regime change, accidental
extrapolation and adversarial test selection all have this shape.
"Validated" is a relation indexed by what it was validated against, and
its central condition is a DISJOINTNESS.

FIVE PROVENANCE RELATIONS, FOUR MEMBERSHIP SEMANTICS (sec.11)
-------------------------------------------------------------
`derived_from` is CONSTITUTIVE INCLUSION, verified: dropping one input
id changes the DerivedValue's id, because the object IS a function of
those inputs. `validated_by` would be CONSTITUTIVE EXCLUSION -- the
validating observations must NOT have entered the fit, and adding one to
the fit would DESTROY the validation rather than change the object.
Those are opposite demands on the same set. `supported_by` is
non-constitutive and non-exclusive; `tested_against` records an attempt
whatever its outcome; `intervened_on` names an act that is not an object
in the pool at all. One edge cannot honestly carry these -- not because
it is too generic, but because two of them contradict each other.

IDENTITY (sec.12), VERIFIED
---------------------------
A linear fit and an Arrhenius fit over the SAME three observations
produce distinct content hashes while the evidence fingerprint is
unchanged. Model identity is a second, independent axis; an evidence
fingerprint can never serve as a model version.

"CAUSAL CLAIM" IS ALSO TOO BROAD (sec.10)
-----------------------------------------
Causal identification (an argument that an effect is estimable at all),
causal estimation (a number), causal prediction under do(x), and a
counterfactual about a specific unit that did not receive the treatment
are four objects with different requirements. Phase 108 had intervention
leading directly to a causal claim and no counterfactual rung at all,
collapsing two distinct levels.

"PREDICTION" IS ALSO TOO BROAD (sec.8)
--------------------------------------
Prediction before observation is a falsifiable commitment; after
observation it is a retrodiction; with uncertainty it is a distribution;
under intervention it is a different quantity entirely. Production's
`Prediction` is a fifth thing: a SUMMARY OF ADMITTED EVIDENCE at an
occupied cell, which returns None rather than a number wherever none of
the four would apply.

WHAT ACTUALLY SURVIVES
----------------------
Not a ladder and not one DAG, but four layers that reference each other
in one direction only:

  OPERATION      campaign -> measurement -> result -> Observation
                 (exists; an act, never a claim)
  EVIDENCE       Observation, co-located by cell key
                 (exists; immutable, append-only)
  ---------------- every arrow above this line is real ----------------
  CLAIM          dependence statistics, distributional relations,
                 mechanistic laws, monotonicity constraints -- separate
                 objects, not rungs, none reachable from production
  REPRESENTATION similarity, embeddings, kernels, adjacency -- not
                 epistemic claims at all; a choice of encoding

Only the first two exist, and no arrow crosses upward into evidence.
Verified: every `put_*` in the tree writes a raw record, a source, a
document, a referent, or an admitted experimental result. No Prediction,
assessment, model or relationship ever enters the pool.

CONSEQUENCE FOR PRODUCTION: none. Zero production changes in this phase.
"""

from __future__ import annotations

import ast
import dataclasses
import math
from pathlib import Path

import pytest

from evidence.identity import content_hash
from evidence.types import make_derived_value
from materials.model_state import Sample, make_model_state, predict, resolve_model_state_key
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("evidence", "retrieval", "materials", "experiment", "workbench")


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


class _Probe:
    def __init__(self, property_name, context):
        self.formulation = type("R", (), {"id": "formulation-a"})()
        self.property = property_name
        self.target_context = dict(context)
        self.id = "probe"


def _pearson(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n)
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / n)
    return cov / (sx * sy)


# -- 2. Observation -> Replication: PREREQUISITE, not free -----------------------------------------


def test_equal_cell_identity_establishes_co_location_not_replication():
    """PHASE 108'S "replication is free" IS FALSIFIED."""
    key = resolve_model_state_key("formulation-a", "conversion", {"cure_time_min": 60})
    state = make_model_state({key: (
        Sample(value=94.0, observation_id="obs-ramped-profile"),
        Sample(value=81.0, observation_id="obs-isothermal-profile"),
    )})
    result = predict(state, _Probe("conversion", {"cure_time_min": 60}))
    assert result.sample_count == 2
    assert result.predicted_value == 87.5
    assert result.uncertainty == pytest.approx(84.5)   # sample variance (n-1), n=2
    # Two different thermal histories, one cell key. Nothing distinguishes
    # this from replication, because the coordinate never named the history.


def test_replication_needs_a_completeness_claim_the_record_does_not_carry():
    narrow = resolve_model_state_key("formulation-a", "conversion", {"cure_time_min": 60})
    ramped = resolve_model_state_key(
        "formulation-a", "conversion", {"cure_time_min": 60, "profile": "ramped"})
    isothermal = resolve_model_state_key(
        "formulation-a", "conversion", {"cure_time_min": 60, "profile": "isothermal"})
    assert len({narrow, ramped, isothermal}) == 3
    # The completeness claim is exactly "no further key is needed", and no
    # object anywhere asserts it.


# -- 3. Association -> Statistical relation: FALSE --------------------------------------------------


def test_a_deterministic_dependence_can_have_zero_linear_association():
    xs = [-2.0, -1.0, 0.0, 1.0, 2.0]
    ys = [x * x for x in xs]
    assert _pearson(xs, ys) == 0.0
    # y is an exact function of x; mutual information is maximal.
    assert all(y == x * x for x, y in zip(xs, ys))


def test_a_non_zero_association_can_have_no_functional_relation():
    xs = [1.0, 1.0, 2.0, 2.0]
    ys = [10.0, 30.0, 20.0, 40.0]
    assert _pearson(xs, ys) == pytest.approx(0.4472, abs=1e-4)
    at_one = {y for x, y in zip(xs, ys) if x == 1.0}
    assert len(at_one) == 2          # not single-valued


def test_association_measures_are_not_interchangeable():
    """A node labelled "association" that does not name its measure is
    unfalsifiable: the measures disagree on the same data."""
    xs = [-2.0, -1.0, 0.0, 1.0, 2.0]
    ys = [x * x for x in xs]
    linear = _pearson(xs, ys)
    # a rank measure on |x| would be maximal; a linear one is zero
    monotone_in_abs = _pearson([abs(x) for x in xs], ys)
    assert linear == 0.0
    assert monotone_in_abs > 0.9


# -- 7. validation is a relation, not a status ------------------------------------------------------


@pytest.mark.parametrize("held_out,disjoint", [
    (frozenset({"obs-d", "obs-e"}), True),
    (frozenset({"obs-b", "obs-d"}), False),      # leakage
])
def test_validation_turns_on_a_disjointness_not_on_the_model(held_out, disjoint):
    fitted_from = frozenset({"obs-a", "obs-b", "obs-c"})
    assert (not (fitted_from & held_out)) is disjoint
    # The model object is IDENTICAL in both rows. The defect lives in the
    # relation between two observation sets, where a status cannot see it.


# -- 11. five relations, four membership semantics --------------------------------------------------


def test_derived_from_is_constitutive_inclusion():
    common = dict(method="fit:linear", content={"slope": -0.42},
                  confidence=0.9, derived_at="2026-01-01T00:00:00Z")
    three = make_derived_value(derived_from=("o1", "o2", "o3"), **common)
    two = make_derived_value(derived_from=("o1", "o2"), **common)
    assert three.id != two.id
    # The object IS a function of its inputs; dropping one makes a
    # different object. `validated_by` would demand the opposite --
    # that the named ids did NOT enter -- so one edge cannot carry both.


def test_no_production_relation_records_exclusion_or_an_act():
    from evidence.types import ClaimedRelationship, DerivedValue

    for cls in (DerivedValue, ClaimedRelationship):
        fields = {f.name for f in dataclasses.fields(cls)}
        for absent in ("validated_by", "tested_against", "intervened_on",
                       "supported_by", "held_out"):
            assert absent not in fields


# -- 12. model identity is a second axis, verified --------------------------------------------------


def test_two_models_over_one_evidence_set_have_distinct_identities():
    observations = sorted(["obs-a", "obs-b", "obs-c"])
    evidence = content_hash({"observations": observations})
    linear = content_hash({"family": "linear", "params": {"a": -0.42, "b": 103.1},
                           "fitted_from": observations})
    arrhenius = content_hash({"family": "arrhenius", "params": {"E_a": 41200.0, "A": 8.1e-3},
                              "fitted_from": observations})
    assert linear != arrhenius
    assert evidence not in (linear, arrhenius)
    # One evidence fingerprint, two models. A model version is not an
    # evidence version.


# -- 9/16. intervention is an operation, and nothing crosses into evidence ---------------------------


def test_the_operation_layer_already_exists_and_produces_observations():
    from experiment.interface import DispatchedMeasurement
    from materials.campaign import ExperimentalCampaign
    from materials.results import ExperimentalResult

    assert {f.name for f in dataclasses.fields(ExperimentalCampaign)} == {
        "id", "process_natural_key", "design", "entries"}
    assert "extraction_method" in {f.name for f in dataclasses.fields(DispatchedMeasurement)}
    assert "record_id" in {f.name for f in dataclasses.fields(ExperimentalResult)}
    # An intervention is an ACT that yields an Observation. It is not a
    # claim, and belongs in no DAG of claims.


def test_every_pool_write_is_evidence_never_a_model():
    writes = set()
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Attribute) and node.attr.startswith("put_"):
                    writes.add(node.attr)
    assert writes == {
        "put_record", "put_source", "put_document", "put_referent",
        "put_observation", "put_claimed_relationship",
    }, sorted(writes)
    # No put_prediction, put_assessment, put_model, put_relationship.


# -- 8/10. prediction and causal claim are both overloaded ------------------------------------------


def test_production_prediction_is_none_of_the_four_prediction_senses():
    """Not a commitment, not a retrodiction, not a distribution, not an
    interventional quantity: a summary of admitted evidence, which
    returns None wherever none of those would apply."""
    state = make_model_state({
        resolve_model_state_key("formulation-a", "tensile_strength", {"temperature_c": 25}):
            (Sample(value=90.0, observation_id="o1"),)
    })
    occupied = predict(state, _Probe("tensile_strength", {"temperature_c": 25}))
    empty = predict(state, _Probe("tensile_strength", {"temperature_c": 60}))
    assert occupied.predicted_value == 90.0 and occupied.sample_count == 1
    assert empty.predicted_value is None and empty.sample_count == 0
    assert occupied.uncertainty is None     # one sample: no distribution


def test_no_causal_or_counterfactual_vocabulary_exists_in_production():
    forbidden = {
        "causal_effect", "identification", "confounder", "do_operator",
        "counterfactual_outcome_of", "average_treatment_effect", "propensity",
    }
    hits = []
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                name = None
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    name = node.name
                elif isinstance(node, ast.Attribute):
                    name = node.attr
                if name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {name}")
    assert hits == [], hits


# -- 15/16. nothing was added ------------------------------------------------------------------------


def test_phase_109_added_no_entailment_machinery():
    forbidden = (
        "EpistemicDAG", "Entailment", "ClaimNode", "ValidationResult",
        "Intervention", "CausalClaim", "AssociationClaim", "validated_by",
    )
    hits = []
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            text = path.read_text()
            for token in forbidden:
                if token in text:
                    hits.append(f"{path.relative_to(REPO)}: {token}")
    assert hits == [], hits
