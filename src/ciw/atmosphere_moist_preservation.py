"""Typed finite-profile receipts for a declared frozen-composition moist column.

The existing preservation APIs bind an independently checked retained report.
Inspection does not compile a column, replay numerical quadrature, activate a
receiver or admit canonical state.
"""
from __future__ import annotations

from copy import deepcopy

from .atmosphere_moist_contract import EXPANSION_OBSERVABLES, SUPPORTED_OBSERVABLES, validate_request
from .control_contracts import detached, keys
from .control_plane import CapabilityRegistry
from .operations.runner import check_seal, digest, seal
from .preservation_contracts import (
    admission_gate_from_spec, contract_from_spec, validate_admission_gate,
    validate_contract, validate_verification, verification_from_spec,
)
from .representation_morphisms import registry_from_specs, validate_registry
from .semantic_capabilities import SemanticRegistry

SCHEMA = "ciw.atmosphere-moist-preservation.v1"
SOURCE = "atmosphere.moist-declared-column.v1"
TARGET = "atmosphere.moist-sampled-column.v1"
MORPHISM = "atmosphere.moist-column-compilation.v1"
PROPERTY_IDS = {
    name: "atmosphere.moist." + name.replace("_", "-") + ".v1"
    for name in SUPPORTED_OBSERVABLES | EXPANSION_OBSERVABLES
}
EXTRA_OMISSIONS = (
    "continuous_height_profile", "horizontal_structure", "time_evolution",
    "aerodynamic_forces", "material_temperature", "material_moisture_content",
    "optical_composition", "transport_law", "dynamic_viscosity",
    "kinematic_viscosity", "latent_heat", "condensate", "humidity_history",
)
CLAIMS = {
    "uses_existing_preservation_contracts": True,
    "synthetic_numerical_scope_only": True,
    "finite_retained_profile_only": True,
    "physical_validation_established": False,
    "standard_atmosphere_certification_established": False,
    "wmo_humidity_conformance_established": False,
    "phase_change_established": False,
    "transport_law_established": False,
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
    ("wind", "prescribed_wind"),
    ("humidity", "relative_humidity"),
    ("vapour_pressure", "vapour_partial_pressure"),
    ("dew_point", "dew_point_closure"),
    ("mixing_ratio", "mixture_parameters"),
    ("sound_speed", "frozen_sound_speed"),
    ("frozen_potential_temperature", "frozen_potential_temperature"),
    ("hydrostatic_profile", "segment_hydrostatic_balance"),
    ("quadrature_refinement", "quadrature_refinement"),
)


def _semantic() -> SemanticRegistry:
    return SemanticRegistry(CapabilityRegistry())


def _property(name: str) -> str:
    return PROPERTY_IDS.get(name, "atmosphere.moist." + name.replace("_", "-") + ".v1")


