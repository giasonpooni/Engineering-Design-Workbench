"""Phase 110: falsification of "Claim" as a common-carrier ontology class.

VERDICT: REJECTED. No universal Claim carrier exists. Of the thirteen
signature fields surveyed, exactly ONE is genuinely common -- identity by
content hash -- and it is already implemented, as a FUNCTION
(`evidence.identity.content_hash`), not as a class. Everything a Claim
superclass would add is non-common.

THE CRITERION THAT DOES THE WORK
--------------------------------
A CLAIM CAN BE FALSE. A REPRESENTATION CAN ONLY BE ILL-SUITED.

An RBF kernel with lengthscale 18.0 is not wrong; a different lengthscale
is a different choice. "These two polymers are chemically similar" is a
claim and can be false. The same number carries both readings, and only
one of them is truth-apt. That single test separates the CLAIM layer from
the REPRESENTATION layer more reliably than any field does -- and it
immediately shows "representation" is itself too broad: an adjacency
SUPPLIED by the dataset is evidence, while an adjacency CHOSEN by the
modeller is representation. One word, two layers.

sec.1 SIGNATURE TABLE -- what is actually common

  subject                NON-COMMON  mutual information has none;
                         monotonicity's subject is a FUNCTION, not a
                         thing; a counterfactual's subject is one unit.
  object                 NON-COMMON  same reason.
  arity                  NON-COMMON  unary (monotonicity), binary
                         symmetric (correlation, similarity), n-ary
                         directed (regression), function-valued
                         (mechanistic law), distribution-valued (p(y|x)).
  directionality         NON-COMMON  forcing subject -> object onto
                         correlation and similarity ASSERTS A DIRECTION
                         THAT DOES NOT EXIST -- a false semantics, not a
                         harmless default.
  parameters             NON-COMMON  fitted coefficients / physical
                         constants with units / kernel hyperparameters /
                         none at all.
  assumptions            DOCUMENTATION ONLY. Every claim has some; they
                         range over noise models, physical regimes,
                         exchangeability and stationarity, with no
                         structure in common. A field that can only hold
                         prose is a comment, not a primitive.
  applicability domain   NON-COMMON  (Phase 106/108): a population, a
                         coordinate region, a convex hull, a physical
                         regime, or undefined.
  provenance kind        NON-COMMON  (Phase 109): four membership
                         semantics, two of them contradictory.
  validation relation    NON-COMMON  see sec.6 below.
  identity               COMMON -- content_hash over canonical content.
                         The only survivor.
  uncertainty            NON-COMMON  see sec.7 below.
  falsification cond.    NON-COMMON  and REPRESENTATIONS HAVE NONE.
  temporal semantics     NON-COMMON  a correlation is timeless, a
                         prediction has a before and an after, an
                         intervention has a moment.

sec.6 "VALIDATED" IS NOT A UNIVERSAL OPERATION
Held-out RMSE, mechanistic-constant agreement with independent
measurement, DIMENSIONAL analysis, conservation-law checks, causal
identification and external replication are six different operations.
Dimensional validation is the irreducible counterexample: it consumes NO
DATA AT ALL -- an equation is dimensionally sound or not, from its units
alone. A `validated_against: [observation ids]` field would be EMPTY for
it, and that emptiness is indistinguishable from "never validated". No
`validated = True` can carry both without semantic loss.

sec.7 UNCERTAINTY IS SIX THINGS
Measurement variance is a property of an instrument; parameter
uncertainty a property of a fit; predictive uncertainty a property of a
forecast; model uncertainty a property of a SET of models; epistemic
uncertainty a property of what is not known; causal-effect uncertainty a
property of an identification argument. Production has exactly one --
`Prediction.uncertainty`, a population variance over admitted samples --
and documents in place that it supports none of the others.

sec.14 IRREDUCIBLE COUNTEREXAMPLES -- one is enough to reject each

  Claim        I(X;Y) = 0.8 bits (symmetric, unitless, population-level,
               no subject) vs "this specimen would not have failed at
               40 C" (directed, one unit, not estimable from any amount
               of population data).
  Relation     similarity (symmetric, NOT truth-apt) vs "A causes B"
               (directed, truth-apt, needs exchangeability).
  Model        y = a*T + b, a total function on the line, vs a PDE whose
               "parameters" are boundary and initial conditions and whose
               "prediction" needs a solver and a discretisation.
               "Evaluate at x" names two different operations.
  Validation   held-out RMSE vs dimensional analysis (zero data).
  Prediction   production's `predict` -- defined only WHERE EVIDENCE
               EXISTS -- vs E[Y | do(X=x)], defined precisely where it
               does not and not computable from observational data at
               all. Same word, disjoint definitions.
  Similarity   k(x,y) = exp(-|x-y|^2 / 2*l^2) with a FITTED lengthscale
               vs a chemical similarity claim. The kernel cannot be
               wrong.

sec.10 THE EVIDENCE BOUNDARY IS STRUCTURAL, NOT CONVENTIONAL
`admit_observation` rejects a fitted coefficient with NO_RECORD_IDS: an
Observation must reference a real Record. The only way in is to MINT A
RECORD whose raw_content is the fitted number -- that is, to assert the
coefficient was EXTRACTED FROM A DOCUMENT. No document said it; a fit
produced it. And `admit_claimed_relationship` demands an
`observation_id`: a relationship must be ATTRIBUTED to something that
SAID it. A fit says nothing; it computes. Those two gates are the
epistemic transformation, and both require a misrepresentation to pass.

sec.11 THE "EVERYTHING IS A REFERENT" ESCAPE HATCH FAILS
`Referent.id = content_hash({natural_key, kind})`. Two DIFFERENT fits
over DIFFERENT data sharing one description COLLIDE INTO ONE OBJECT --
verified. Avoiding the collision means encoding parameters, assumptions
and provenance into `natural_key`: a schema inside a string, invisible to
every guard. The hatch either collides distinct claims or smuggles a
schema. A Referent is what a claim is ABOUT; it was never the claim.

sec.13 WHAT THE EXISTING ONTOLOGY LOSES -- exactly six things

  1 SYMMETRY. Nothing is symmetric. `ClaimedRelationship` is directed.
  2 COMPUTED vs STATED. `ClaimedRelationship` needs an observation that
    asserted it; `Observation` needs a record. A fit has neither.
  3 A SUBJECT THAT IS A FUNCTION. Monotonicity is about f, not a thing.
  4 WHERE THE CLAIM STOPS. No applicability domain anywhere.
  5 THE DISJOINTNESS. Validation-as-exclusion is inexpressible.
  6 WHAT THE DATA DETERMINED vs WHAT THE MODELLER CHOSE. A DerivedValue
    with derived_from=(observations) asserts its content IS a function of
    those inputs. A linear fit's content is a function of (observations,
    CHOICE OF FAMILY), and the family choice has no id and no provenance.
    The edge would be incomplete IN A WAY THAT IS INVISIBLE.

Item 6 is the one that matters most, and it is new here: the existing
ontology does not merely lack a slot, it would silently misdescribe the
claim's dependency structure.

sec.15 CLASSIFICATION
  Claim (universal carrier)          REJECTED
  Relation (universal)               REJECTED
  Model (universal)                  REJECTED
  Validation (universal status)      REJECTED
  Prediction (universal)             REJECTED
  Similarity (universal)             FALSE ANALOGY
  "Representation" as one layer      REJECTED -- adjacency splits
  "assumptions" as a field           SURVIVES AS DOCUMENTATION ONLY
  Identity by content hash           ALREADY REPRESENTED
  Referent as a claim carrier        REJECTED
  The four-layer separation itself   SURVIVES
  Truth-aptness as the layer test    SURVIVES

CONSEQUENCE FOR PRODUCTION: none. Zero production changes in this phase.
The existing ontology IS the minimal boundary: it holds exactly what can
be recorded without asserting something no one measured, and the six
losses above are all losses of things that would be claims, not evidence.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from evidence.admission import admit_claimed_relationship, admit_observation
from evidence.identity import content_hash
from evidence.pool import EvidencePool
from evidence.types import (
    ClaimedRelationship,
    DerivedValue,
    Observation,
    Referent,
    make_claimed_relationship,
    make_document,
    make_observation,
    make_referent,
    make_source,
)
from materials.model_state import Prediction
from workbench import theme

REPO = Path(__file__).resolve().parent.parent
PRODUCTION = ("evidence", "retrieval", "materials", "experiment", "workbench")

OBSERVATIONS = ("obs-a", "obs-b", "obs-c")


@pytest.fixture(autouse=True)
def _plain():
    theme.set_color(False)
    yield
    theme.set_color(None)


@pytest.fixture
def pool():
    p = EvidencePool()
    source = make_source(kind="paper", name="s")
    p.put_source(source)
    p.put_document(make_document(
        source_id=source.id, raw_content="x", retrieval_method="m",
        retrieved_at="2026-01-01T00:00:00Z"))
    return p


# -- 5. identity is the ONE common field -----------------------------------------------------------


MODEL_SPECS = {
    "linear": {"family": "linear", "params": {"a": -0.42, "b": 103.1},
               "assumes": ["additive noise"]},
    "polynomial": {"family": "poly2", "params": {"a": -0.004, "b": 0.13, "c": 88.0},
                   "assumes": ["additive noise"]},
    "arrhenius": {"family": "arrhenius", "params": {"E_a": 41200.0, "A": 8.1e-3},
                  "assumes": ["single activated process", "T in kelvin"]},
    "gaussian_process": {"family": "gp", "params": {"kernel": "rbf", "lengthscale": 18.0,
                                                    "sigma": 4.1},
                         "assumes": ["stationarity", "smoothness"]},
}


def test_four_models_over_identical_evidence_are_four_distinct_claims():
    fitted_from = sorted(OBSERVATIONS)
    ids = {
        name: content_hash({**spec, "fitted_from": fitted_from})
        for name, spec in MODEL_SPECS.items()
    }
    assert len(set(ids.values())) == 4
    assert content_hash({"observations": fitted_from}) not in set(ids.values())


def test_params_does_not_mean_the_same_thing_across_the_four():
    """Coefficients, physical constants with units, and kernel
    hyperparameters. `params` shares a name and nothing else."""
    assert set(MODEL_SPECS["linear"]["params"]) == {"a", "b"}
    assert set(MODEL_SPECS["arrhenius"]["params"]) == {"E_a", "A"}
    assert "kernel" in MODEL_SPECS["gaussian_process"]["params"]
    # The GP's "parameter" names a FUNCTION; the others name numbers.


# -- 2/3. arity and directionality are not universal ------------------------------------------------


ARITIES = {
    "monotonicity": "unary (its subject is a FUNCTION)",
    "correlation": "binary SYMMETRIC",
    "mutual_information": "binary SYMMETRIC",
    "similarity": "binary SYMMETRIC",
    "regression": "n-ary DIRECTED",
    "interpolation": "n-ary DIRECTED",
    "mechanistic_law": "function-valued",
    "conditional_distribution": "distribution-valued",
    "counterfactual": "unary over ONE UNIT",
}


def test_no_universal_arity_exists():
    shapes = {v.split()[0] for v in ARITIES.values()}
    assert shapes == {"unary", "binary", "n-ary", "function-valued", "distribution-valued"}


def test_the_only_directed_binary_object_cannot_hold_a_symmetric_claim():
    fields = {f.name for f in dataclasses.fields(ClaimedRelationship)}
    assert {"from_referent_id", "to_referent_id"} <= fields
    # Forcing a correlation into from/to asserts a direction that is not
    # there -- a false semantics, not a harmless default.
    symmetric = {k for k, v in ARITIES.items() if "SYMMETRIC" in v}
    assert symmetric == {"correlation", "mutual_information", "similarity"}


# -- 9. truth-aptness is the layer test -------------------------------------------------------------


TRUTH_APT = {
    "correlation coefficient": True,
    "mechanistic law": True,
    "monotonicity of f": True,
    "causal effect estimate": True,
    "rbf kernel with lengthscale 18.0": False,
    "a 32-dimensional embedding": False,
    "a chosen similarity function": False,
}


def test_a_claim_can_be_false_a_representation_can_only_be_ill_suited():
    claims = {k for k, v in TRUTH_APT.items() if v}
    representations = {k for k, v in TRUTH_APT.items() if not v}
    assert len(claims) == 4 and len(representations) == 3
    # A different lengthscale is a different CHOICE, never a correction.


def test_representation_is_itself_too_broad_because_adjacency_splits():
    """An adjacency SUPPLIED by the dataset is evidence; an adjacency
    CHOSEN by the modeller is representation. One word, two layers."""
    supplied = {"source": "dataset", "truth_apt": True}
    chosen = {"source": "modeller", "truth_apt": False}
    assert supplied["truth_apt"] != chosen["truth_apt"]


# -- 10. the evidence boundary is structural --------------------------------------------------------


def test_a_fitted_coefficient_cannot_be_admitted_as_an_observation(pool):
    fitted = make_observation(
        record_ids=(), extraction_method="fit:linear", content={"slope": -0.42},
        confidence=0.9, extracted_at="2026-01-01T00:00:00Z")
    errors = admit_observation(pool, fitted)
    assert isinstance(errors, list)
    assert {e.code for e in errors} == {"NO_RECORD_IDS"}
    # The only way in is to mint a Record whose raw_content is the fitted
    # number -- asserting a document said what a fit computed.


def test_a_correlation_cannot_be_admitted_as_a_claimed_relationship(pool):
    relationship = make_claimed_relationship(
        from_referent_id="r1", to_referent_id="r2", type="correlates_with",
        observation_id="does-not-exist", confidence=0.8)
    errors = admit_claimed_relationship(pool, relationship)
    assert isinstance(errors, list)
    assert "UNKNOWN_OBSERVATION" in {e.code for e in errors}
    # A relationship must be ATTRIBUTED to something that SAID it.


def test_observation_requires_a_record_and_relationship_requires_an_observation():
    assert "record_ids" in {f.name for f in dataclasses.fields(Observation)}
    assert "observation_id" in {f.name for f in dataclasses.fields(ClaimedRelationship)}


# -- 11. the Referent escape hatch fails -------------------------------------------------------------


def test_two_distinct_models_collide_into_one_referent():
    label = "linear model of tensile_strength vs T"
    first = make_referent(natural_key=label, kind="concept")
    second = make_referent(natural_key=label, kind="concept")
    assert first.id == second.id
    # Identity is content_hash({natural_key, kind}) and nothing else.
    assert {f.name for f in dataclasses.fields(Referent)} == {"id", "natural_key", "kind"}


def test_a_referent_carries_no_parameters_assumptions_or_applicability():
    fields = {f.name for f in dataclasses.fields(Referent)}
    for absent in ("parameters", "assumptions", "applicability_domain", "derived_from", "method"):
        assert absent not in fields


# -- 13. the six exact losses -----------------------------------------------------------------------


def test_no_existing_object_has_a_symmetric_relation():
    for cls in (Observation, ClaimedRelationship, DerivedValue, Prediction, Referent):
        fields = {f.name for f in dataclasses.fields(cls)}
        assert not {"between", "pair", "unordered"} & fields


def test_no_existing_object_takes_a_function_as_its_subject():
    for cls in (Observation, ClaimedRelationship, DerivedValue, Referent):
        fields = {f.name for f in dataclasses.fields(cls)}
        for absent in ("function", "constrains", "holds_over"):
            assert absent not in fields


def test_derived_from_would_misdescribe_a_fit_s_dependency_structure():
    """THE SHARPEST LOSS. `derived_from=(observations)` asserts the content
    IS a function of those inputs. A linear fit's content is a function of
    (observations, CHOICE OF FAMILY) -- and the family choice has no id
    and no provenance, so the edge is incomplete INVISIBLY."""
    fitted_from = sorted(OBSERVATIONS)
    linear = content_hash({**MODEL_SPECS["linear"], "fitted_from": fitted_from})
    arrhenius = content_hash({**MODEL_SPECS["arrhenius"], "fitted_from": fitted_from})
    assert linear != arrhenius
    # Identical derived_from, different content: derived_from does not
    # determine the object, yet claims to.
    fields = {f.name for f in dataclasses.fields(DerivedValue)}
    assert "family" not in fields and "chosen_by" not in fields


# -- 6/7. validation and uncertainty are not universal ----------------------------------------------


VALIDATION_KINDS = {
    "held_out_rmse": "consumes observations",
    "mechanistic_constant_agreement": "consumes an independent measurement",
    "dimensional_analysis": "consumes NO DATA",
    "conservation_law": "consumes NO DATA",
    "causal_identification": "consumes an argument, not data",
    "external_replication": "consumes a whole independent study",
}


def test_dimensional_validation_consumes_no_data_at_all():
    """The irreducible counterexample to a universal `validated` status:
    an empty `validated_against` is indistinguishable from never
    validated."""
    dataless = {k for k, v in VALIDATION_KINDS.items() if "NO DATA" in v}
    assert dataless == {"dimensional_analysis", "conservation_law"}
    assert len(VALIDATION_KINDS) == 6


def test_production_has_exactly_one_uncertainty_and_documents_its_limits():
    fields = {f.name for f in dataclasses.fields(Prediction)}
    assert "uncertainty" in fields
    for absent in ("parameter_uncertainty", "model_uncertainty", "epistemic_uncertainty"):
        assert absent not in fields
    text = " ".join((REPO / "materials" / "model_state.py").read_text().split())
    assert "do not support any of those claims, and none is fabricated here" in text


# -- 15. nothing was added ---------------------------------------------------------------------------


def test_phase_110_added_no_superclass():
    forbidden = {
        "Claim", "Relation", "Model", "Validation", "Similarity",
        "ClaimCarrier", "AbstractClaim",
    }
    hits = []
    for package in PRODUCTION:
        for path in sorted((REPO / package).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                # EXACT class names -- `ClaimedRelationship` and `ModelState`
                # merely start with two of these words.
                if isinstance(node, ast.ClassDef) and node.name in forbidden:
                    hits.append(f"{path.relative_to(REPO)}: {node.name}")
    assert hits == [], hits


def test_the_only_universal_is_a_function_not_a_class():
    """`content_hash` is the single genuinely common field's
    implementation, and it is already here."""
    module = (REPO / "evidence" / "identity.py").read_text()
    classes = [n.name for n in ast.walk(ast.parse(module)) if isinstance(n, ast.ClassDef)]
    assert classes == []
    functions = [n.name for n in ast.walk(ast.parse(module)) if isinstance(n, ast.FunctionDef)]
    assert "content_hash" in functions
