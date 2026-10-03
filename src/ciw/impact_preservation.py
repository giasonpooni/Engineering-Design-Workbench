"""Typed preservation receipts for the narrow numerical impact workload.

The independently computed impact report supplies the evidence. This bridge
describes its exact request/result/report bindings and numerical obligations;
it neither executes a solver nor supplies a cross-scale commutative witness.
Reading a retained bundle reconstructs these declarations without repeating
the independent numerical verification.
"""
from __future__ import annotations

from copy import deepcopy

from .control_contracts import detached, keys
from .control_plane import CapabilityRegistry
from .impact_contract import EXPANSION_OBSERVABLES, validate_request
from .operations.runner import check_seal, digest, seal
from .preservation_contracts import (
    admission_gate_from_spec,
    contract_from_spec,
    validate_admission_gate,
    validate_contract,
    validate_verification,
    verification_from_spec,
)
from .representation_morphisms import registry_from_specs, validate_registry
from .semantic_capabilities import SemanticRegistry

SCHEMA = "ciw.impact-preservation.v1"
SOURCE = "impact.initial-reference.v1"
TARGET = "impact.sampled-trace.v1"
MORPHISM = "impact.spring-contact-simulation.v1"
PROPERTY_IDS = {
    "force_time": "impact.force-history.v1",
    "impulse": "impact.support-impulse.v1",
    "restitution": "impact.restitution.v1",
    "energy_accounting": "impact.energy-accounting.v1",
    "separation_time": "impact.separation-time.v1",
    **{name: "impact." + name.replace("_", "-") + ".v1"
       for name in EXPANSION_OBSERVABLES},
}
CLAIMS = {
    "uses_existing_preservation_contracts": True,
    "synthetic_numerical_scope_only": True,
    "physical_validation_established": False,
    "scale_preservation_established": False,
    "cross_scale_commutative_witness_supplied": False,
    "canonical_state_mutated": False,
    "state_admission_performed": False,
    "execution_authority": False,
}


def _semantic() -> SemanticRegistry:
    # The morphism is descriptive: an empty existing registry avoids loading
    # unrelated providers or inventing an executable semantic capability.
    return SemanticRegistry(CapabilityRegistry())


def _representation(identity, role, schema_id, refs, scale, queries):
    return {
        "representation_id": identity, "role": role,
        "source_state_type": "synthetic_undamped_point_mass_massless_spring",
        "schema_id": schema_id,
        "quantity_semantics": "signed compression, inward velocity, compression-only support force",
        "unit_semantics": "SI: s, m, m/s, N, N*s, J; restitution dimensionless",
        "frame_semantics": "one fixed support; inward normal positive",
        "time_semantics": "first contact t=0; contact and separating free flight",
        "scale": scale,
        "uncertainty_semantics": "declared numerical tolerances; no physical parameter uncertainty qualification",
        "equivalence_contract": "TASK_SPECIFIC",
        "preserved_queries": queries, "supported_interventions": [],
        "recovery_route": "retained request, solver trace and independent numerical report",
        "provenance_refs": refs,
        "notes": "No plate, damage, morphology or molecular state is represented. Scale entries are reference normalization scales, not multiscale validation.",
    }


def _effect(identity, tolerance, unit, metric):
    return {
        "property_id": identity, "effect": "BOUND",
        "output_property_id": identity, "transform_id": None,
        "bound": {"metric": metric, "upper_bound": tolerance, "unit": unit,
                  "composition": "ADDITIVE_ABSOLUTE"},
        "notes": "Acceptance threshold for this retained primary/refined numerical run only; no continuum, material or experimental error bound.",
    }


