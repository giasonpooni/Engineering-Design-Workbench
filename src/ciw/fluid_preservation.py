"""Typed finite-trajectory receipts with explicit fluid scale and coupling losses.

These receipts bind the retained numerical report on existing preservation APIs.
They do not assert a molecular-to-continuum arrow, resolve discarded spatial or
vertical physics, establish receiver qualification, or admit canonical state.
"""
from __future__ import annotations

from copy import deepcopy

from . import fluid_contract as domain
from .control_contracts import detached, keys
from .control_plane import CapabilityRegistry
from .operations.runner import check_seal, digest, seal
from .preservation_contracts import (admission_gate_from_spec, contract_from_spec,
    validate_admission_gate, validate_contract, validate_verification, verification_from_spec)
from .representation_morphisms import registry_from_specs, validate_registry
from .semantic_capabilities import SemanticRegistry

SCHEMA = "ciw.fluid-preservation.v1"
OMISSIONS = {"molecular_identity", "molecular_transport_parameters", "resolved_vertical_velocity",
             "three_dimensional_flow", "general_material_constitutive_response",
             "general_receiver_coupling", "experimental_model_uncertainty"}
CLAIMS = {"uses_existing_preservation_contracts": True, "finite_retained_trajectory_only": True,
          "synthetic_numerical_scope_only": True, "physical_validation_established": False,
          "molecular_preservation_established": False, "cross_scale_commutative_witness_supplied": False,
          "resolved_vertical_flow_established": False, "general_receiver_coupling_established": False,
          "canonical_state_mutated": False, "state_admission_performed": False, "execution_authority": False}


def _semantic():
    return SemanticRegistry(CapabilityRegistry())


def _property(profile, name):
    return "fluid." + profile + "." + name.replace("_", "-") + ".v1"


def _scope(profile, request):
    if profile in domain.EXTENDED_PROFILES:
        return domain.module(profile).preservation_scope(request)
    if profile == "reservoir":
        return {"representation": "lumped linear incompressible continuum perturbation",
                "particle_meaning": "none", "spatial_detail": "two reservoir heads and one connector flow; no spatial velocity field",
                "vertical_detail": "hydrostatic head only; vertical velocity and vertical structure absent",
                "clock": "provider-owned elapsed synthetic model time; synchronous midpoint coupling",
                "receiver_coupling": ("one preloaded linear lumped piston; traction and equal opposite interface work at the same midpoint"
                                      if request["structure"]["enabled"] else "rigid boundary; piston motion and interface work absent"),
                "physical_validity": "passive unforced small-head and bounded-travel perturbation; input energy bounds guard the continuous domain",
                "molecular_scope": "not represented; no molecular reduction or preservation witness"}
    return {"representation": "one-dimensional uniform-depth linear shallow-water surface gravity wave",
            "particle_meaning": "none", "spatial_detail": "periodic staggered horizontal cells and faces; finite spatial grid",
            "vertical_detail": "depth-averaged horizontal velocity and hydrostatic bottom pressure; resolved vertical velocity absent",
            "clock": "provider-owned elapsed synthetic model time; fixed synchronous finite-volume steps",
            "receiver_coupling": "none; rigid uniform bed and periodic boundaries; structural response is unqualified",
            "physical_validity": "small amplitude and long wavelength; acoustic pressure waves, breaking and wetting are unrepresented",
            "molecular_scope": "not represented; no molecular reduction or preservation witness"}


def _representation(identity, role, schema, refs, profile, scope, scale, queries):
    descriptions = {
        "molecular": ("declared classical force-shifted LJ sites and finite position, velocity, force, energy, momentum and toy thermodynamic traces", "Reduced Lennard-Jones units with m=sigma=epsilon=k_B=1; optional SI scales remain explicit unvalidated declarations"),
        "sph": ("declared one-dimensional SPH computational fluid parcels and finite trajectories, density, pressure, energy and momentum", "SI metres, seconds, kilograms, pascals and joules; each parcel represents continuum fluid mass"),
        "fsi": ("declared linear shallow-water channel and moving wall; finite surface, velocity, boundary traction, wall displacement and interface work", "SI metres, seconds, kilograms, pascals, newtons and joules; pressure perturbation about a preloaded equilibrium"),
    }
    quantity, units = descriptions.get(profile, (None, None))
    return {"representation_id": identity, "role": role, "source_state_type": scope["representation"],
            "schema_id": schema,
            "quantity_semantics": quantity or ("declared synthetic continuum inputs and finite SI time traces of reservoir transfer, head, pressure, connector velocity, piston motion and energy"
                                   if profile == "reservoir" else "declared synthetic shallow-water inputs and finite SI time/space traces of surface elevation, depth-averaged velocity, volume flux, hydrostatic pressure and energy"),
            "unit_semantics": units or "SI metres, seconds, cubic metres, kilograms, pascals, newtons and joules; no implicit conversion",
            "frame_semantics": scope["spatial_detail"], "time_semantics": scope["clock"], "scale": scale,
            "uncertainty_semantics": "declared numerical residual thresholds only; experimental and physical model uncertainty unqualified",
            "equivalence_contract": "TASK_SPECIFIC", "preserved_queries": queries, "supported_interventions": [],
            "recovery_route": "exact retained request, finite trajectories and independent numerical report",
            "provenance_refs": refs,
            "notes": scope["vertical_detail"] + ". " + scope["receiver_coupling"] + ". " + scope["molecular_scope"] + "."}


