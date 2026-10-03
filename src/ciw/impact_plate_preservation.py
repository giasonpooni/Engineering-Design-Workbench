"""Typed numerical receipts for the bounded elastic plate/contact workload.

The bridge consumes a retained independent report through NET's existing
representation, preservation, verification and eligibility APIs.  Its bounds
describe sampled finite-dimensional numerical acceptance.  Retained validation
does not propagate modes, run eigensolvers or replay a numerical provider.
"""
from __future__ import annotations

from copy import deepcopy

from .control_contracts import detached, keys
from .control_plane import CapabilityRegistry
from .impact_plate_contract import EXPANSION_OBSERVABLES, validate_request
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

SCHEMA = "ciw.impact-plate-preservation.v1"
SOURCE = "impact.plate-initial-reference.v1"
TARGET = "impact.plate-sampled-traces.v1"
MORPHISM = "impact.plate-contact-simulation.v1"
TRACE_LABELS = ("primary", "refined", "spatial")
PROPERTY_IDS = {
    "force_time": "impact.plate-patch-force-history.v1",
    "impulse": "impact.plate-striker-impulse.v1",
    "restitution": "impact.plate-striker-restitution.v1",
    "energy_accounting": "impact.plate-total-energy-accounting.v1",
    "separation_time": "impact.plate-first-separation-time.v1",
    "plate_deformation": "impact.plate-patch-deflection-history.v1",
    "plate_modes": "impact.plate-modal-state-history.v1",
    **{name: "impact.plate-" + name.replace("_", "-") + ".v1"
       for name in EXPANSION_OBSERVABLES},
}
CLAIMS = {
    "uses_existing_preservation_contracts": True,
    "synthetic_numerical_scope_only": True,
    "physical_validation_established": False,
    "continuum_convergence_established": False,
    "three_dimensional_solid_response_established": False,
    "local_contact_pressure_established": False,
    "total_striker_plate_momentum_conservation_established": False,
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
    # Declarative SIMULATE only; no provider or controller is added here.
    return SemanticRegistry(CapabilityRegistry())


def _representation(identity, role, schema_id, refs, scale, queries):
    return {
        "representation_id": identity, "role": role,
        "source_state_type": "synthetic_striker_simply_supported_isotropic_elastic_plate_patch_contact",
        "schema_id": schema_id,
        "quantity_semantics": "striker displacement and velocity, patch-average deflection and velocity, signed striker-minus-patch gap, compression-only spring force, sine-mode displacements and velocities, striker/contact/plate kinetic and bending energies",
        "unit_semantics": "SI: s, m, m/s, N, N*s, J; restitution and modal patch couplings dimensionless; uniform plate modulus Pa and contact stiffness N/m are distinct inputs",
        "frame_semantics": "fixed simply supported rectangular plate; striker and transverse plate deflection positive in the approach direction; one prescribed fixed rectangular patch",
        "time_semantics": "initial undeformed plate at first contact t=0; first release followed by separated flight and plate vibration; subsequent contact unsupported",
        "scale": scale,
        "uncertainty_semantics": "declared sampled numerical thresholds only; geometry and elastic constants are uncalibrated inputs; physical uncertainty unqualified",
        "equivalence_contract": "TASK_SPECIFIC",
        "preserved_queries": queries, "supported_interventions": [],
        "recovery_route": "retained strict geometry/material/loading request, primary/time-refined/spatial-refined traces and independent report",
        "provenance_refs": refs,
        "notes": "Primary and time-refined histories share one finite sine basis; the spatial history retains two additional modes per axis with the refined timestep. Fixed supports exchange plate momentum. No total plate-plus-striker momentum conservation, local pressure resolution, stress, strain, plasticity, fracture, rate, thermal, morphology or molecular state is represented. Nominal scales normalize numerical checks and do not establish physical scale preservation.",
    }


def _effect(identity, tolerance, unit, metric):
    return {
        "property_id": identity, "effect": "BOUND",
        "output_property_id": identity, "transform_id": None,
        "bound": {"metric": metric, "upper_bound": tolerance, "unit": unit,
                  "composition": "ADDITIVE_ABSOLUTE"},
        "notes": "Acceptance threshold for this exact retained finite-dimensional sampled run only; no continuous-time, continuum, three-dimensional, experimental or constitutive error bound.",
    }


def _report_notes(names):
    notes = "Exact retained report checks: " + ", ".join(names)
    if len(notes) > 1900:
        return ("Exact retained canonical report check-set digest " + digest(names)
                + "; " + str(len(names)) + " named checks. The retained report contains their full names and measurements.")
    return notes


def _assemble(request, result, report):
    """Assemble declarations from retained values and statuses without replay."""
    sem = _semantic()
    request_ref = digest(request)
    result_ref, report_ref = result["record_digest"], report["record_digest"]
    refs = [request_ref, result_ref, report_ref]
    scales, tolerances = report["reference"]["scales"], request["tolerances"]
    scale = {
        "length_m": scales["displacement_m"], "time_s": scales["time_s"],
        "energy_j": scales["energy_j"], "resolution": None,
        "label": "nominal point-mass/contact scales for the declared finite plate workload; not continuum or physical scale qualification",
    }
    queries = sorted(PROPERTY_IDS[name] for name in request["desired_observables"]
                     if name not in EXPANSION_OBSERVABLES)
    registry = registry_from_specs(
        [_representation(SOURCE, "MODEL", "ciw.impact-plate-request.v1", [request_ref, report_ref], scale, queries),
         _representation(TARGET, "SIGNAL", "ciw.impact-plate-result.v1", [result_ref, report_ref],
                         {**scale, "resolution": result["primary"]["dt_s"]}, queries)],
        [{"morphism_id": MORPHISM, "kind": "SIMULATE",
          "domain_representation_id": SOURCE, "codomain_representation_id": TARGET,
          "semantic_capability": None,
          "parameter_names": sorted(request["model"]) + sorted(request["integration"]),
          "preconditions": ["strict bounded SI geometry, uniform isotropic elastic constants, loading and integration request", "zero initial plate state, gravity and damping; fixed simply supported edges"],
          "validity": {
              "assumptions": ["linear Kirchhoff-Love rectangular plate", "uniform thickness and isotropic elasticity", "fixed simply supported edges", "finite sine-mode basis", "one finite rectangular uniform-pressure patch", "one point-mass striker and effective massless compression-only elastic spring", "work-conjugate patch displacement and modal force projection"],
              "operating_regime": ["the exact retained request", "recorded modal L1 deflection-to-thickness ratio and slope bound each at most 0.1", "first contact and separated flight with no recontact"],
              "failure_conditions": ["failed independent numerical or linear-regime checks", "unsupported subsequent contact", "requested richer material, contact, fracture or cross-scale response"],
          },
          "preservation": {"queries": queries, "interventions": [], "invariants": [], "approximation_tolerance": None},
          "loss": {"class": "TASK_SPECIFIC", "description": "finite sampled bending modes and one prescribed patch coordinate; richer physical observables explicitly absent", "metrics": {}},
          "uncertainty": {"behavior": "UNKNOWN", "method": "retained numerical thresholds only; physical input and model uncertainty unqualified"},
          "reversibility": "NONE", "authority_requirements": [],
          "verification_requirements": ["independent retained spectral/history/contact/energy checks for all three traces", "same-basis timestep comparison and enlarged-basis spatial comparison", "sampled small-deflection, slope and single-contact guards"],
          "provenance_refs": refs,
          "notes": "Declarative SIMULATE over the existing Session operation. Spatial truncation and time comparisons are numerical acceptance, not continuum convergence or a cross-scale commutative witness. Plate vibration energy is not material dissipation or toughness.",
        }], sem,
    )
    definitions = _definitions(scales, report["reference"]["state_normalizations"])
    effects = [_effect(identity, tolerances[tolerance] * normalization, unit, metric)
               for identity, tolerance, normalization, unit, metric, names in definitions]
    effects.extend([
        _effect(PROPERTY_IDS["plate_modes"], tolerances["analytic_normalized"], "1",
                "maximum_declared_normalized_sampled_modal_displacement_or_velocity_error"),
        _effect("impact.plate-timestep-refinement.v1", tolerances["refinement_normalized"], "1",
                "maximum_declared_normalized_same_basis_time_refinement_change"),
        _effect("impact.plate-spatial-refinement.v1", tolerances["spatial_refinement_normalized"], "1",
                "maximum_declared_normalized_enlarged_basis_spatial_refinement_change"),
        _effect("impact.plate-timestep-displacement-field.v1",
                tolerances["refinement_normalized"] * scales["displacement_m"], "m",
                "maximum_sampled_same_basis_l1_displacement_field_difference_bound"),
        _effect("impact.plate-spatial-displacement-field.v1",
                tolerances["spatial_refinement_normalized"] * scales["displacement_m"], "m",
                "maximum_sampled_common_modes_plus_added_tail_l1_displacement_field_difference_bound"),
    ])
    for name in sorted(EXPANSION_OBSERVABLES):
        effects.append({"property_id": PROPERTY_IDS[name], "effect": "FORGET", "output_property_id": None,
                        "transform_id": None, "bound": None,
                        "notes": "Tracked richer physical query absent from this numerical schema; no richer state was simulated or physically reduced."})
    requirements = {
        "impact.plate-schema-integrity.v1": (["schema_integrity"], "EXACT_ALGEBRA"),
        "impact.plate-declared-contact-law.v1": ([label + "." + name for label in TRACE_LABELS
                                                 for name in ("force_law", "compression_only_force", "gap_projection")], "NUMERICAL_BOUND"),
        "impact.plate-work-conjugate-projection.v1": ([label + "." + name for label in TRACE_LABELS
                                                     for name in ("patch_displacement_projection", "patch_velocity_projection")], "NUMERICAL_BOUND"),
        "impact.plate-integrator-equations.v1": ([label + ".integrator_equations" for label in TRACE_LABELS], "NUMERICAL_BOUND"),
        "impact.plate-recorded-linear-regime.v1": ([label + "." + name for label in TRACE_LABELS
                                                  for name in ("small_deflection_ratio", "small_slope_bound")], "NUMERICAL_BOUND"),
        "impact.plate-first-release-single-contact.v1": ([label + "." + name for label in TRACE_LABELS
                                                       for name in ("separation_event", "single_contact")], "NUMERICAL_BOUND"),
        "impact.plate-independent-report-acceptance.v1": ([row["name"] for row in report["checks"]
                                                          if row["name"] != "schema_integrity"], "NUMERICAL_BOUND"),
    }
    contract = contract_from_spec(registry, sem, {
        "contract_id": "impact.plate-contact-preservation.v1", "morphism_id": MORPHISM,
        "requires": list(requirements), "effects": effects,
        "notes": "Numerical sampled and aggregate acceptance for this exact retained model and recorded domain. FORGET describes schema omission, not a material or scale reduction.",
    })
    checks_by_name = {row["name"]: row for row in report["checks"]}

    def receipt(kind, identity, names, method):
        rows = [checks_by_name.get(name) for name in names]
        status = ("REFUTED" if any(row is not None and row["status"] == "FAIL" for row in rows)
                  else "VERIFIED" if rows and all(row is not None and row["status"] == "PASS" for row in rows)
                  else "UNRESOLVED")
        return {"kind": kind, "property_id": identity, "status": status,
                "method": method if status != "UNRESOLVED" else "NOT_PERFORMED",
                "evidence_ref": report_ref, "notes": _report_notes(names)}

    checks = [receipt("REQUIRE", identity, names, method)
              for identity, (names, method) in requirements.items()]
    checks.extend(receipt("BOUND", identity,
                          [label + "." + name for label in TRACE_LABELS for name in names], "NUMERICAL_BOUND")
                  for identity, tolerance, normalization, unit, metric, names in definitions)
    checks.append(receipt("BOUND", PROPERTY_IDS["plate_modes"],
                          [label + ".analytic." + name for label in TRACE_LABELS
                           for name in ("modal_displacement_m", "modal_velocity_m_per_s")], "NUMERICAL_BOUND"))
    for prefix, identity in (("time_refinement.", "impact.plate-timestep-refinement.v1"),
                             ("spatial_refinement.", "impact.plate-spatial-refinement.v1")):
        checks.append(receipt("BOUND", identity,
                              [row["name"] for row in report["checks"] if row["name"].startswith(prefix)], "NUMERICAL_BOUND"))
    for name, identity in (("time_refinement", "impact.plate-timestep-displacement-field.v1"),
                           ("spatial_refinement", "impact.plate-spatial-displacement-field.v1")):
        checks.append(receipt("BOUND", identity, [name + ".displacement_field_bound"], "NUMERICAL_BOUND"))
    for name in sorted(EXPANSION_OBSERVABLES):
        checks.append({"kind": "FORGET", "property_id": PROPERTY_IDS[name], "status": "VERIFIED",
                       "method": "EXACT_ALGEBRA", "evidence_ref": result_ref,
                       "notes": "Exact schema omission only: result represents no " + name + "; this does not establish a physical reduction."})
    verification = verification_from_spec(registry, sem, contract, {
        "verification_id": "impact.plate-contact-preservation-verification.v1",
        "source_state_ref": request_ref, "candidate_state_ref": result_ref, "checks": checks,
        "notes": "Typed receipt of the retained independent report. NUMERICAL_BOUND supplies sampled finite-model acceptance; no FORMAL_PROOF, continuous-time/continuum guarantee or experimental qualification.",
    })
    gate = admission_gate_from_spec(registry, sem, contract, verification, {
        "gate_id": "impact.plate-contact-preservation-gate.v1",
        "forbidden_forgets": sorted(PROPERTY_IDS[name] for name in request["desired_observables"]
                                    if name in EXPANSION_OBSERVABLES),
        "notes": "Numerical loss-policy eligibility only. Unsupported requested physical quantities are refused. No canonical state admission.",
    })
    return seal({"schema": SCHEMA, "request_digest": request_ref, "result_digest": result_ref,
                 "report_digest": report_ref, "registry": registry, "contract": contract,
                 "verification": verification, "admission_gate": gate, "claims": deepcopy(CLAIMS)})


def _definitions(scales, state_normalizations):
    # Names and thresholds follow the fixed installed plate verifier.
    # Displacements, striker velocity and force use nominal contact scales.
    # Modal/patch velocities use basis-dependent energy-derived scales.  A
    # common SI effect conservatively takes the largest declared per-basis
    # denominator; each receipt still requires every per-trace error check.
    def state_scale(field):
        return max(state_normalizations[label][field] for label in ("primary", "spatial"))

    return [
        ("impact.plate-striker-displacement-history.v1", "analytic_normalized", state_scale("striker_displacement_m"), "m",
         "maximum_absolute_sampled_striker_displacement_error", ["analytic.striker_displacement_m"]),
        ("impact.plate-striker-velocity-history.v1", "analytic_normalized", state_scale("velocity_m_per_s"), "m/s",
         "maximum_absolute_sampled_striker_velocity_error", ["analytic.velocity_m_per_s"]),
        ("impact.plate-compression-history.v1", "analytic_normalized", state_scale("compression_m"), "m",
         "maximum_absolute_sampled_contact_spring_compression_error", ["analytic.compression_m"]),
        (PROPERTY_IDS["force_time"], "analytic_normalized", state_scale("force_n"), "N",
         "maximum_absolute_sampled_patch_force_error", ["analytic.force_n"]),
        (PROPERTY_IDS["plate_deformation"], "analytic_normalized", state_scale("plate_contact_displacement_m"), "m",
         "maximum_absolute_sampled_patch_average_deflection_error", ["analytic.plate_contact_displacement_m"]),
        ("impact.plate-patch-velocity-history.v1", "analytic_normalized", state_scale("plate_contact_velocity_m_per_s"), "m/s",
         "maximum_absolute_sampled_patch_average_velocity_error", ["analytic.plate_contact_velocity_m_per_s"]),
        ("impact.plate-modal-displacement-history.v1", "analytic_normalized", state_scale("modal_displacement_m"), "m",
         "maximum_absolute_sampled_modal_displacement_error", ["analytic.modal_displacement_m"]),
        ("impact.plate-modal-velocity-history.v1", "analytic_normalized", state_scale("modal_velocity_m_per_s"), "m/s",
         "maximum_absolute_sampled_modal_velocity_error", ["analytic.modal_velocity_m_per_s"]),
        (PROPERTY_IDS["impulse"], "impulse_relative", scales["impulse_n_s"], "N*s",
         "absolute_integrated_striker_impulse_error", ["striker_impulse"]),
        ("impact.plate-striker-momentum-balance.v1", "momentum_relative", scales["impulse_n_s"], "N*s",
         "maximum_absolute_striker_momentum_residual", ["all_history_striker_momentum_balance"]),
        (PROPERTY_IDS["energy_accounting"], "energy_relative", scales["energy_j"], "J",
         "maximum_absolute_striker_contact_plate_kinetic_plus_bending_energy_drift", ["maximum_energy_drift"]),
        (PROPERTY_IDS["restitution"], "restitution_absolute", 1.0, "1",
         "absolute_striker_restitution_error", ["restitution"]),
        (PROPERTY_IDS["separation_time"], "separation_relative", scales["time_s"], "s",
         "absolute_interpolated_first_release_time_error", ["separation_event", "separation_time"]),
    ]


def build(request: dict, result: dict, report: dict) -> dict:
    """Bind a structurally valid retained report through the existing typed APIs."""
    from .impact_plate_verification import validate_report
    request = validate_request(request)
    validate_report(request, result, report)
    return _assemble(request, result, report)


def validate(bundle: dict, request: dict, result: dict, report: dict) -> dict:
    """Validate retained exact receipts without solving or repeating the audit."""
    from .impact_plate_verification import validate_report
    keys(bundle, {"schema", "record_digest", "request_digest", "result_digest", "report_digest",
                  "registry", "contract", "verification", "admission_gate", "claims"})
    check_seal(bundle)
    request = validate_request(request)
    validate_report(request, result, report)
    if (bundle["schema"] != SCHEMA or bundle["claims"] != CLAIMS
            or bundle["request_digest"] != digest(request)
            or bundle["result_digest"] != result["record_digest"]
            or bundle["report_digest"] != report["record_digest"]):
        raise ValueError("Plate preservation bundle scope or content binding differs")
    sem = _semantic()
    validate_registry(bundle["registry"], sem)
    validate_contract(bundle["contract"], bundle["registry"], sem)
    validate_verification(bundle["verification"], bundle["registry"], sem, bundle["contract"])
    validate_admission_gate(bundle["admission_gate"], bundle["registry"], sem,
                            bundle["contract"], bundle["verification"])
    if bundle != _assemble(request, result, report):
        raise ValueError("Plate preservation receipt differs from retained report obligations")
    return detached(bundle)
