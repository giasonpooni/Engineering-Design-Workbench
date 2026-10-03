"""Representation + Morphism Registry V1.

This layer describes scientific meaning and preservation obligations for existing
semantic capabilities. It does not select engines or execute providers.
"""
from __future__ import annotations
from copy import deepcopy
import math
import re
from typing import Any

from .control_contracts import content_ref, detached, json_tree, keys, record, text
from .operations.runner import check_seal
from .semantic_capabilities import SemanticRegistry

ID = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*$")
ROLES = {"STATE","OBSERVATION","SIGNAL","SPECTRAL","SPATIAL","VISUAL","MODEL","PARAMETER","GRAPH","MATRIX","TABLE","OTHER"}
MORPHISM_KINDS = {"OBSERVE","ADMIT","PROJECT","TRANSFORM","ESTIMATE","SIMULATE","COARSEN","REFINE","RETRIEVE","NEEDLE","VERIFY","REWRITE","RENDER","RETAIN"}
EQUIVALENCE = {"EXACT","STRUCTURAL","TASK_SPECIFIC","LOSSY"}
LOSS_CLASSES = {"EXACT","STRUCTURAL","TASK_SPECIFIC","LOSSY"}
UNCERTAINTY_BEHAVIOR = {"PRESERVE","PROPAGATE","REDUCE","EXPAND","REPLACE","UNKNOWN"}
REVERSIBILITY = {"EXACT","LEFT_INVERTIBLE","RIGHT_INVERTIBLE","APPROXIMATE","NONE","UNKNOWN"}
CHECK_KINDS = {"DOMAIN","CODOMAIN","VALIDITY","PRESERVATION","LOSS","UNCERTAINTY","PROVENANCE","EXECUTION"}
CHECK_STATUS = {"PASS","FAIL","UNRESOLVED"}
MAX_LIST = 128

def _versioned(value: Any, label: str) -> str:
    if type(value) is not str or ID.fullmatch(value) is None or len(value) > 180:
        raise ValueError(f"{label} must be a bounded versioned hierarchical ID")
    return value

def _unique_text(values: Any, label: str, maximum=MAX_LIST) -> list[str]:
    if type(values) is not list or len(values) > maximum:
        raise ValueError(f"{label} must be a bounded list")
    result = [text(item) for item in values]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result

def _refs(values: Any, label: str) -> list[str]:
    if type(values) is not list or len(values) > MAX_LIST:
        raise ValueError(f"{label} must be a bounded list")
    result = [content_ref(item) for item in values]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return result

def _scale(value: Any) -> dict:
    keys(value, {"length_m","time_s","energy_j","resolution","label"})
    result = {}
    for name in ("length_m","time_s","energy_j","resolution"):
        raw = value[name]
        if raw is None:
            result[name] = None
        else:
            if type(raw) not in (int,float) or isinstance(raw,bool):
                raise ValueError(f"scale.{name} must be numerical or null")
            numeric = float(raw)
            if not math.isfinite(numeric) or numeric <= 0 or numeric > 1e150:
                raise ValueError(f"scale.{name} must be finite positive when declared")
            result[name] = numeric
    result["label"] = text(value["label"])
    return result