def _assemble(request, result, report):
    """Construct only from retained report values; do not rerun its arithmetic."""
    sem = _semantic()
    request_ref, result_ref, report_ref = digest(request), result["record_digest"], report["record_digest"]
    refs = [request_ref, result_ref, report_ref]
    reference, tolerances = report["reference"], request["tolerances"]
    scale = {
        "length_m": reference["maximum_compression_m"],
        "time_s": reference["contact_duration_s"],
        "energy_j": reference["initial_energy_j"],
        "resolution": None, "label": "analytical normalization scales for the declared synthetic contact",
    }
    queries = sorted(PROPERTY_IDS[name] for name in request["desired_observables"]
                     if name not in EXPANSION_OBSERVABLES)
    registry = registry_from_specs(
        [_representation(SOURCE, "MODEL", "ciw.impact-request.v1", [request_ref, report_ref], scale, queries),
         _representation(TARGET, "SIGNAL", "ciw.impact-result.v1", [result_ref, report_ref],
                         {**scale, "resolution": result["primary"]["dt_s"]}, queries)],
        [{"morphism_id": MORPHISM, "kind": "SIMULATE",
          "domain_representation_id": SOURCE, "codomain_representation_id": TARGET,
          "semantic_capability": None,
          "parameter_names": ["mass_kg", "stiffness_n_per_m", "initial_speed_m_per_s", "steps_per_contact"],
          "preconditions": ["strict bounded SI request", "zero initial compression, damping and contact gravity"],
          "validity": {
              "assumptions": ["point mass", "massless linear spring", "fixed support", "compression-only contact"],
              "operating_regime": ["the exact retained request and fixed contact-normal frame"],
              "failure_conditions": ["failed independent numerical checks", "requested plate, damage or molecular response"],
          },
          "preservation": {"queries": queries, "interventions": [], "invariants": [],
                           "approximation_tolerance": None},
          "loss": {"class": "TASK_SPECIFIC", "description": "finite sampled numerical path; higher physical observables explicitly unavailable",
                   "metrics": {}},
          "uncertainty": {"behavior": "UNKNOWN", "method": "numerical report thresholds only; physical uncertainty unqualified"},
          "reversibility": "NONE", "authority_requirements": [],
          "verification_requirements": ["independent retained analytic/history/invariant checks"],
          "provenance_refs": refs,
          "notes": "Declarative SIMULATE morphism over an existing operation. No automatic inverse or cross-scale witness.",
        }], sem,
    )
    # Each group maps exactly to existing verifier checks. Absolute SI bounds
    # use the same reference scales as those normalized checks.
    definitions = [
        ("impact.compression-history.v1", "analytic_normalized", reference["maximum_compression_m"], "m",
         "maximum_absolute_sampled_compression_error", ["analytic.compression_m"]),
        ("impact.velocity-history.v1", "analytic_normalized", request["model"]["initial_speed_m_per_s"], "m/s",
         "maximum_absolute_sampled_velocity_error", ["analytic.velocity_m_per_s"]),
        (PROPERTY_IDS["force_time"], "analytic_normalized", reference["peak_force_n"], "N",
         "maximum_absolute_sampled_force_error", ["analytic.force_n"]),
        (PROPERTY_IDS["impulse"], "impulse_relative", reference["support_impulse_n_s"], "N*s",
         "absolute_support_impulse_error", ["support_impulse"]),
        ("impact.momentum-balance.v1", "momentum_relative", reference["support_impulse_n_s"], "N*s",
         "maximum_absolute_all_history_momentum_residual", ["all_history_momentum_balance"]),
        (PROPERTY_IDS["energy_accounting"], "energy_relative", reference["initial_energy_j"], "J",
         "maximum_absolute_energy_drift", ["maximum_energy_drift"]),
        (PROPERTY_IDS["restitution"], "restitution_absolute", 1.0, "1",
         "absolute_restitution_error", ["restitution"]),
        (PROPERTY_IDS["separation_time"], "separation_relative", reference["contact_duration_s"], "s",
         "absolute_interpolated_separation_time_error", ["separation_event", "separation_time"]),
    ]
    effects = [_effect(identity, tolerances[tolerance] * normalization, unit, metric)
               for identity, tolerance, normalization, unit, metric, names in definitions]
    effects.append(_effect("impact.timestep-refinement.v1", tolerances["refinement_normalized"], "1",
                           "maximum_declared_normalized_refinement_change"))
    for name in sorted(EXPANSION_OBSERVABLES):
        effects.append({"property_id": PROPERTY_IDS[name], "effect": "FORGET",
                        "output_property_id": None, "transform_id": None, "bound": None,
                        "notes": "Declared tracked property is absent from this numerical schema; no claim that a richer physical state was simulated or reduced."})
    requirements = {
        "impact.schema-integrity.v1": (["schema_integrity"], "EXACT_ALGEBRA"),
        "impact.declared-contact-law.v1": ([label + "." + name for label in ("primary", "refined")
                                           for name in ("force_law", "compression_only_force")], "NUMERICAL_BOUND"),
        "impact.integrator-equations.v1": ([label + ".integrator_equations" for label in ("primary", "refined")], "NUMERICAL_BOUND"),
    }
    contract = contract_from_spec(registry, sem, {
        "contract_id": "impact.spring-contact-preservation.v1", "morphism_id": MORPHISM,
        "requires": list(requirements), "effects": effects,
        "notes": "Numerical sample and aggregate error thresholds qualified by this retained run; FORGET records schema omission, not molecular-to-component reduction.",
    })
    checks_by_name = {row["name"]: row for row in report["checks"]}

    def receipt(kind, identity, names, method):
        rows = [checks_by_name.get(name) for name in names]
        status = ("REFUTED" if any(row is not None and row["status"] == "FAIL" for row in rows)
                  else "VERIFIED" if all(row is not None and row["status"] == "PASS" for row in rows)
                  else "UNRESOLVED")
        return {"kind": kind, "property_id": identity, "status": status,
                "method": method if status != "UNRESOLVED" else "NOT_PERFORMED",
                "evidence_ref": report_ref,
                "notes": "Exact retained report checks: " + ", ".join(names),
                }

    checks = [receipt("REQUIRE", identity, names, method)
              for identity, (names, method) in requirements.items()]
    checks.extend(receipt("BOUND", identity,
                          [label + "." + name for label in ("primary", "refined") for name in names],
                          "NUMERICAL_BOUND")
                  for identity, tolerance, normalization, unit, metric, names in definitions)
    refinement_names = ["refinement." + name for name in (
        "compression_m", "velocity_m_per_s", "force_n", "support_impulse", "restitution",
        "peak_force", "maximum_compression", "separation_time")]
    checks.append(receipt("BOUND", "impact.timestep-refinement.v1", refinement_names, "NUMERICAL_BOUND"))
    for name in sorted(EXPANSION_OBSERVABLES):
        checks.append({"kind": "FORGET", "property_id": PROPERTY_IDS[name],
                       "status": "VERIFIED", "method": "EXACT_ALGEBRA", "evidence_ref": result_ref,
                       "notes": "Exact schema omission only: result represents no " + name + "; this does not establish a physical reduction."})
    verification = verification_from_spec(registry, sem, contract, {
        "verification_id": "impact.spring-contact-preservation-verification.v1",
        "source_state_ref": request_ref, "candidate_state_ref": result_ref,
        "checks": checks,
        "notes": "Typed receipt of the retained independent report. NUMERICAL_BOUND is acceptance at sampled times for this numerical model, not FORMAL_PROOF or experimental qualification.",
    })
    gate = admission_gate_from_spec(registry, sem, contract, verification, {
        "gate_id": "impact.spring-contact-preservation-gate.v1",
        "forbidden_forgets": sorted(PROPERTY_IDS[name] for name in request["desired_observables"]
                                    if name in EXPANSION_OBSERVABLES),
        "notes": "Eligibility for the declared numerical loss policy only; unsupported requested observables are refused. No canonical state admission.",
    })
    return seal({"schema": SCHEMA, "request_digest": request_ref, "result_digest": result_ref,
                 "report_digest": report_ref, "registry": registry, "contract": contract,
                 "verification": verification, "admission_gate": gate, "claims": deepcopy(CLAIMS)})


