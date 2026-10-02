"""Typed receipts for the narrow synthetic crush/contact numerical workload.

The independent numerical report supplies evidence. This bridge declares and
binds its exact request/result/report obligations through the existing typed
morphism, preservation, verification and eligibility APIs. Retained inspection
does not run a solver or repeat the numerical audit.
"""
from __future__ import annotations

from copy import deepcopy

from .control_contracts import detached, keys
from .control_plane import CapabilityRegistry
from .impact_crush_contract import EXPANSION_OBSERVABLES, validate_request
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

SCHEMA = "ciw.impact-crush-preservation.v1"
SOURCE = "impact.crush-initial-reference.v1"
TARGET = "impact.crush-sampled-trace.v1"
MORPHISM = "impact.crush-contact-simulation.v1"
PROPERTY_IDS = {
    "force_time": "impact.crush-force-history.v1",
    "impulse": "impact.crush-support-impulse.v1",
    "restitution": "impact.crush-restitution.v1",
    "energy_accounting": "impact.crush-total-energy-accounting.v1",
    "separation_time": "impact.crush-separation-time.v1",
    "plastic_work": "impact.crush-plastic-work.v1",
    "residual_compression": "impact.crush-residual-compression.v1",
    **{name: "impact.crush-" + name.replace("_", "-") + ".v1"
       for name in EXPANSION_OBSERVABLES},
}
CLAIMS = {
    "uses_existing_preservation_contracts": True,
    "synthetic_numerical_scope_only": True,
    "physical_validation_established": False,
    "hardness_established": False,
    "material_damage_established": False,
    "molecular_response_established": False,
    "scale_preservation_established": False,
    "cross_scale_commutative_witness_supplied": False,
    "canonical_state_mutated": False,
    "state_admission_performed": False,
    "execution_authority": False,
}


def _semantic() -> SemanticRegistry:
    # Descriptive SIMULATE declaration only: no executable semantic provider
    # is registered, no new controller or execution authority is introduced.
    return SemanticRegistry(CapabilityRegistry())


def _representation(identity, role, schema_id, refs, scale, queries):
    return {
        "representation_id": identity, "role": role,
        "source_state_type": "synthetic_point_mass_unilateral_elastic_perfectly_plastic_spring",
        "schema_id": schema_id,
        "quantity_semantics": "signed total compression, inward velocity, compression-only support force, nonnegative residual plastic compression and dissipated plastic work",
        "unit_semantics": "SI: s, m, m/s, N, N*s, J; restitution dimensionless; stiffness N/m and yield force N are effective spring parameters",
        "frame_semantics": "one fixed support; inward normal positive; contact gap measured relative to residual plastic compression",
        "time_semantics": "first contact t=0; loading, unloading and separating free flight",
        "scale": scale,
        "uncertainty_semantics": "declared numerical thresholds only; no physical parameter uncertainty qualification",
        "equivalence_contract": "TASK_SPECIFIC",
        "preserved_queries": queries, "supported_interventions": [],
        "recovery_route": "retained strict request, five-field solver trace and independent numerical report",
        "provenance_refs": refs,
        "notes": "Plastic compression and plastic work belong to a synthetic effective spring. No plate, rate, thermal, damage, fracture, morphology or molecular state is represented. Scale entries normalize numerical checks and do not establish multiscale validation.",
    }


def _effect(identity, tolerance, unit, metric):
    return {
        "property_id": identity, "effect": "BOUND",
        "output_property_id": identity, "transform_id": None,
        "bound": {"metric": metric, "upper_bound": tolerance, "unit": unit,
                  "composition": "ADDITIVE_ABSOLUTE"},
        "notes": "Acceptance threshold for this retained primary/refined synthetic numerical run only; no experimental, continuum or material constitutive error bound.",
    }