def representation_from_spec(spec: dict) -> dict:
    keys(spec, {"representation_id","role","source_state_type","schema_id","quantity_semantics",
                "unit_semantics","frame_semantics","time_semantics","scale","uncertainty_semantics",
                "equivalence_contract","preserved_queries","supported_interventions","recovery_route",
                "provenance_refs","notes"})
    if spec["role"] not in ROLES:
        raise ValueError("Unknown representation role")
    if spec["equivalence_contract"] not in EQUIVALENCE:
        raise ValueError("Unknown representation equivalence contract")
    recovery = spec["recovery_route"]
    if recovery is not None:
        recovery = text(recovery)
    if type(spec["notes"]) is not str or len(spec["notes"]) > 8192:
        raise ValueError("Representation notes must be bounded text")
    value = record("representation-spec",
        representation_id=_versioned(spec["representation_id"],"representation_id"),
        role=spec["role"], source_state_type=text(spec["source_state_type"]),
        schema_id=text(spec["schema_id"]), quantity_semantics=text(spec["quantity_semantics"]),
        unit_semantics=text(spec["unit_semantics"]), frame_semantics=text(spec["frame_semantics"]),
        time_semantics=text(spec["time_semantics"]), scale=_scale(spec["scale"]),
        uncertainty_semantics=text(spec["uncertainty_semantics"]),
        equivalence_contract=spec["equivalence_contract"],
        preserved_queries=_unique_text(spec["preserved_queries"],"preserved queries"),
        supported_interventions=_unique_text(spec["supported_interventions"],"supported interventions"),
        recovery_route=recovery, provenance_refs=_refs(spec["provenance_refs"],"representation provenance refs"),
        notes=spec["notes"],
        claims={"representation_not_canonical_state":True,
                "query_preservation_does_not_imply_intervention_preservation":True,
                "execution_authority":False})
    validate_representation(value)
    return value

def validate_representation(value: dict) -> dict:
    keys(value, {"schema","record_digest","representation_id","role","source_state_type","schema_id",
                 "quantity_semantics","unit_semantics","frame_semantics","time_semantics","scale",
                 "uncertainty_semantics","equivalence_contract","preserved_queries","supported_interventions",
                 "recovery_route","provenance_refs","notes","claims"})
    if value["schema"] != "ciw.representation-spec.v1":
        raise ValueError("Wrong representation schema")
    check_seal(value); _versioned(value["representation_id"],"representation_id")
    if value["role"] not in ROLES:
        raise ValueError("Unknown representation role")
    for name in ("source_state_type","schema_id","quantity_semantics","unit_semantics","frame_semantics","time_semantics","uncertainty_semantics"):
        text(value[name])
    _scale(value["scale"])
    if value["equivalence_contract"] not in EQUIVALENCE:
        raise ValueError("Unknown representation equivalence contract")
    _unique_text(value["preserved_queries"],"preserved queries")
    _unique_text(value["supported_interventions"],"supported interventions")
    if value["recovery_route"] is not None:
        text(value["recovery_route"])
    _refs(value["provenance_refs"],"representation provenance refs")
    if type(value["notes"]) is not str or len(value["notes"]) > 8192:
        raise ValueError("Representation notes must be bounded text")
    if value["claims"] != {"representation_not_canonical_state":True,
                            "query_preservation_does_not_imply_intervention_preservation":True,
                            "execution_authority":False}:
        raise ValueError("Representation claims exceed descriptive authority")
    return detached(value)

def _validity(value: Any) -> dict:
    keys(value, {"assumptions","operating_regime","failure_conditions"})
    return {"assumptions":_unique_text(value["assumptions"],"validity assumptions"),
            "operating_regime":_unique_text(value["operating_regime"],"operating regime"),
            "failure_conditions":_unique_text(value["failure_conditions"],"failure conditions")}

def _preservation(value: Any) -> dict:
    keys(value, {"queries","interventions","invariants","approximation_tolerance"})
    tolerance = value["approximation_tolerance"]
    if tolerance is not None:
        if type(tolerance) not in (int,float) or isinstance(tolerance,bool):
            raise ValueError("approximation_tolerance must be numerical or null")
        tolerance=float(tolerance)
        if not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError("approximation_tolerance must be finite nonnegative")
    return {"queries":_unique_text(value["queries"],"preserved queries"),
            "interventions":_unique_text(value["interventions"],"preserved interventions"),
            "invariants":_unique_text(value["invariants"],"preserved invariants"),
            "approximation_tolerance":tolerance}

def _loss(value: Any) -> dict:
    keys(value, {"class","description","metrics"})
    if value["class"] not in LOSS_CLASSES:
        raise ValueError("Unknown morphism loss class")
    if type(value["metrics"]) is not dict or len(value["metrics"]) > 64:
        raise ValueError("loss metrics must be a bounded object")
    json_tree(value["metrics"])
    return {"class":value["class"],"description":text(value["description"]),"metrics":deepcopy(value["metrics"])}