def _assemble(request, result, report):
    profile = domain.profile_for_request(request)
    contract = domain.module(profile)
    prefix = "fluid." + profile
    source, target, morphism = prefix + ".declared-model.v1", prefix + ".finite-trajectory.v1", prefix + ".simulation.v1"
    request_ref, result_ref, report_ref = digest(request), result["record_digest"], report["record_digest"]
    refs = [request_ref, result_ref, report_ref]
    scope = _scope(profile, request)
    scale = {"length_m": (contract.length_scale_m(request) if profile in domain.EXTENDED_PROFILES else
                           request["connector"]["length_m"] if profile == "reservoir" else request["model"]["length_m"]),
             "time_s": (contract.time_scale_s(request) if profile in domain.EXTENDED_PROFILES else
                         request["clock"]["duration_s"] if profile == "reservoir" else request["integration"]["duration_s"]),
             "energy_j": None, "resolution": None,
             "label": ("declared bounded model domain; source representation and unit conversion explicit; cross-scale maps qualified separately"
                       if profile in domain.EXTENDED_PROFILES else "declared continuum model domain only; no molecular or cross-scale qualification")}
    queries = [_property(profile, "numerical_" + row["name"]) for row in report["checks"]]
    sem = _semantic()
    registry = registry_from_specs(
        [_representation(source, "MODEL", contract.REQUEST_SCHEMA, [request_ref, report_ref], profile, scope, scale, queries),
         _representation(target, "SIGNAL", contract.RESULT_SCHEMA, [result_ref, report_ref], profile, scope, scale, queries)],
        [{"morphism_id": morphism, "kind": "SIMULATE", "domain_representation_id": source,
          "codomain_representation_id": target, "semantic_capability": None,
          "parameter_names": sorted(request),
          "preconditions": ["exact bounded synthetic declaration in explicit units" if profile in domain.EXTENDED_PROFILES else "exact bounded synthetic SI declaration", "fixed model-owned clock and hard physical domain bounds"],
          "validity": {"assumptions": [scope["representation"], scope["vertical_detail"], scope["receiver_coupling"]],
                       "operating_regime": [scope["physical_validity"], "exact finite retained time and spatial grids"],
                       "failure_conditions": ["failed independent numerical acceptance", "requested unrepresented scales or physical observables"]},
          "preservation": {"queries": queries, "interventions": [], "invariants": [], "approximation_tolerance": None},
          "loss": {"class": "TASK_SPECIFIC", "description": scope["vertical_detail"], "metrics": {}},
          "uncertainty": {"behavior": "UNKNOWN", "method": "numerical acceptance thresholds only; physical uncertainty unqualified"},
          "reversibility": "NONE", "authority_requirements": [],
          "verification_requirements": ["independent reference and conservation checks", "declared refinement checks", "LOCAL qualification and every check PASS"],
          "provenance_refs": refs,
          "notes": ("Session owns operation occurrences. This fixed synthetic provider retains explicitly declared atomistic, parcel or continuum trajectories; absent richer physics is not a proved physical reduction."
                    if profile in domain.EXTENDED_PROFILES else "Session owns operation occurrences. This fixed synthetic provider retains finite trajectories; omitted molecular and richer continuum state was never acquired or reduced.")}], sem)
    effects = [{"property_id": _property(profile, "numerical_" + row["name"]), "effect": "BOUND",
                "output_property_id": _property(profile, "numerical_" + row["name"]), "transform_id": None,
                "bound": {"metric": "retained_report_" + row["name"], "upper_bound": row["tolerance"],
                          "unit": "1", "composition": "ADDITIVE_ABSOLUTE"},
                "notes": "Named retained numerical report threshold only; no receiver-model or experimental error bound."}
               for row in report["checks"]]
    absent = OMISSIONS
    if profile == "molecular":
        absent = (OMISSIONS - {"molecular_identity"}) | {"chemical_molecular_identity", "bonded_molecular_structure"}
    omissions = sorted(absent | contract.EXPANSION_OBSERVABLES | getattr(contract, "REFUSED_OBSERVABLES", set()))
    effects += [{"property_id": _property(profile, name), "effect": "FORGET", "output_property_id": None,
                 "transform_id": None, "bound": None,
                 "notes": "Explicit schema absence; no physical reduction, molecular mapping or receiver verification is claimed."}
                for name in omissions]
    independent, local = prefix + ".independent-report-acceptance.v1", prefix + ".local-qualification.v1"
    preserved_contract = contract_from_spec(registry, sem,
        {"contract_id": prefix + ".trajectory-preservation.v1", "morphism_id": morphism,
         "requires": [independent, local], "effects": effects,
         "notes": "The exact independent retained report qualifies finite synthetic numerics only; omissions are explicit and canonical state admission is separate."})
    passed = report["status"] == "PASS" and all(row["status"] == "PASS" for row in report["checks"])
    eligible = passed and report["qualification"]["action"] == "LOCAL"
    checks = [{"kind": "REQUIRE", "property_id": independent, "status": "VERIFIED" if passed else "REFUTED",
               "method": "NUMERICAL_BOUND", "evidence_ref": report_ref, "notes": "Every exact retained independent check must PASS."},
              {"kind": "REQUIRE", "property_id": local, "status": "VERIFIED" if eligible else "REFUTED",
               "method": "EXACT_ALGEBRA", "evidence_ref": report_ref, "notes": "Require LOCAL qualification and all numerical checks PASS."}]
    checks += [{"kind": "BOUND", "property_id": _property(profile, "numerical_" + row["name"]),
                "status": "VERIFIED" if row["status"] == "PASS" else "REFUTED", "method": "NUMERICAL_BOUND",
                "evidence_ref": report_ref, "notes": "Exact retained numerical check " + row["name"]}
               for row in report["checks"]]
    checks += [{"kind": "FORGET", "property_id": _property(profile, name), "status": "VERIFIED", "method": "EXACT_ALGEBRA",
                "evidence_ref": result_ref, "notes": "Declared schema absence of " + name + "; not a proved physical reduction."}
               for name in omissions]
    verification = verification_from_spec(registry, sem, preserved_contract,
        {"verification_id": prefix + ".trajectory-preservation-verification.v1", "source_state_ref": request_ref,
         "candidate_state_ref": result_ref, "checks": checks,
         "notes": "Static typed receipt of independent numerical report; no molecular, experimental or general receiver proof."})
    gate = admission_gate_from_spec(registry, sem, preserved_contract, verification,
        {"gate_id": prefix + ".trajectory-preservation-gate.v1",
         "forbidden_forgets": sorted(_property(profile, name) for name in request["desired_observables"] if name in omissions),
         "notes": "Numerical eligibility only. LOCAL and all checks PASS under the loss policy are required. No state admission performed."})
    claims = deepcopy(CLAIMS)
    if profile in domain.EXTENDED_PROFILES:
        claims["represented_particle_semantics"] = scope["particle_meaning"]
        claims["cross_scale_constitutive_closure_established"] = False
    return seal({"schema": SCHEMA, "profile": profile, "request_digest": request_ref, "result_digest": result_ref,
                 "report_digest": report_ref, "model_scope": scope, "registry": registry, "contract": preserved_contract,
                 "verification": verification, "admission_gate": gate, "claims": claims})


def build(request: dict, result: dict, report: dict) -> dict:
    request = domain.validate_request(request)
    domain.validate_report(request, result, report)
    return _assemble(request, result, report)


def validate(bundle: dict, request: dict, result: dict, report: dict) -> dict:
    keys(bundle, {"schema", "profile", "record_digest", "request_digest", "result_digest", "report_digest",
                  "model_scope", "registry", "contract", "verification", "admission_gate", "claims"})
    check_seal(bundle)
    request = domain.validate_request(request)
    domain.validate_report(request, result, report)
    if digest(bundle) != digest(_assemble(request, result, report)):
        raise ValueError("Fluid preservation differs from exact finite-report scope or obligations")
    sem = _semantic()
    validate_registry(bundle["registry"], sem)
    validate_contract(bundle["contract"], bundle["registry"], sem)
    validate_verification(bundle["verification"], bundle["registry"], sem, bundle["contract"])
    validate_admission_gate(bundle["admission_gate"], bundle["registry"], sem, bundle["contract"], bundle["verification"])
    return detached(bundle)