def build(request: dict, result: dict, report: dict) -> dict:
    """Bind an independently computed numerical report to existing typed APIs."""
    from .impact_verification import validate_report
    request = validate_request(request)
    validate_report(request, result, report)
    return _assemble(request, result, report)


def validate(bundle: dict, request: dict, result: dict, report: dict) -> dict:
    """Check retained structure and bindings without solving or reverifying."""
    from .impact_verification import validate_report
    keys(bundle, {"schema", "record_digest", "request_digest", "result_digest", "report_digest",
                  "registry", "contract", "verification", "admission_gate", "claims"})
    check_seal(bundle)
    request = validate_request(request)
    validate_report(request, result, report)
    if (bundle["schema"] != SCHEMA or bundle["claims"] != CLAIMS
            or bundle["request_digest"] != digest(request)
            or bundle["result_digest"] != result["record_digest"]
            or bundle["report_digest"] != report["record_digest"]):
        raise ValueError("Impact preservation bundle scope or content binding differs")
    sem = _semantic()
    validate_registry(bundle["registry"], sem)
    validate_contract(bundle["contract"], bundle["registry"], sem)
    validate_verification(bundle["verification"], bundle["registry"], sem, bundle["contract"])
    validate_admission_gate(bundle["admission_gate"], bundle["registry"], sem,
                            bundle["contract"], bundle["verification"])
    if bundle != _assemble(request, result, report):
        raise ValueError("Impact preservation receipt differs from retained report obligations")
    return detached(bundle)
