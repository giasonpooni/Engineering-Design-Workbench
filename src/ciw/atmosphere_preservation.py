"""Typed finite-profile receipts for a declared dry hydrostatic column.

The existing representation, preservation, verification and admission-gate
APIs bind a retained numerical report. Inspection never recompiles a column,
integrates a hydrostatic law, invokes a provider or admits canonical state.
"""
from __future__ import annotations

from copy import deepcopy

from .atmosphere_contract import EXPANSION_OBSERVABLES, validate_request
from .control_contracts import detached, keys
from .control_plane import CapabilityRegistry
from .operations.runner import check_seal, digest, seal
from .preservation_contracts import (
    admission_gate_from_spec, contract_from_spec, validate_admission_gate,
    validate_contract, validate_verification, verification_from_spec,
)
from .representation_morphisms import registry_from_specs, validate_registry
from .semantic_capabilities import SemanticRegistry

SCHEMA = "ciw.atmosphere-preservation.v1"
SOURCE = "atmosphere.declared-column.v1"
TARGET = "atmosphere.sampled-column.v1"
MORPHISM = "atmosphere.column-compilation.v1"
PROPERTY_IDS = {
    name: "atmosphere." + name.replace("_", "-") + ".v1"
    for name in {
        "temperature", "pressure", "density", "sound_speed", "viscosity", "wind",
        "potential_temperature", "hydrostatic_profile", *EXPANSION_OBSERVABLES,
    }
}
EXTRA_OMISSIONS = (
    "continuous_height_profile", "horizontal_structure", "time_evolution",
    "aerodynamic_forces", "material_temperature", "optical_composition",
)
CLAIMS = {
    "uses_existing_preservation_contracts": True,
    "synthetic_numerical_scope_only": True,
    "finite_retained_profile_only": True,
    "physical_validation_established": False,
    "standard_atmosphere_certification_established": False,
    "weather_forecast_established": False,
    "wind_dynamics_established": False,
    "material_conditioning_established": False,
    "visual_scattering_established": False,
    "cross_scale_commutative_witness_supplied": False,
    "canonical_state_mutated": False,
    "state_admission_performed": False,
    "execution_authority": False,
}
DEFINITIONS = (
    ("temperature", "prescribed_temperature"),
    ("pressure", "cumulative_pressure_profile"),
    ("density", "equation_of_state"),
    ("sound_speed", "sound_speed"),
    ("dynamic_viscosity", "dynamic_viscosity"),
    ("kinematic_viscosity", "kinematic_viscosity"),
    ("potential_temperature", "potential_temperature"),
    ("wind", "prescribed_wind"),
    ("hydrostatic_profile", "segment_hydrostatic_balance"),
    ("quadrature_refinement", "quadrature_refinement"),
)


def _semantic() -> SemanticRegistry:
    return SemanticRegistry(CapabilityRegistry())


def _property(name: str) -> str:
    return PROPERTY_IDS.get(name, "atmosphere." + name.replace("_", "-") + ".v1")


def _representation(identity, role, schema_id, refs, scale, queries):
    return {
        "representation_id": identity, "role": role,
        "source_state_type": "prescribed_dry_hydrostatic_constant_gravity_column",
        "schema_id": schema_id,
        "quantity_semantics": "temperature, pressure, dry density, sound speed, dynamic and kinematic viscosity, potential temperature and prescribed ENU wind at declared relative heights",
        "unit_semantics": "SI: height m; temperature K; pressure Pa; density kg/m^3; sound and wind m/s; dynamic viscosity Pa*s; kinematic viscosity m^2/s",
        "frame_semantics": "declared local ENU frame; heights above a separately retained reference-height origin; source context is a declaration",
        "time_semantics": "one declared static column; optional context time does not establish measured weather or atmospheric evolution",
        "scale": scale,
        "uncertainty_semantics": "retained normalized numerical acceptance thresholds only; source, input and physical-model uncertainty unqualified",
        "equivalence_contract": "TASK_SPECIFIC", "preserved_queries": queries,
        "supported_interventions": [],
        "recovery_route": "retained strict atmosphere request, exact ordered height samples and independent numerical report",
        "provenance_refs": refs,
        "notes": "Temperature lapse and constant wind are prescribed, not inferred. The compiler represents a dry ideal-gas hydrostatic column at constant gravity. Height origin is metadata, not a gravity or geodesy model. Omitted moisture, clouds, turbulence, chemistry, optical state and material conditioning are explicit losses. Numerical acceptance does not establish experimental or weather validity.",
    }