def _uncertainty(value: Any) -> dict:
    keys(value, {"behavior","method"})
    if value["behavior"] not in UNCERTAINTY_BEHAVIOR:
        raise ValueError("Unknown uncertainty behavior")
    method=value["method"]
    if method is not None:
        method=text(method)
    return {"behavior":value["behavior"],"method":method}

def morphism_from_spec(spec: dict, representations: dict[str,dict], semantic: SemanticRegistry) -> dict:
    keys(spec, {"morphism_id","kind","domain_representation_id","codomain_representation_id",
                "semantic_capability","parameter_names","preconditions","validity","preservation","loss",
                "uncertainty","reversibility","authority_requirements","verification_requirements",
                "provenance_refs","notes"})
    if spec["kind"] not in MORPHISM_KINDS:
        raise ValueError("Unknown scientific morphism kind")
    domain=_versioned(spec["domain_representation_id"],"domain representation")
    codomain=_versioned(spec["codomain_representation_id"],"codomain representation")
    if domain not in representations or codomain not in representations:
        raise ValueError("Morphism domain/codomain must be declared representations")
    capability=spec["semantic_capability"]
    if capability is not None:
        capability=_versioned(capability,"semantic capability")
        if capability not in semantic._morphisms:
            raise ValueError("Morphism semantic capability is not declared")
    if spec["reversibility"] not in REVERSIBILITY:
        raise ValueError("Unknown morphism reversibility")
    if type(spec["notes"]) is not str or len(spec["notes"]) > 8192:
        raise ValueError("Morphism notes must be bounded text")
    value=record("scientific-morphism",
        morphism_id=_versioned(spec["morphism_id"],"morphism_id"),kind=spec["kind"],
        domain_representation_id=domain,codomain_representation_id=codomain,
        semantic_capability=capability,parameter_names=_unique_text(spec["parameter_names"],"parameter names"),
        preconditions=_unique_text(spec["preconditions"],"morphism preconditions"),
        validity=_validity(spec["validity"]),preservation=_preservation(spec["preservation"]),
        loss=_loss(spec["loss"]),uncertainty=_uncertainty(spec["uncertainty"]),
        reversibility=spec["reversibility"],
        authority_requirements=_unique_text(spec["authority_requirements"],"authority requirements"),
        verification_requirements=_unique_text(spec["verification_requirements"],"verification requirements"),
        provenance_refs=_refs(spec["provenance_refs"],"morphism provenance refs"),notes=spec["notes"],
        claims={"typed_scientific_morphism":True,"semantic_capability_is_execution_link_not_truth":True,
                "finite_witness_required_for_empirical_claim":True,"execution_authority":False})
    validate_morphism(value,representations,semantic); return value

def validate_morphism(value: dict, representations: dict[str,dict], semantic: SemanticRegistry) -> dict:
    keys(value, {"schema","record_digest","morphism_id","kind","domain_representation_id",
                 "codomain_representation_id","semantic_capability","parameter_names","preconditions",
                 "validity","preservation","loss","uncertainty","reversibility","authority_requirements",
                 "verification_requirements","provenance_refs","notes","claims"})
    if value["schema"]!="ciw.scientific-morphism.v1":
        raise ValueError("Wrong scientific morphism schema")
    check_seal(value); _versioned(value["morphism_id"],"morphism_id")
    if value["kind"] not in MORPHISM_KINDS: raise ValueError("Unknown scientific morphism kind")
    for name in ("domain_representation_id","codomain_representation_id"):
        rep_id=_versioned(value[name],name)
        if rep_id not in representations: raise ValueError("Morphism references an unknown representation")
    capability=value["semantic_capability"]
    if capability is not None:
        capability=_versioned(capability,"semantic capability")
        if capability not in semantic._morphisms: raise ValueError("Morphism semantic capability is not declared")
    _unique_text(value["parameter_names"],"parameter names"); _unique_text(value["preconditions"],"morphism preconditions")
    _validity(value["validity"]); _preservation(value["preservation"]); _loss(value["loss"]); _uncertainty(value["uncertainty"])
    if value["reversibility"] not in REVERSIBILITY: raise ValueError("Unknown morphism reversibility")
    _unique_text(value["authority_requirements"],"authority requirements")
    _unique_text(value["verification_requirements"],"verification requirements")
    _refs(value["provenance_refs"],"morphism provenance refs")
    if type(value["notes"]) is not str or len(value["notes"])>8192: raise ValueError("Morphism notes must be bounded text")
    if value["claims"] != {"typed_scientific_morphism":True,"semantic_capability_is_execution_link_not_truth":True,
                            "finite_witness_required_for_empirical_claim":True,"execution_authority":False}:
        raise ValueError("Morphism claims exceed contract scope")
    return detached(value)