def _representation(identity, role, schema_id, refs, scale, queries):
    return {
        "representation_id": identity, "role": role,
        "source_state_type": "prescribed_unsaturated_constant_mixing_ratio_hydrostatic_column",
        "schema_id": schema_id,
        "quantity_semantics": "temperature, pressure, constituent and mixture density, liquid-water humidity diagnostics, fixed water mixing ratio, frozen-composition sound speed and potential temperature, and prescribed ENU wind at declared relative heights",
        "unit_semantics": "SI: height m; temperature and dew point K; pressure Pa; density kg/m^3; sound and wind m/s; humidity and water mass fraction dimensionless; mixing ratio kg/kg dry air",
        "frame_semantics": "declared local ENU frame; heights above a separately retained reference-height origin; source context is a declaration",
        "time_semantics": "one declared static column; optional context time does not establish measured weather or atmospheric evolution",
        "scale": scale,
        "uncertainty_semantics": "retained normalized numerical acceptance thresholds only; source, input and physical-model uncertainty unqualified",
        "equivalence_contract": "TASK_SPECIFIC", "preserved_queries": queries,
        "supported_interventions": [],
        "recovery_route": "retained strict moist atmosphere request, exact ordered height samples and independent numerical report",
        "provenance_refs": refs,
        "notes": "Constant water mixing ratio, temperature lapse and wind are prescribed. Ideal constituents and fixed heat capacities supply a frozen-composition model. Pure-liquid Magnus humidity omits pressure enhancement and ice; a continuous unsaturation guard qualifies the declared analytic law only. Transport, phase change, latent heat, clouds, chemistry, optics and specimen conditioning are absent. Numerical acceptance does not establish physical or weather validity.",
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
        [_representation(SOURCE, "MODEL", "ciw.atmosphere-moist-request.v1", [request_ref, report_ref], scale, queries),
         _representation(TARGET, "SIGNAL", "ciw.atmosphere-moist-result.v1", [result_ref, report_ref], scale, queries)],
        [{"morphism_id": MORPHISM, "kind": "SIMULATE",
          "domain_representation_id": SOURCE, "codomain_representation_id": TARGET,
          "semantic_capability": None,
          "parameter_names": sorted("reference." + name for name in request["reference"])
                             + sorted("profile." + name for name in request["profile"])
                             + ["sampling.height_m"],
          "preconditions": ["strict bounded SI moist-column declaration", "ordered height grid starts at the retained reference"],
          "validity": {
              "assumptions": ["ideal dry-air and water-vapour constituents", "constant water mixing ratio", "constant gravity", "prescribed linear temperature lapse", "fixed constituent heat capacities", "pure-liquid Magnus humidity diagnostic without pressure enhancement", "prescribed constant ENU wind"],
              "operating_regime": ["exact retained request and sampled height grid", "declared bounded warm, unsaturated column with frozen composition"],
              "failure_conditions": ["failed independent numerical or declared-domain checks", "sampled or continuous relative humidity above 0.95", "requested unrepresented transport, phase, dynamic, optical or material response"],
          },
          "preservation": {"queries": queries, "interventions": [], "invariants": [], "approximation_tolerance": None},
          "loss": {"class": "TASK_SPECIFIC", "description": "finite static moist-column samples with prescribed composition and wind; transport and phase response absent", "metrics": {}},
          "uncertainty": {"behavior": "UNKNOWN", "method": "numerical thresholds only; input and physical-model uncertainty unqualified"},
          "reversibility": "NONE", "authority_requirements": [],
          "verification_requirements": ["independent retained constituent and hydrostatic checks", "independent segment quadrature and refinement acceptance", "hard sampled and continuous unsaturation acceptance", "all report checks PASS and LOCAL qualification"],
          "provenance_refs": refs,
          "notes": "Declarative SIMULATE for the fixed installed moist atmospheric compiler. Session owns execution. Numerical diagnostics and the selected law's continuous unsaturation guard establish numerical eligibility only; no provider activation, experimental qualification or cross-scale witness.",
        }], sem,
    )
    checks_by_name = {row["name"]: row for row in report["checks"]}
    effects = [{
        "property_id": _property(name), "effect": "BOUND", "output_property_id": _property(name),
        "transform_id": None,
        "bound": {"metric": "maximum_declared_normalized_" + check_name + "_residual",
                  "upper_bound": checks_by_name[check_name]["tolerance"],
                  "unit": "1", "composition": "ADDITIVE_ABSOLUTE"},
        "notes": "Numerical threshold for the exact retained finite profile and named report residual; no measured-state or receiver-model error bound. Sound and potential temperature are frozen-composition quantities.",
    } for name, check_name in DEFINITIONS]
    omissions = sorted(EXPANSION_OBSERVABLES | set(EXTRA_OMISSIONS))
    effects.extend({"property_id": _property(name), "effect": "FORGET", "output_property_id": None,
                    "transform_id": None, "bound": None,
                    "notes": "Explicit absence from this finite frozen-composition schema; no richer physical state was reduced or validated."}
                   for name in omissions)
    acceptance = "atmosphere.moist.independent-report-acceptance.v1"
    locality = "atmosphere.moist.local-qualification.v1"
    requirements = {acceptance: [row["name"] for row in report["checks"]], locality: []}
    contract = contract_from_spec(registry, sem, {
        "contract_id": "atmosphere.moist-column-preservation.v1", "morphism_id": MORPHISM,
        "requires": list(requirements), "effects": effects,
        "notes": "Every retained independent check and LOCAL qualification are required. FORGET denotes schema omission. Eligibility is distinct from physical qualification and canonical admission.",
    })

    def receipt(kind, identity, names):
        status = _status([checks_by_name.get(name) for name in names])
        return {"kind": kind, "property_id": identity, "status": status,
                "method": "NUMERICAL_BOUND" if status != "UNRESOLVED" else "NOT_PERFORMED",
                "evidence_ref": report_ref, "notes": "Exact retained report checks: " + ", ".join(names)}

    checks = [receipt("REQUIRE", acceptance, requirements[acceptance])]
    local = (report["qualification"]["action"] == "LOCAL" and report["status"] == "PASS"
             and all(row["status"] == "PASS" for row in report["checks"]))
    checks.append({"kind": "REQUIRE", "property_id": locality,
                   "status": "VERIFIED" if local else "REFUTED", "method": "EXACT_ALGEBRA",
                   "evidence_ref": report_ref,
                   "notes": "Exact retained qualification must be LOCAL, report status PASS, and every report check PASS; this is numerical eligibility only."})
    checks.extend(receipt("BOUND", _property(name), [check_name]) for name, check_name in DEFINITIONS)
    checks.extend({"kind": "FORGET", "property_id": _property(name), "status": "VERIFIED",
                   "method": "EXACT_ALGEBRA", "evidence_ref": result_ref,
                   "notes": "Exact schema omission: no " + name + " is represented or physically qualified."}
                  for name in omissions)
    verification = verification_from_spec(registry, sem, contract, {
        "verification_id": "atmosphere.moist-column-preservation-verification.v1",
        "source_state_ref": request_ref, "candidate_state_ref": result_ref, "checks": checks,
        "notes": "Typed receipt of the exact retained numerical report. No formal proof, measured weather qualification, physical continuum guarantee or receiver validation.",
    })
    gate = admission_gate_from_spec(registry, sem, contract, verification, {
        "gate_id": "atmosphere.moist-column-preservation-gate.v1",
        "forbidden_forgets": sorted(_property(name) for name in request["desired_observables"]
                                    if name in EXPANSION_OBSERVABLES),
        "notes": "Numerical eligibility requires LOCAL and all checks PASS under the explicit loss policy. No physical or canonical-state admission.",
    })
    return seal({"schema": SCHEMA, "request_digest": request_ref, "result_digest": result_ref,
                 "report_digest": report_ref, "registry": registry, "contract": contract,
                 "verification": verification, "admission_gate": gate, "claims": deepcopy(CLAIMS)})