def _status(rows):
    if any(row is not None and row["status"] == "FAIL" for row in rows):
        return "REFUTED"
    if rows and all(row is not None and row["status"] == "PASS" for row in rows):
        return "VERIFIED"
    return "UNRESOLVED"


def _assemble(request, result, report):
    sem = _semantic()
    request_ref = digest(request)
    result_ref, report_ref = result["record_digest"], report["record_digest"]
    refs = [request_ref, result_ref, report_ref]
    scale = {"length_m": request["sampling"]["height_m"][-1], "time_s": None,
             "energy_j": None, "resolution": None,
             "label": "declared sampled column height; no continuum or physical-scale qualification"}
    queries = sorted(_property(name) for name in request["desired_observables"]
                     if name not in EXPANSION_OBSERVABLES)
    registry = registry_from_specs(
        [_representation(SOURCE, "MODEL", "ciw.atmosphere-request.v1", [request_ref, report_ref], scale, queries),
         _representation(TARGET, "SIGNAL", "ciw.atmosphere-result.v1", [result_ref, report_ref], scale, queries)],
        [{"morphism_id": MORPHISM, "kind": "SIMULATE",
          "domain_representation_id": SOURCE, "codomain_representation_id": TARGET,
          "semantic_capability": None,
          "parameter_names": sorted("reference." + name for name in request["reference"])
                             + sorted("profile." + name for name in request["profile"])
                             + ["sampling.height_m"],
          "preconditions": ["strict bounded SI dry-column declaration", "ordered height grid starts at the retained reference"],
          "validity": {
              "assumptions": ["dry ideal gas", "constant gravity", "prescribed linear temperature lapse", "fixed thermodynamic and Sutherland coefficients", "prescribed constant ENU wind"],
              "operating_regime": ["exact retained request and sampled height grid", "bounded temperature and subadiabatic declared lapse"],
              "failure_conditions": ["failed independent numerical or declared-domain checks", "requested unrepresented moist, dynamic, optical or material response"],
          },
          "preservation": {"queries": queries, "interventions": [], "invariants": [], "approximation_tolerance": None},
          "loss": {"class": "TASK_SPECIFIC", "description": "finite static dry-column samples with prescribed wind; richer physical observables absent", "metrics": {}},
          "uncertainty": {"behavior": "UNKNOWN", "method": "numerical thresholds only; input and physical-model uncertainty unqualified"},
          "reversibility": "NONE", "authority_requirements": [],
          "verification_requirements": ["independent retained constitutive and hydrostatic checks", "independent segment quadrature and refinement acceptance", "all report checks PASS and LOCAL qualification"],
          "provenance_refs": refs,
          "notes": "Declarative SIMULATE for the fixed installed atmospheric compiler. The existing Session owns execution. A finite profile and independent quadrature comparison supply numerical acceptance only; no weather forecast, experimental qualification, provider activation or cross-scale witness.",
        }], sem,
    )
    checks_by_name = {row["name"]: row for row in report["checks"]}
    effects = [{
        "property_id": _property(name), "effect": "BOUND", "output_property_id": _property(name),
        "transform_id": None,
        "bound": {"metric": "maximum_declared_normalized_" + check_name + "_residual",
                  "upper_bound": checks_by_name[check_name]["tolerance"],
                  "unit": "1", "composition": "ADDITIVE_ABSOLUTE"},
        "notes": "Numerical threshold for the exact retained finite profile and named report residual; no experimental, continuous-profile or receiver-model error bound.",
    } for name, check_name in DEFINITIONS]
    # The public viscosity query requires both independent SI property checks.
    effects.append({
        "property_id": _property("viscosity"), "effect": "BOUND", "output_property_id": _property("viscosity"),
        "transform_id": None,
        "bound": {"metric": "maximum_declared_normalized_dynamic_or_kinematic_viscosity_residual",
                  "upper_bound": max(checks_by_name[name]["tolerance"] for name in ("dynamic_viscosity", "kinematic_viscosity")),
                  "unit": "1", "composition": "ADDITIVE_ABSOLUTE"},
        "notes": "Both dynamic and kinematic viscosity checks must pass their own retained thresholds; this aggregate dimensionless bound uses their larger threshold.",
    })
    omissions = sorted(EXPANSION_OBSERVABLES | set(EXTRA_OMISSIONS))
    effects.extend({"property_id": _property(name), "effect": "FORGET", "output_property_id": None,
                    "transform_id": None, "bound": None,
                    "notes": "Explicit absence from this fixed finite dry-column schema; no richer physical state was reduced or validated."}
                   for name in omissions)
    requirements = {
        "atmosphere.independent-report-acceptance.v1": [row["name"] for row in report["checks"]],
        "atmosphere.local-qualification.v1": [],
    }
    contract = contract_from_spec(registry, sem, {
        "contract_id": "atmosphere.column-preservation.v1", "morphism_id": MORPHISM,
        "requires": list(requirements), "effects": effects,
        "notes": "All retained independent checks are required. LOCAL numerical eligibility is distinct from physical qualification and canonical admission. FORGET denotes schema omission, not a proved physical reduction.",
    })

    def receipt(kind, identity, names):
        status = _status([checks_by_name.get(name) for name in names])
        return {"kind": kind, "property_id": identity, "status": status,
                "method": "NUMERICAL_BOUND" if status != "UNRESOLVED" else "NOT_PERFORMED",
                "evidence_ref": report_ref, "notes": "Exact retained report checks: " + ", ".join(names)}

    checks = [receipt("REQUIRE", "atmosphere.independent-report-acceptance.v1",
                      requirements["atmosphere.independent-report-acceptance.v1"])]
    local = (report["qualification"]["action"] == "LOCAL" and report["status"] == "PASS"
             and all(row["status"] == "PASS" for row in report["checks"]))
    checks.append({"kind": "REQUIRE", "property_id": "atmosphere.local-qualification.v1",
                   "status": "VERIFIED" if local else "REFUTED", "method": "EXACT_ALGEBRA",
                   "evidence_ref": report_ref,
                   "notes": "Exact retained qualification must be LOCAL, report status PASS, and every report check PASS; this is numerical eligibility only."})
    checks.extend(receipt("BOUND", _property(name), [check_name]) for name, check_name in DEFINITIONS)
    checks.append(receipt("BOUND", _property("viscosity"), ["dynamic_viscosity", "kinematic_viscosity"]))
    checks.extend({"kind": "FORGET", "property_id": _property(name), "status": "VERIFIED",
                   "method": "EXACT_ALGEBRA", "evidence_ref": result_ref,
                   "notes": "Exact schema omission: no " + name + " is represented or physically qualified."}
                  for name in omissions)
    verification = verification_from_spec(registry, sem, contract, {
        "verification_id": "atmosphere.column-preservation-verification.v1",
        "source_state_ref": request_ref, "candidate_state_ref": result_ref, "checks": checks,
        "notes": "Typed receipt of the exact retained numerical report. No FORMAL_PROOF, continuous-profile guarantee, measured weather qualification or receiver validation.",
    })
    gate = admission_gate_from_spec(registry, sem, contract, verification, {
        "gate_id": "atmosphere.column-preservation-gate.v1",
        "forbidden_forgets": sorted(_property(name) for name in request["desired_observables"]
                                    if name in EXPANSION_OBSERVABLES),
        "notes": "Numerical eligibility requires LOCAL and all checks PASS under the explicit loss policy. No physical or canonical-state admission.",
    })
    return seal({"schema": SCHEMA, "request_digest": request_ref, "result_digest": result_ref,
                 "report_digest": report_ref, "registry": registry, "contract": contract,
                 "verification": verification, "admission_gate": gate, "claims": deepcopy(CLAIMS)})