def _assemble(request, result, report):
    """Assemble declarations from retained check statuses without replaying them."""
    sem = _semantic()
    request_ref, result_ref, report_ref = digest(request), result["record_digest"], report["record_digest"]
    refs = [request_ref, result_ref, report_ref]
    reference, tolerances = report["reference"], request["tolerances"]
    scale = {
        "length_m": reference["maximum_compression_m"],
        "time_s": reference["contact_duration_s"],
        "energy_j": reference["initial_energy_j"],
        "resolution": None,
        "label": "analytical normalization scales for the declared synthetic crush/contact",
    }
    queries = sorted(PROPERTY_IDS[name] for name in request["desired_observables"]
                     if name not in EXPANSION_OBSERVABLES)
    registry = registry_from_specs(
        [_representation(SOURCE, "MODEL", "ciw.impact-crush-request.v1", [request_ref, report_ref], scale, queries),
         _representation(TARGET, "SIGNAL", "ciw.impact-crush-result.v1", [result_ref, report_ref],
                         {**scale, "resolution": result["primary"]["dt_s"]}, queries)],
        [{"morphism_id": MORPHISM, "kind": "SIMULATE",
          "domain_representation_id": SOURCE, "codomain_representation_id": TARGET,
          "semantic_capability": None,
          "parameter_names": ["mass_kg", "stiffness_n_per_m", "initial_speed_m_per_s", "yield_force_n", "steps_per_contact"],
          "preconditions": ["strict bounded SI request", "zero initial compression, plastic compression, damping and contact gravity"],
          "validity": {
              "assumptions": ["point mass", "massless effective elastic perfectly plastic spring", "fixed support", "compression-only contact", "nonnegative monotonic plastic compression", "plastic work equals yield force times plastic compression"],
              "operating_regime": ["the exact retained request and fixed contact-normal frame"],
              "failure_conditions": ["failed independent numerical checks", "requested plate, rate, thermal, damage, fracture or molecular response"],
          },
          "preservation": {"queries": queries, "interventions": [], "invariants": [],
                           "approximation_tolerance": None},
          "loss": {"class": "TASK_SPECIFIC", "description": "finite sampled synthetic numerical path; richer physical observables explicitly unavailable",
                   "metrics": {}},
          "uncertainty": {"behavior": "UNKNOWN", "method": "numerical report thresholds only; physical uncertainty unqualified"},
          "reversibility": "NONE", "authority_requirements": [],
          "verification_requirements": ["independent retained analytical/history/return-map/invariant checks"],
          "provenance_refs": refs,
          "notes": "Declarative SIMULATE morphism over an existing operation. Dissipated spring work does not establish damage or hardness. No inverse or cross-scale commutative witness.",
        }], sem,
    )
    # Zero plastic deformation/work in the elastic branch must retain finite
    # bounds: use maximum total compression and initial energy respectively.
    definitions = [
        ("impact.crush-compression-history.v1", "analytic_normalized", reference["maximum_compression_m"], "m",
         "maximum_absolute_sampled_compression_error", ["analytic.compression_m"]),
        ("impact.crush-velocity-history.v1", "analytic_normalized", request["model"]["initial_speed_m_per_s"], "m/s",
         "maximum_absolute_sampled_velocity_error", ["analytic.velocity_m_per_s"]),
        (PROPERTY_IDS["force_time"], "analytic_normalized", reference["peak_force_n"], "N",
         "maximum_absolute_sampled_force_error", ["analytic.force_n"]),
        ("impact.crush-plastic-compression-history.v1", "analytic_normalized", reference["maximum_compression_m"], "m",
         "maximum_absolute_sampled_plastic_compression_error", ["analytic.plastic_compression_m"]),
        ("impact.crush-plastic-work-history.v1", "analytic_normalized", reference["initial_energy_j"], "J",
         "maximum_absolute_sampled_plastic_work_error", ["analytic.plastic_work_j"]),
        (PROPERTY_IDS["impulse"], "impulse_relative", reference["support_impulse_n_s"], "N*s",
         "absolute_integrated_support_impulse_error", ["support_impulse"]),
        ("impact.crush-momentum-balance.v1", "momentum_relative", reference["support_impulse_n_s"], "N*s",
         "maximum_absolute_all_history_momentum_residual", ["all_history_momentum_balance"]),
        (PROPERTY_IDS["energy_accounting"], "energy_relative", reference["initial_energy_j"], "J",
         "maximum_absolute_kinetic_plus_elastic_plus_plastic_work_drift", ["maximum_energy_drift"]),
        (PROPERTY_IDS["plastic_work"], "analytic_normalized", reference["initial_energy_j"], "J",
         "absolute_final_plastic_work_error", ["plastic_work"]),
        ("impact.crush-rebound-energy-loss.v1", "energy_relative", reference["initial_energy_j"], "J",
         "absolute_rebound_energy_loss_vs_plastic_work_residual", ["rebound_energy_loss"]),
        (PROPERTY_IDS["residual_compression"], "analytic_normalized", reference["maximum_compression_m"], "m",
         "absolute_residual_plastic_compression_error", ["residual_compression"]),
        (PROPERTY_IDS["restitution"], "restitution_absolute", 1.0, "1",
         "absolute_restitution_error", ["restitution"]),
        (PROPERTY_IDS["separation_time"], "separation_relative", reference["contact_duration_s"], "s",
         "absolute_interpolated_separation_time_error", ["separation_event", "separation_time"]),
    ]
    effects = [_effect(identity, tolerances[tolerance] * normalization, unit, metric)
               for identity, tolerance, normalization, unit, metric, names in definitions]
    effects.append(_effect("impact.crush-timestep-refinement.v1", tolerances["refinement_normalized"], "1",
                           "maximum_declared_normalized_refinement_change"))
    for name in sorted(EXPANSION_OBSERVABLES):
        effects.append({"property_id": PROPERTY_IDS[name], "effect": "FORGET",
                        "output_property_id": None, "transform_id": None, "bound": None,
                        "notes": "Tracked physical query absent from the numerical schema; no richer physical state was simulated or physically reduced."})
    requirements = {
        "impact.crush-schema-integrity.v1": (["schema_integrity"], "EXACT_ALGEBRA"),
        "impact.crush-declared-contact-law.v1": ([label + "." + name for label in ("primary", "refined")
                                                 for name in ("force_law", "force_cap", "compression_only_force")], "NUMERICAL_BOUND"),
        "impact.crush-plastic-state-law.v1": ([label + "." + name for label in ("primary", "refined")
                                              for name in ("plastic_nonnegative", "plastic_monotonic", "return_mapping", "plastic_work_algebra", "yield_branch")], "NUMERICAL_BOUND"),
        "impact.crush-integrator-equations.v1": ([label + ".integrator_equations" for label in ("primary", "refined")], "NUMERICAL_BOUND"),
    }
    contract = contract_from_spec(registry, sem, {
        "contract_id": "impact.crush-contact-preservation.v1", "morphism_id": MORPHISM,
        "requires": list(requirements), "effects": effects,
        "notes": "Numerical sampled and aggregate thresholds for this retained run. FORGET records schema omission, not material, molecular or scale reduction.",
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
                "notes": "Exact retained report checks: " + ", ".join(names)}

    checks = [receipt("REQUIRE", identity, names, method)
              for identity, (names, method) in requirements.items()]
    checks.extend(receipt("BOUND", identity,
                          [label + "." + name for label in ("primary", "refined") for name in names],
                          "NUMERICAL_BOUND")
                  for identity, tolerance, normalization, unit, metric, names in definitions)
    refinement_names = ["refinement." + name for name in (
        "compression_m", "velocity_m_per_s", "force_n", "plastic_compression_m", "plastic_work_j",
        "support_impulse", "restitution", "peak_force", "maximum_compression", "residual_compression",
        "plastic_work", "separation_time")]
    checks.append(receipt("BOUND", "impact.crush-timestep-refinement.v1", refinement_names, "NUMERICAL_BOUND"))
    for name in sorted(EXPANSION_OBSERVABLES):
        checks.append({"kind": "FORGET", "property_id": PROPERTY_IDS[name],
                       "status": "VERIFIED", "method": "EXACT_ALGEBRA", "evidence_ref": result_ref,
                       "notes": "Exact schema omission only: result represents no " + name + "; this does not establish a physical reduction."})
    verification = verification_from_spec(registry, sem, contract, {
        "verification_id": "impact.crush-contact-preservation-verification.v1",
        "source_state_ref": request_ref, "candidate_state_ref": result_ref,
        "checks": checks,
        "notes": "Typed receipt of the retained independent numerical report. NUMERICAL_BOUND qualifies this synthetic model at sampled times and declared aggregates; no FORMAL_PROOF or experimental qualification.",
    })
    gate = admission_gate_from_spec(registry, sem, contract, verification, {
        "gate_id": "impact.crush-contact-preservation-gate.v1",
        "forbidden_forgets": sorted(PROPERTY_IDS[name] for name in request["desired_observables"]
                                    if name in EXPANSION_OBSERVABLES),
        "notes": "Eligibility only for this numerical loss policy. Unsupported requested physical observables are refused. No canonical state admission.",
    })
    return seal({"schema": SCHEMA, "request_digest": request_ref, "result_digest": result_ref,
                 "report_digest": report_ref, "registry": registry, "contract": contract,
                 "verification": verification, "admission_gate": gate, "claims": deepcopy(CLAIMS)})


def build(request: dict, result: dict, report: dict) -> dict:
    """Bind a structurally valid retained numerical report to existing typed APIs."""
    from .impact_crush_verification import validate_report
    request = validate_request(request)
    validate_report(request, result, report)
    return _assemble(request, result, report)


def validate(bundle: dict, request: dict, result: dict, report: dict) -> dict:
    """Validate retained structure and exact receipt bindings without replay."""
    from .impact_crush_verification import validate_report
    keys(bundle, {"schema", "record_digest", "request_digest", "result_digest", "report_digest",
                  "registry", "contract", "verification", "admission_gate", "claims"})
    check_seal(bundle)
    request = validate_request(request)
    validate_report(request, result, report)
    if (bundle["schema"] != SCHEMA or bundle["claims"] != CLAIMS
            or bundle["request_digest"] != digest(request)
            or bundle["result_digest"] != result["record_digest"]
            or bundle["report_digest"] != report["record_digest"]):
        raise ValueError("Crush preservation bundle scope or content binding differs")
    sem = _semantic()
    validate_registry(bundle["registry"], sem)
    validate_contract(bundle["contract"], bundle["registry"], sem)
    validate_verification(bundle["verification"], bundle["registry"], sem, bundle["contract"])
    validate_admission_gate(bundle["admission_gate"], bundle["registry"], sem,
                            bundle["contract"], bundle["verification"])
    if bundle != _assemble(request, result, report):
        raise ValueError("Crush preservation receipt differs from retained report obligations")
    return detached(bundle)