def build(request: dict, result: dict, report: dict) -> dict:
    """Build typed receipts from retained artifacts without numerical replay."""
    from .atmosphere_moist_verification import validate_report
    request = validate_request(request)
    validate_report(request, result, report)
    return _assemble(request, result, report)


def validate(bundle: dict, request: dict, result: dict, report: dict) -> dict:
    """Validate exact static obligations using the existing preservation APIs."""
    from .atmosphere_moist_verification import validate_report
    keys(bundle, {"schema", "record_digest", "request_digest", "result_digest", "report_digest",
                  "registry", "contract", "verification", "admission_gate", "claims"})
    check_seal(bundle)
    request = validate_request(request)
    validate_report(request, result, report)
    if (bundle["schema"] != SCHEMA or bundle["claims"] != CLAIMS
            or bundle["request_digest"] != digest(request)
            or bundle["result_digest"] != result["record_digest"]
            or bundle["report_digest"] != report["record_digest"]):
        raise ValueError("Moist atmosphere preservation scope or content binding differs")
    sem = _semantic()
    validate_registry(bundle["registry"], sem)
    validate_contract(bundle["contract"], bundle["registry"], sem)
    validate_verification(bundle["verification"], bundle["registry"], sem, bundle["contract"])
    validate_admission_gate(bundle["admission_gate"], bundle["registry"], sem,
                            bundle["contract"], bundle["verification"])
    if digest(bundle) != digest(_assemble(request, result, report)):
        raise ValueError("Moist atmosphere preservation differs from retained report obligations")
    return detached(bundle)