def registry_from_specs(representation_specs: list[dict], morphism_specs: list[dict], semantic: SemanticRegistry) -> dict:
    if not isinstance(semantic,SemanticRegistry): raise TypeError("Registry requires SemanticRegistry")
    if type(representation_specs) is not list or not 1<=len(representation_specs)<=256:
        raise ValueError("Registry requires 1..256 representations")
    reps=[representation_from_spec(item) for item in representation_specs]
    rep_map={item["representation_id"]:item for item in reps}
    if len(rep_map)!=len(reps): raise ValueError("Duplicate representation identity")
    if type(morphism_specs) is not list or len(morphism_specs)>512: raise ValueError("Registry morphism count exceeds bound")
    morphisms=[morphism_from_spec(item,rep_map,semantic) for item in morphism_specs]
    morphism_map={item["morphism_id"]:item for item in morphisms}
    if len(morphism_map)!=len(morphisms): raise ValueError("Duplicate morphism identity")
    value=record("morphism-registry",representations=rep_map,morphisms=morphism_map,
                 semantic_catalog_ref=content_ref(semantic.catalog()["record_digest"]),
                 claims={"describes_scientific_semantics":True,"selects_engine":False,
                         "authorizes_execution":False,"canonical_state_authority":False})
    validate_registry(value,semantic); return value

def validate_registry(value: dict, semantic: SemanticRegistry) -> dict:
    keys(value, {"schema","record_digest","representations","morphisms","semantic_catalog_ref","claims"})
    if value["schema"]!="ciw.morphism-registry.v1": raise ValueError("Wrong morphism registry schema")
    check_seal(value); content_ref(value["semantic_catalog_ref"])
    if value["semantic_catalog_ref"]!=semantic.catalog()["record_digest"]:
        raise ValueError("Morphism registry is bound to a different semantic catalog")
    if type(value["representations"]) is not dict or not value["representations"]:
        raise ValueError("Registry representations must be nonempty")
    reps={}
    for key,row in value["representations"].items():
        if key!=row.get("representation_id"): raise ValueError("Representation map key differs from identity")
        reps[key]=validate_representation(row)
    if type(value["morphisms"]) is not dict: raise ValueError("Registry morphisms must be an object")
    for key,row in value["morphisms"].items():
        if key!=row.get("morphism_id"): raise ValueError("Morphism map key differs from identity")
        validate_morphism(row,reps,semantic)
    if value["claims"] != {"describes_scientific_semantics":True,"selects_engine":False,
                            "authorizes_execution":False,"canonical_state_authority":False}:
        raise ValueError("Morphism registry claims exceed descriptive authority")
    return detached(value)

