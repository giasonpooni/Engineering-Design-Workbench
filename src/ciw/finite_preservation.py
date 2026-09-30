"""Exact finite probability / compression / intervention witnesses.

The caller supplies complete finite tables, not executable source code. All
states are checked, including zero-probability states. No empirical or causal
meaning is inferred from a declared probability or deterministic map.
"""
from __future__ import annotations

from fractions import Fraction
import re
from typing import Any

from .control_contracts import detached, keys, record, text
from .operations.runner import check_seal
from .representation_morphisms import validate_registry
from .semantic_capabilities import SemanticRegistry

MAX_STATES = 64
RATIONAL_BOUND = 10**9
FIELDS = {"experiment_id", "projection_morphism_id", "intervention_id", "query_id",
          "query_unit", "fine_states", "coarse_states", "projection", "probabilities",
          "observable", "fine_intervention", "coarse_intervention"}
CLAIMS = {"exact_rational_arithmetic": True, "all_declared_states_checked": True,
          "zero_probability_states_checked": True, "probabilities_are_declared": True,
          "unique_inverse_inferred": False, "empirical_calibration_established": False,
          "general_morphism_law_proved": False, "causal_effects_established": False,
          "automatic_needle_authorization": False, "provider_execution": False,
          "canonical_state_mutated": False, "execution_authority": False}


def _states(value: Any) -> list[str]:
    if type(value) is not list or not 1 <= len(value) <= MAX_STATES:
        raise ValueError("A finite space requires 1..64 state labels")
    if any(type(s) is not str or not s.strip() or len(s) > 64 for s in value):
        raise ValueError("State labels must be bounded nonempty strings")
    if len(set(value)) != len(value):
        raise ValueError("Duplicate finite state label")
    return list(value)


def _rational(value: Any) -> Fraction:
    if type(value) is int:
        if abs(value) > RATIONAL_BOUND:
            raise ValueError("Rational input exceeds arithmetic bound")
        return Fraction(value)
    if type(value) is not str or len(value) > 48 or re.fullmatch(r"-?[0-9]+(?:/[0-9]+)?", value) is None:
        raise ValueError("Use an integer or exact rational string, not a float or boolean")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Invalid rational input") from exc
    if abs(result.numerator) > RATIONAL_BOUND or result.denominator > RATIONAL_BOUND:
        raise ValueError("Rational input exceeds arithmetic bound")
    return result


def _table(value: Any, domain: list[str], codomain: list[str]) -> dict[str, str]:
    keys(value, set(domain))
    if any(type(v) is not str or v not in codomain for v in value.values()):
        raise ValueError("Finite map must be total and stay within its declared codomain")
    return {s: value[s] for s in domain}


def _normalise(spec: dict) -> dict:
    keys(spec, FIELDS)
    fine, coarse = _states(spec["fine_states"]), _states(spec["coarse_states"])
    keys(spec["probabilities"], set(fine))
    keys(spec["observable"], set(fine))
    probabilities = {s: _rational(spec["probabilities"][s]) for s in fine}
    observable = {s: _rational(spec["observable"][s]) for s in fine}
    if any(p < 0 for p in probabilities.values()) or sum(probabilities.values()) != 1:
        raise ValueError("Declared probabilities must be nonnegative and sum exactly to one")
    result = {k: text(spec[k]) for k in ("experiment_id", "projection_morphism_id",
                                       "intervention_id", "query_id", "query_unit")}
    result.update(
        fine_states=fine, coarse_states=coarse,
        projection=_table(spec["projection"], fine, coarse),
        probabilities={s: str(probabilities[s]) for s in fine},
        observable={s: str(observable[s]) for s in fine},
        fine_intervention=_table(spec["fine_intervention"], fine, fine),
        coarse_intervention=_table(spec["coarse_intervention"], coarse, coarse),
    )
    return result