def build(request: dict, result: dict, report: dict) -> dict:
    """Build typed receipts from strict retained artifacts without numerical replay."""
    from .atmosphere_verification import validate_report
    request = validate_request(request)
    validate_report(request, result, report)
    return _assemble(request, result, report)


def validate(bundle: dict, request: dict, result: dict, report: dict) -> dict:
    """Validate exact static obligations using the existing preservation APIs."""
    from .atmosphere_verification import validate_report
    keys(bundle, {"schema", "record_digest", "request_digest", "result_digest", "report_digest",
                  "registry", "contract", "verification", "admission_gate", "claims"})
    check_seal(bundle)
    request = validate_request(request)
    validate_report(request, result, report)
    if (bundle["schema"] != SCHEMA or bundle["claims"] != CLAIMS
            or bundle["request_digest"] != digest(request)
            or bundle["result_digest"] != result["record_digest"]
            or bundle["report_digest"] != report["record_digest"]):
        raise ValueError("Atmosphere preservation scope or content binding differs")
    sem = _semantic()
    validate_registry(bundle["registry"], sem)
    validate_contract(bundle["contract"], bundle["registry"], sem)
    validate_verification(bundle["verification"], bundle["registry"], sem, bundle["contract"])
    validate_admission_gate(bundle["admission_gate"], bundle["registry"], sem,
                            bundle["contract"], bundle["verification"])
    if digest(bundle) != digest(_assemble(request, result, report)):
        raise ValueError("Atmosphere preservation differs from retained report obligations")
    return detached(bundle)