def witness_from_spec(registry: dict, semantic: SemanticRegistry, spec: dict) -> dict:
    registry=validate_registry(registry,semantic)
    keys(spec, {"witness_id","morphism_id","source_evidence_id","execution_ref","result_ref","checks","notes"})
    morphism_id=_versioned(spec["morphism_id"],"morphism_id")
    if morphism_id not in registry["morphisms"]: raise ValueError("Witness references unknown morphism")
    checks=spec["checks"]
    if type(checks) is not list or not 1<=len(checks)<=MAX_LIST: raise ValueError("Witness requires 1..128 checks")
    seen=set(); normalized=[]
    for item in checks:
        keys(item, {"check_id","kind","status","evidence_ref","notes"})
        check_id=text(item["check_id"])
        if check_id in seen: raise ValueError("Duplicate witness check")
        seen.add(check_id)
        if item["kind"] not in CHECK_KINDS or item["status"] not in CHECK_STATUS: raise ValueError("Invalid witness check")
        evidence=item["evidence_ref"]
        if item["status"]=="PASS" and evidence is None: raise ValueError("Passing witness check requires evidence")
        if evidence is not None: evidence=content_ref(evidence)
        if type(item["notes"]) is not str or len(item["notes"])>2048: raise ValueError("Witness check notes must be bounded")
        normalized.append({"check_id":check_id,"kind":item["kind"],"status":item["status"],"evidence_ref":evidence,"notes":item["notes"]})
    if type(spec["notes"]) is not str or len(spec["notes"])>4096: raise ValueError("Witness notes must be bounded text")
    value=record("morphism-witness",witness_id=text(spec["witness_id"]),registry_ref=registry["record_digest"],
                 morphism_id=morphism_id,morphism_ref=registry["morphisms"][morphism_id]["record_digest"],
                 source_evidence_id=content_ref(spec["source_evidence_id"]),
                 execution_ref=content_ref(spec["execution_ref"]),result_ref=content_ref(spec["result_ref"]),
                 checks=normalized,notes=spec["notes"],
                 claims={"finite_execution_witness":True,"general_morphism_law_proved":False,
                         "cross_representation_commutativity_proved":False,"physical_validity_established":False})
    validate_witness(value,registry); return value

def validate_witness(value: dict, registry: dict) -> dict:
    keys(value, {"schema","record_digest","witness_id","registry_ref","morphism_id","morphism_ref",
                 "source_evidence_id","execution_ref","result_ref","checks","notes","claims"})
    if value["schema"]!="ciw.morphism-witness.v1": raise ValueError("Wrong morphism witness schema")
    check_seal(value); text(value["witness_id"])
    for name in ("registry_ref","morphism_ref","source_evidence_id","execution_ref","result_ref"): content_ref(value[name])
    if value["registry_ref"]!=registry["record_digest"]: raise ValueError("Witness references a different registry")
    morphism_id=_versioned(value["morphism_id"],"morphism_id")
    if morphism_id not in registry["morphisms"]: raise ValueError("Witness references unknown morphism")
    if value["morphism_ref"]!=registry["morphisms"][morphism_id]["record_digest"]: raise ValueError("Witness morphism identity mismatch")
    if type(value["checks"]) is not list or not value["checks"]: raise ValueError("Witness requires checks")
    seen=set()
    for item in value["checks"]:
        keys(item, {"check_id","kind","status","evidence_ref","notes"})
        cid=text(item["check_id"])
        if cid in seen: raise ValueError("Duplicate witness check")
        seen.add(cid)
        if item["kind"] not in CHECK_KINDS or item["status"] not in CHECK_STATUS: raise ValueError("Invalid witness check")
        if item["status"]=="PASS" and item["evidence_ref"] is None: raise ValueError("Passing witness check requires evidence")
        if item["evidence_ref"] is not None: content_ref(item["evidence_ref"])
    if value["claims"] != {"finite_execution_witness":True,"general_morphism_law_proved":False,
                            "cross_representation_commutativity_proved":False,"physical_validity_established":False}:
        raise ValueError("Witness claims exceed finite execution evidence")
    return detached(value)

def inspect_registry(value: dict, semantic: SemanticRegistry) -> dict:
    checked=validate_registry(value,semantic)
    return {"schema":"ciw.morphism-registry-inspection.v1","record_digest":checked["record_digest"],
            "representations":len(checked["representations"]),"morphisms":len(checked["morphisms"]),
            "semantic_capabilities":sorted({row["semantic_capability"] for row in checked["morphisms"].values() if row["semantic_capability"] is not None}),
            "selects_engine":False,"authorizes_execution":False}