def _evaluate(spec: dict) -> dict:
    fine, coarse = spec["fine_states"], spec["coarse_states"]
    project, action, coarse_action = spec["projection"], spec["fine_intervention"], spec["coarse_intervention"]
    probability = {s: Fraction(spec["probabilities"][s]) for s in fine}
    observable = {s: Fraction(spec["observable"][s]) for s in fine}
    pushforward = {y: sum((probability[x] for x in fine if project[x] == y), Fraction()) for y in coarse}
    fibres, conflicts, mismatches = {}, [], []
    lifted_expectation, residual_variance = Fraction(), Fraction()
    query_exact = True
    for y in coarse:
        members = [x for x in fine if project[x] == y]
        mass = pushforward[y]
        mean = sum((probability[x] * observable[x] for x in members), Fraction()) / mass if mass else None
        variance = sum((probability[x] * (observable[x] - mean)**2 for x in members), Fraction()) / mass if mass else None
        targets = {project[action[x]] for x in members}
        constant = len({observable[x] for x in members}) <= 1
        query_exact = query_exact and constant
        fibres[y] = {
            "states": members, "probability": str(mass),
            "conditional_probabilities": {x: str(probability[x] / mass) for x in members} if mass else None,
            "conditional_mean": str(mean) if mean is not None else None,
            "conditional_variance": str(variance) if variance is not None else None,
            "conditional_status": "DEFINED" if mass else "ZERO_MASS_UNDEFINED",
            "query_constant_on_fibre": constant,
            "projected_intervention_targets": sorted(targets),
        }
        if mass:
            lifted_expectation += mass * mean
            residual_variance += mass * variance
        if len(targets) > 1:
            first = members[0]
            second = next(x for x in members if project[action[x]] != project[action[first]])
            conflicts.append({"coarse_state": y, "fine_states": [first, second],
                              "projected_targets": [project[action[first]], project[action[second]]]})
    left_distribution = {y: Fraction() for y in coarse}
    right_distribution = {y: Fraction() for y in coarse}
    for x in fine:
        left, right = project[action[x]], coarse_action[project[x]]
        left_distribution[left] += probability[x]
        right_distribution[right] += probability[x]
        if left != right:
            mismatches.append({"fine_state": x, "probability": str(probability[x]),
                               "project_after_intervention": left,
                               "intervene_after_projection": right})
    expectation = sum((probability[x] * observable[x] for x in fine), Fraction())
    return {
        "fine_state_count": len(fine), "coarse_state_count": len(coarse),
        "pushforward": {y: str(pushforward[y]) for y in coarse}, "fibres": fibres,
        "expectation": str(expectation), "conditional_expectation_integral": str(lifted_expectation),
        "expectation_preserved": expectation == lifted_expectation,
        "query_exact_on_all_declared_states": query_exact,
        "unresolved_within_fibre_variance": str(residual_variance),
        "deterministic_coarse_intervention_exists_on_image": not conflicts,
        "fibre_conflicts": conflicts,
        "commutativity_status": "PASS" if not mismatches else "FAIL",
        "commutativity_counterexamples": mismatches,
        "project_after_intervention_distribution": {y: str(left_distribution[y]) for y in coarse},
        "intervene_after_projection_distribution": {y: str(right_distribution[y]) for y in coarse},
        "intervened_distributions_equal": left_distribution == right_distribution,
    }


def finite_witness_from_spec(registry: dict, semantic: SemanticRegistry, spec: dict) -> dict:
    """Evaluate one completely declared finite square, preserving failures."""
    registry = validate_registry(registry, semantic)
    spec = _normalise(spec)
    morphism = registry["morphisms"].get(spec["projection_morphism_id"])
    if morphism is None or morphism["kind"] not in {"PROJECT", "COARSEN", "TRANSFORM"}:
        raise ValueError("Finite witness requires a declared projection/coarsening morphism")
    domain = registry["representations"][morphism["domain_representation_id"]]
    codomain = registry["representations"][morphism["codomain_representation_id"]]
    for rep in (domain, codomain):
        if rep["schema_id"] != "ciw.finite-state-label.v1":
            raise ValueError("Finite tables require explicit finite-state-label representation contracts")
    if spec["intervention_id"] not in domain["supported_interventions"]:
        raise ValueError("Fine representation does not declare the named intervention")
    results = _evaluate(spec)
    contract_support = (spec["intervention_id"] in codomain["supported_interventions"]
                        and spec["intervention_id"] in morphism["preservation"]["interventions"])
    return record(
        "finite-preservation", registry_ref=registry["record_digest"],
        morphism_ref=morphism["record_digest"], domain_ref=domain["record_digest"],
        codomain_ref=codomain["record_digest"], specification=spec, results=results,
        declared_coarse_intervention_support=contract_support,
        contract_and_finite_check_pass=contract_support and results["commutativity_status"] == "PASS",
        claims=CLAIMS,
    )


def validate_finite_witness(value: dict, registry: dict, semantic: SemanticRegistry) -> dict:
    """Re-evaluate from retained input tables; hashes alone do not prove results."""
    keys(value, {"schema", "record_digest", "registry_ref", "morphism_ref", "domain_ref", "codomain_ref",
                 "specification", "results", "declared_coarse_intervention_support",
                 "contract_and_finite_check_pass", "claims"})
    check_seal(value)
    expected = finite_witness_from_spec(registry, semantic, value["specification"])
    if value != expected:
        raise ValueError("Finite witness differs from exact recomputation or registry binding")
    return detached(value)


def require_finite_local_support(value: dict, registry: dict, semantic: SemanticRegistry) -> dict:
    """A refusal-safe evidence check, NOT a Needle plan or execution authority."""
    value = validate_finite_witness(value, registry, semantic)
    if not value["contract_and_finite_check_pass"]:
        raise ValueError("Local finite intervention lacks declared support or fails commutativity")
    return value


def example_specs() -> tuple[dict, dict, dict]:
    """Synthetic declared example and counterexample; no physical calibration."""
    scale = {"length_m": None, "time_s": None, "energy_j": None, "resolution": None,
             "label": "finite declared partition"}
    common = {
        "role": "STATE", "source_state_type": "declared-finite-state-space",
        "schema_id": "ciw.finite-state-label.v1", "quantity_semantics": "synthetic state labels",
        "unit_semantics": "dimensionless state labels", "frame_semantics": "declared finite space",
        "time_semantics": "one declared map application", "scale": scale,
        "uncertainty_semantics": "declared exact finite probabilities, not empirically calibrated",
        "supported_interventions": ["switch"], "recovery_route": None,
        "provenance_refs": [], "notes": "Synthetic arithmetic fixture; not a physical thermal model.",
    }
    reps = [
        {**common, "representation_id": "finite.fine.v1", "equivalence_contract": "EXACT",
         "preserved_queries": ["temperature-proxy"]},
        {**common, "representation_id": "finite.coarse.v1", "equivalence_contract": "LOSSY",
         "preserved_queries": ["conditional-temperature-proxy"]},
    ]
    morphism = {
        "morphism_id": "finite.partition.v1", "kind": "COARSEN",
        "domain_representation_id": "finite.fine.v1", "codomain_representation_id": "finite.coarse.v1",
        "semantic_capability": None, "parameter_names": [],
        "preconditions": ["complete finite tables and declared probability model"],
        "validity": {"assumptions": ["exact rational arithmetic"],
                     "operating_regime": ["at most 64 states per space"],
                     "failure_conditions": ["noncommuting intervention table"]},
        "preservation": {"queries": ["conditional-temperature-proxy"], "interventions": ["switch"],
                         "invariants": ["total probability"], "approximation_tolerance": None},
        "loss": {"class": "LOSSY", "description": "Multiple fine labels share one coarse label.", "metrics": {}},
        "uncertainty": {"behavior": "PROPAGATE", "method": "finite pushforward and conditional probabilities"},
        "reversibility": "NONE", "authority_requirements": [],
        "verification_requirements": ["exact commutativity on every declared state"],
        "provenance_refs": [], "notes": "Declared intervention support is tested, not assumed true.",
    }
    valid = {
        "experiment_id": "finite-compatible", "projection_morphism_id": "finite.partition.v1",
        "intervention_id": "switch", "query_id": "temperature-proxy", "query_unit": "K",
        "fine_states": ["cold-a", "cold-b", "warm-a", "warm-b"], "coarse_states": ["cold", "warm"],
        "projection": {"cold-a": "cold", "cold-b": "cold", "warm-a": "warm", "warm-b": "warm"},
        "probabilities": {x: "1/4" for x in ("cold-a", "cold-b", "warm-a", "warm-b")},
        "observable": {"cold-a": "270", "cold-b": "274", "warm-a": "290", "warm-b": "294"},
        "fine_intervention": {"cold-a": "warm-a", "cold-b": "warm-b", "warm-a": "cold-a", "warm-b": "cold-b"},
        "coarse_intervention": {"cold": "warm", "warm": "cold"},
    }
    invalid = detached(valid)
    invalid["experiment_id"] = "finite-incompatible"
    invalid["fine_intervention"] = {"cold-a": "warm-a", "cold-b": "cold-b", "warm-a": "cold-a", "warm-b": "warm-b"}
    invalid["coarse_intervention"] = {"cold": "cold", "warm": "warm"}
    return {"representations": reps, "morphisms": [morphism]}, valid, invalid
