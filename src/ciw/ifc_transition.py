"""Actual IFC bytes through pinned CSE into NET's existing review boundaries.

The independent verifier covers one explicit length quantity, its imported prior
and every RAW Gaussian posterior entry. Derived geometry and physical truth are
outside that verification scope. Whole original IFC bytes are retained, including
when CSE refuses lowering; no repair or hidden subset is executed.
"""
from __future__ import annotations

import base64
from copy import deepcopy
import math
from pathlib import Path
import re
import uuid

from . import bim_quantity
from .adapters.protocol import AdapterRefusal
from .adapters.subprocess import _json
from .control_contracts import content_ref, keys, state, text
from .control_plane import builtin_registry
from .core.covariance import create_covariance_artifact
from .declared_workload import AUTHORITY, RESULT_SCHEMA
from .industrial_transition import binding_from_spec, identity_verification_from_spec, transition_envelope_from_spec
from .interop_ingress import CHECK_KINDS, identity_reference_from_qualification, ingress_from_spec, profile_from_spec, qualify_ingress, verification_from_spec as ingress_verification
from .ifc_subset_verifier import inspect_source
from .operations.runner import check_seal, seal
from .preservation_contracts import admission_gate_from_spec, contract_from_spec, verification_from_spec as preservation_verification
from .representation_morphisms import registry_from_specs
from .semantic_capabilities import builtin_semantic_registry
from .telemetry import byte_digest, canonical, digest

SCHEMA = "ciw.ifc-transition-run.v1"
PROVIDER_TREE = "d1bea6737380b1cdd8f42f9962e282f1047dceec"
SCOPE = "one explicit declared IFC length quantity; logical source-object identity only"
AUDIT_BOOTSTRAP = """import json,sys\nsys.path.insert(0,sys.argv[1])\nfrom gat.ifc_audit import audit_ifc_text\nraw=sys.stdin.buffer.read()\nreport=audit_ifc_text(raw.decode('utf-8'),source=sys.argv[2]).to_dict()\nprint(json.dumps(report,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False))\n"""


def _blob(raw):
    return {"sha256": byte_digest(raw), "byte_count": len(raw),
            "bytes_b64": base64.b64encode(raw).decode("ascii")}


def _unblob(value, limit=4 * 1024 * 1024):
    keys(value, {"sha256", "byte_count", "bytes_b64"})
    if type(value["bytes_b64"]) is not str or len(value["bytes_b64"]) > 4 * ((limit + 2) // 3):
        raise ValueError("Retained IFC transport exceeds byte budget")
    raw = base64.b64decode(value["bytes_b64"], validate=True)
    if len(raw) > limit or value != _blob(raw):
        raise ValueError("Retained IFC transport byte binding mismatch")
    return raw


class RetainedBimWorkflow(bim_quantity.BimQuantityWorkflow):
    """Same native operation and Session; additionally keep actual stdout bytes."""
    def _step(self, source, evidence_id, bound):
        adapter, runtime, _ = bound
        if self._runtime_projection(adapter.runtime_identity()) != self._runtime_projection(runtime):
            raise ValueError("CSE provider identity changed")
        code, raw = adapter._run(bim_quantity._BOOTSTRAP, [str(adapter.source_root)], canonical(source))
        adapter.runtime_identity()
        if code:
            raise AdapterRefusal("BIM_QUANTITY_REFUSED", "Pinned CSE refused bounded IFC execution")
        data = _json(raw)
        bim_quantity._check_data(source, data)
        occurrence = "execution-" + uuid.uuid4().hex
        result = {"schema": RESULT_SCHEMA, "operation_id": self.operation, "execution_ref": occurrence,
                  "input_refs": [evidence_id], "data": data, "authority": AUTHORITY}
        result["result_id"] = digest(result)
        numerical = {"operation_id": self.operation, "data": data}
        return {"runtime_ref": self.role, "operation_id": self.operation, "execution_id": occurrence,
                "input_refs": [evidence_id], "request": source, "request_sha256": digest(source),
                "result": result, "result_sha256": digest(result), "result_id": result["result_id"],
                "numerical_result": numerical, "numerical_result_id": digest(numerical),
                "transport_output": _blob(raw)}

    def _validate_step(self, step, source, evidence_id):
        if type(step) is not dict or "transport_output" not in step:
            raise ValueError("IFC adapter requires exact native mapped-output bytes")
        raw = _unblob(step["transport_output"])
        if canonical(_json(raw)) != canonical(step["result"]["data"]):
            raise ValueError("Native output bytes differ from mapped result")
        super()._validate_step({key: value for key, value in step.items() if key != "transport_output"}, source, evidence_id)


workflow = RetainedBimWorkflow()


def _closure():
    # Bounded source commitments, not signatures or binary-authenticated
    # transitive dependency identities.
    files = ("ifc_transition.py", "ifc_subset_verifier.py", "bim_quantity.py", "adapters/subprocess.py",
             "declared_workload.py", "control_contracts.py", "control_plane.py", "core/covariance.py",
             "operations/runner.py", "interop_ingress.py", "industrial_transition.py", "preservation_contracts.py",
             "representation_morphisms.py", "semantic_capabilities.py", "telemetry.py", "exchange.py")
    return {name: byte_digest((Path(__file__).parent / name).read_bytes()) for name in files}


def _spec(value, ifc):
    keys(value, {"run_id", "canonical_entity_id", "required_admission_authority", "target", "model_frame", "source_provenance"})
    if type(value["run_id"]) is not str or not re.fullmatch(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*", value["run_id"]):
        raise ValueError("IFC run_id must be a versioned hierarchical ID")
    text(value["canonical_entity_id"])
    if type(value["required_admission_authority"]) is not str or not re.fullmatch(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*", value["required_admission_authority"]):
        raise ValueError("IFC admission authority must be a versioned hierarchical ID")
    bim_quantity._target(value["target"])
    if value["model_frame"] is not None:
        text(value["model_frame"])
    provenance = value["source_provenance"]
    keys(provenance, {"kind", "source_uri", "revision", "source_path", "license", "sha256"})
    if provenance["kind"] not in {"PUBLIC_REFERENCE", "SYNTHETIC_FIXTURE", "USER_ARTIFACT"}:
        raise ValueError("Declare artifact provenance kind")
    for field in ("source_uri", "revision", "source_path", "license"):
        text(provenance[field])
    content_ref(provenance["sha256"])
    if provenance["sha256"] != byte_digest(ifc):
        raise ValueError("Original IFC bytes differ from declared artifact provenance")
    return deepcopy(value)


def _audit(raw, bound):
    adapter, runtime, _ = bound
    if workflow._runtime_projection(adapter.runtime_identity()) != workflow._runtime_projection(runtime):
        raise ValueError("CSE changed before IFC audit")
    code, output = adapter._run(AUDIT_BOOTSTRAP, [str(adapter.source_root), byte_digest(raw)], raw)
    adapter.runtime_identity()
    if code:
        raise AdapterRefusal("IFC_AUDIT_FAILED", "Pinned CSE audit did not produce a retained inventory")
    return seal({"schema": "ciw.ifc-native-audit-occurrence.v1", "execution_id": "execution-" + uuid.uuid4().hex,
                 "operation_id": "cse.ifc-audit.v1", "input_ref": byte_digest(raw),
                 "runtime_ref": digest(runtime), "bootstrap_ref": byte_digest(AUDIT_BOOTSTRAP.encode()),
                 "transport_output": _blob(output), "data": _json(output), "authority": AUTHORITY})


def _verify_audit(value, ifc, runtime, inspected):
    keys(value, {"schema", "record_digest", "execution_id", "operation_id", "input_ref", "runtime_ref", "bootstrap_ref", "transport_output", "data", "authority"})
    check_seal(value)
    if (value["schema"] != "ciw.ifc-native-audit-occurrence.v1" or value["operation_id"] != "cse.ifc-audit.v1"
            or not re.fullmatch(r"execution-[a-f0-9]{32}", value["execution_id"])
            or value["input_ref"] != byte_digest(ifc) or value["runtime_ref"] != digest(runtime)
            or value["bootstrap_ref"] != byte_digest(AUDIT_BOOTSTRAP.encode()) or value["authority"] != AUTHORITY
            or canonical(_json(_unblob(value["transport_output"]))) != canonical(value["data"])):
        raise ValueError("Native IFC audit occurrence binding mismatch")
    report = value["data"]
    if report["source"] != {"path": byte_digest(ifc), "sha256": byte_digest(ifc)[7:], "size_bytes": len(ifc)}:
        raise ValueError("IFC audit source identity differs from original bytes")
    if report["schema"] != inspected["source_schema"] or report["schema"] != "IFC4":
        raise ValueError("IFC audit schema differs from actual bounded IFC4 profile")
    if report["units"] != inspected["length_units"]:
        raise ValueError("IFC audit unit inventory differs from project-assigned source units")
    if report["assurance"] != {"audit_authorizes_decisions": False, "requires_explicit_decision_scope": True, "partial_ingestion_may_authorize": False}:
        raise ValueError("IFC audit assurance exceeds non-mutating inventory scope")
    if report["parse"]["status"] != "PASS" or report["inventory"]["instance_count"] != inspected["instance_count"] or report["inventory"]["type_counts"] != inspected["type_counts"]:
        raise ValueError("IFC audit inventory differs from independent STEP inspection")
    rows = [row for row in report["entities"] if row["global_id"] == inspected["target"]["global_id"]]
    if len(rows) != 1 or rows[0]["step_id"] != inspected["source_step_id"] or rows[0]["canonical_class"] != inspected["target"]["ifc_class"]:
        raise ValueError("IFC audit target differs from independent source-object identity")
    row = rows[0]
    quantity = inspected["target"]["quantity"]
    if inspected["quantity_present"] != (quantity in row["available_quantities"]):
        raise ValueError("IFC audit target quantity presence differs from source links")
    if not inspected["quantity_present"] and (quantity not in row["missing_quantities"] or report["pipeline"]["pipeline_ready"] or report["pipeline"]["lowering"]["status"] != "BLOCKED"):
        raise ValueError("Missing source quantity cannot become an audit-ready world")


def _near(actual, expected):
    # No absolute variance floor: a 1e-20 result cannot be replaced by 1e-13.
    # The tolerance is relative to the expected quantity plus a float64 ulp
    # allowance, including exactly-zero off-diagonal entries.
    if not math.isclose(float(actual), float(expected), rel_tol=2e-10, abs_tol=32 * math.ulp(float(expected))):
        raise ValueError("Independent RAW Gaussian/source mapping check failed")


def _independent_checked(source, data, inspected):
    observation = bim_quantity._observation(source)
    if data["reason"] == "native_refusal":
        return {"mapping_status": "REFUTED" if not inspected["quantity_present"] else "UNRESOLVED",
                "reason": "source_target_quantity_missing" if not inspected["quantity_present"] else "native_lowering_refused",
                "verified_raw_posterior_entries": 0, "target_row": None}
    if not inspected["quantity_present"] or data["unit_context"] != inspected["unit_context"]:
        raise ValueError("Native prior requires the actual declared source quantity and SI unit context")
    prior, posterior = data["prior"], data["posterior"]
    row = next((i for i, q in enumerate(prior["quantities"]) if all(q[key] == source["target"][key] for key in source["target"])), None)
    if row is None or prior["quantities"][row]["role"] != "raw" or prior["quantities"][row]["unit"] != "m":
        raise ValueError("Native mapped target must be the declared raw metre quantity")
    _near(prior["mean"][row], inspected["nominal_metres"])
    _near(prior["covariance"][row][row], inspected["prior_sigma_metres"] ** 2)
    raw_rows = [i for i, q in enumerate(prior["quantities"]) if q["role"] == "raw"]
    actual_raw = [{key: prior["quantities"][i][key] for key in ("ifc_class", "global_id", "quantity")} for i in raw_rows]
    actual_raw.sort(key=lambda q: (q["ifc_class"], q["global_id"], q["quantity"]))
    if actual_raw != inspected["raw_quantity_inventory"]:
        raise ValueError("Native RAW inventory is incomplete or differs from the whole source profile")
    # CSE's imported RAW belief is diagonal with declared per-quantity sigmas.
    # Check every source-backed RAW entry, not only the measured target. This
    # profile refuses optional structural/material quantities it cannot check.
    ifc = bim_quantity._bytes(source["ifc_bytes_b64"], 65536)
    for i in raw_rows:
        q = prior["quantities"][i]
        descriptor = inspect_source(ifc, {key: q[key] for key in ("ifc_class", "global_id", "quantity")})
        if not descriptor["quantity_present"] or q["unit"] != "m":
            raise ValueError("Every imported RAW quantity must have a supported explicit source length")
        _near(prior["mean"][i], descriptor["nominal_metres"])
        for j in raw_rows:
            _near(prior["covariance"][i][j], descriptor["prior_sigma_metres"] ** 2 if i == j else 0.0)
    checked = 0
    if data["status"] == "accepted":
        innovation = observation["value"] - prior["mean"][row]
        denominator = prior["covariance"][row][row] + observation["variance"]
        for i in raw_rows:
            _near(posterior["mean"][i], prior["mean"][i] + prior["covariance"][i][row] / denominator * innovation)
            for j in raw_rows:
                expected_variance = prior["covariance"][row][row] * observation["variance"] / denominator
                expected = expected_variance if i == row and j == row else prior["covariance"][i][j]
                _near(posterior["covariance"][i][j], expected)
                checked += 1
        verdict, reason = "VERIFIED", "raw_scalar_conditioning_verified"
    elif data["status"] == "held":
        verdict, reason = "UNRESOLVED", data["reason"]
    else:
        verdict, reason = "REFUTED", data["reason"]
    return {"mapping_status": verdict, "reason": reason, "verified_raw_posterior_entries": checked,
            "target_row": row}


def _independent(source, data, inspected):
    try:
        return _independent_checked(source, data, inspected)
    except ValueError:
        # A structurally valid native operation can disagree with the independent
        # source or numerical check. Keep that actual execution as counterevidence;
        # withhold projection rather than losing its occurrence on rejection.
        return {"mapping_status": "REFUTED", "reason": "independent_mapping_disagreement",
                "verified_raw_posterior_entries": 0, "target_row": None}


def _representation(rep_id, role):
    return {"representation_id": rep_id, "role": role, "source_state_type": "ifc-declared-length-quantity",
            "schema_id": "IFC STEP bounded quantity profile / ciw.state.v1", "quantity_semantics": SCOPE,
            "unit_semantics": "explicit project SI length units converted to metres", "frame_semantics": "operator-declared frame; no surveyed transform",
            "time_semantics": "logical before/after native conditioning; no physical acquisition timestamp claim",
            "scale": {"length_m": None, "time_s": None, "energy_j": None, "resolution": None, "label": "bounded scalar"},
            "uncertainty_semantics": "CSE declared prior policy and explicitly independent synthetic/user measurement; no calibration authentication",
            "equivalence_contract": "TASK_SPECIFIC", "preserved_queries": ["logical-source-object-identity"],
            "supported_interventions": [], "recovery_route": None, "provenance_refs": [], "notes": SCOPE}


def _semantics():
    semantic = builtin_semantic_registry(builtin_registry(bind=True))
    morphism = {"morphism_id": "interop.ifc-quantity-conditioning.v1", "kind": "TRANSFORM",
        "domain_representation_id": "interop.ifc-declared-source.v1", "codomain_representation_id": "interop.ifc-quantity-state.v1",
        "semantic_capability": None, "parameter_names": [], "preconditions": ["exact IFC bytes", "unambiguous source quantity", "explicit SI length units", "independent observation with exact bindings"],
        "validity": {"assumptions": [SCOPE], "operating_regime": ["bounded declared scalar quantity"], "failure_conditions": ["unsupported or missing required IFC source data"]},
        "preservation": {"queries": ["logical-source-object-identity"], "interventions": [], "invariants": ["logical source identity", "metre units", "declared frame label"], "approximation_tolerance": None},
        "loss": {"class": "TASK_SPECIFIC", "description": "Only one target scalar is projected; remaining IFC content retained as evidence", "metrics": {}},
        "uncertainty": {"behavior": "PROPAGATE", "method": "scalar independent-noise Gaussian conditioning"}, "reversibility": "NONE",
        "authority_requirements": ["external admission authority review"], "verification_requirements": ["independent source links and RAW conditioning check"], "provenance_refs": [], "notes": SCOPE}
    registry = registry_from_specs([_representation("interop.ifc-declared-source.v1", "TABLE"), _representation("interop.ifc-quantity-state.v1", "STATE")], [morphism], semantic)
    effects = []
    for property_id in ("identity.logical-source-object.v1", "quantity.metre-unit.v1", "frame.declared-label.v1"):
        effects.append({"property_id": property_id, "effect": "PRESERVE", "output_property_id": property_id, "transform_id": None, "bound": None, "notes": SCOPE})
    for property_id, transform in (("quantity.declared-mean.v1", "mapping.ifc-gaussian-conditioning.v1"), ("uncertainty.declared-variance.v1", "mapping.independent-noise-gaussian.v1")):
        effects.append({"property_id": property_id, "effect": "TRANSFORM", "output_property_id": property_id, "transform_id": transform, "bound": None, "notes": "Verified only under stated independent-noise and source-prior assumptions"})
    effects.append({"property_id": "representation.unprojected-ifc-details.v1", "effect": "FORGET", "output_property_id": None, "transform_id": None, "bound": None, "notes": "Not projected to target state; original complete bytes remain evidence"})
    contract = contract_from_spec(registry, semantic, {"contract_id": "interop.ifc-quantity-preservation.v1", "morphism_id": morphism["morphism_id"], "requires": ["mapping.ifc-applicability.v1"], "effects": effects, "notes": SCOPE})
    profile = profile_from_spec(registry, semantic, contract, {"profile_id": "interop.ifc-bounded-length-profile.v1", "source_family": "STANDARD", "standard_id": "standard.ifc.v1", "source_profile_id": "interop.ifc-declared-length-subset.v1", "source_system_id": "industrial.ifc-source.v1", "source_schema_id": "IFC4 STEP; bounded declared-length subset only, no whole-standard conformance certification", "morphism_id": morphism["morphism_id"], "mapping_id": "interop.cse-ifc-quantity.v1", "mapping_assumptions": [SCOPE, "prior sigma is declared model policy", "measurement noise independence is supplied"], "uncertainty_semantics": "declared Gaussian covariance; not authenticated metrology", "declared_loss_properties": ["representation.unprojected-ifc-details.v1"], "verification_requirements": ["source STEP links", "native execution bytes", "independent RAW Gaussian check"], "notes": SCOPE})
    return semantic, registry, contract, profile


def _project(native_state, spec, execution_id, evidence):
    row = next(i for i, q in enumerate(native_state["quantities"]) if all(q[key] == spec["target"][key] for key in spec["target"]))
    value, variance = native_state["mean"][row], native_state["covariance"][row][row]
    quantity = spec["target"]["quantity"]
    frame = spec["model_frame"] or "unresolved-declared-frame"
    covariance = create_covariance_artifact(matrix=[[variance]], quantity_ids=[quantity], units=["m"], frame=frame,
        reference_values=[value], method="native CSE imported/conditioned scalar covariance",
        basis={"kind": "estimated_state", "id": native_state["belief_digest"]},
        provenance={"provider": "cse", "source_evidence_ids": evidence, "source_covariance_ids": []},
        assumptions=["declared source prior sigma", "noise independence supplied; calibration authenticity not established"])
    return state(identity={"model_id": "interop.ifc-quantity-model.v1", "entity_id": spec["canonical_entity_id"], "execution_id": execution_id},
        clock={"id": "declared-model-reference-no-acquisition-time", "time_s": 0}, frame=frame,
        variables={quantity: {"value": value, "unit": "m"}}, uncertainty=covariance,
        provenance={"provider": "cse", "sources": evidence, "semantics": "estimated"})


def _unavailable_projection(spec, execution_id, evidence):
    return state(identity={"model_id": "interop.ifc-quantity-model.v1", "entity_id": spec["canonical_entity_id"], "execution_id": execution_id},
        clock={"id": "declared-model-reference-no-acquisition-time", "time_s": 0},
        frame=spec["model_frame"] or "unresolved-declared-frame",
        variables={spec["target"]["quantity"]: {"value": None, "unit": "m"}}, uncertainty=None,
        provenance={"provider": "ifc-quantity-projection-unavailable", "sources": evidence, "semantics": "reference"})


def _records(native, audit, spec, inspected, independent):
    semantic, registry, contract, profile = _semantics()
    source = workflow._source(base64.b64decode(native["source"]["evidence"][0]["bytes_b64"], validate=True))
    step = native["steps"][0]
    data = step["result"]["data"]
    receipt = seal({"schema": "ciw.ifc-independent-mapping-verification.v1", "verification_id": spec["run_id"] + ".independent.v1",
        "execution_ref": step["result_id"], "native_session_ref": native["bundle_digest"], "audit_ref": audit["record_digest"],
        "input_ref": data["ifc_sha256"], "observation_ref": data["observation_sha256"], "output_ref": step["transport_output"]["sha256"],
        "verifier_identity": _closure(), "source_inspection": inspected, "outcome": independent,
        "numerical_comparison_bound": {"relative_tolerance": 2e-10, "float64_ulp_allowance": 32, "absolute_variance_floor": None},
        "scope": SCOPE, "physical_validity_established": False, "derived_output_independently_verified": False,
        "dependency_binary_authentication": "not_established", "state_admission_performed": False})
    ingress = ingress_from_spec(profile, {"ingress_id": spec["run_id"] + ".ingress.v1", "payload_ref": data["ifc_sha256"], "payload_media_type": "application/x-step",
        "source_identity": {"reference_id": "industrial.ifc-object.v1", "namespace": "IFC GlobalId / exact whole-file occurrence", "external_id": spec["target"]["global_id"], "object_kind": "BIM_OBJECT"},
        "mapping_parameters": {"target": spec["target"], "declared_frame": spec["model_frame"], "source_provenance": spec["source_provenance"]},
        "mapping_evidence_refs": [receipt["record_digest"], audit["record_digest"]], "notes": "Declarative ingress retained beneath an actual pinned execution occurrence"})
    checks = [{"kind": kind, "status": "VERIFIED" if kind in {"PROFILE_CONFORMANCE", "SOURCE_IDENTITY"} else independent["mapping_status"],
               "method": "EVIDENCE_CROSSCHECK" if kind == "SOURCE_IDENTITY" else "MAPPING_TEST",
               "evidence_ref": receipt["record_digest"], "notes": "PROFILE_CONFORMANCE covers only this declared bounded subset; " + SCOPE}
              for kind in sorted(CHECK_KINDS)]
    verification = ingress_verification(profile, ingress, {"verification_id": spec["run_id"] + ".interop-verification.v1", "checks": checks, "notes": independent["reason"]})
    qualification = qualify_ingress(registry, semantic, contract, profile, ingress, verification)
    result = {"registry": registry, "preservation_contract": contract, "profile": profile, "ingress": ingress,
              "mapping_verification": receipt, "ingress_verification": verification, "qualification": qualification,
              "source_state": None, "candidate_state": None, "entity_binding": None, "identity_verification": None,
              "preservation_verification": None, "preservation_gate": None, "transition_envelope": None}
    evidence = [data["ifc_sha256"], data["observation_sha256"], receipt["record_digest"]]
    if data["prior"] is None or independent["target_row"] is None:
        before = _unavailable_projection(spec, None, evidence)
        after = _unavailable_projection(spec, step["execution_id"], evidence)
    else:
        before = _project(data["prior"], spec, None, evidence)
        after = _project(data["posterior"], spec, step["execution_id"], evidence)
    source_reference = {"reference_id": "industrial.ifc-object.v1", "system_id": "industrial.ifc-source.v1", "namespace": "IFC GlobalId / exact whole-file occurrence",
        "external_id": spec["target"]["global_id"], "object_kind": "BIM_OBJECT", "evidence_ref": receipt["record_digest"]}
    if qualification["status"] == "QUALIFIED":
        source_reference = identity_reference_from_qualification(qualification, registry, semantic, contract, profile, ingress, verification)
    binding = binding_from_spec({"binding_id": spec["run_id"] + ".binding.v1", "canonical_entity_id": spec["canonical_entity_id"],
        "references": [source_reference, {"reference_id": "industrial.cse-quantity.v1", "system_id": "industrial.cse-state.v1", "namespace": "CSE logical IFC target",
        "external_id": ":".join(spec["target"][key] for key in ("ifc_class", "global_id", "quantity")), "object_kind": "SIMULATION_VARIABLE", "evidence_ref": receipt["record_digest"]}], "notes": "Logical source-object continuity; no physical-asset equivalence or entity admission"})
    identity = identity_verification_from_spec(binding, {"verification_id": spec["run_id"] + ".identity-verification.v1",
        "checks": [{"reference_id": row["reference_id"], "status": "VERIFIED", "method": "EXACT_IDENTIFIER", "evidence_ref": receipt["record_digest"], "notes": SCOPE} for row in binding["references"]], "notes": SCOPE})
    obligations = [("REQUIRE", prop) for prop in contract["requires"]] + [(effect["effect"], effect["property_id"]) for effect in contract["effects"]]
    def preservation_check(kind, prop):
        status = independent["mapping_status"] if kind in {"REQUIRE", "TRANSFORM"} else "VERIFIED"
        method = "NUMERICAL_BOUND" if kind == "TRANSFORM" else "EXACT_ALGEBRA"
        evidence_ref = receipt["record_digest"]
        if prop == "frame.declared-label.v1" and spec["model_frame"] is None:
            status, method, evidence_ref = "UNRESOLVED", "NOT_PERFORMED", None
        return {"kind": kind, "property_id": prop, "status": status, "method": method, "evidence_ref": evidence_ref, "notes": SCOPE}
    preservation = preservation_verification(registry, semantic, contract, {"verification_id": spec["run_id"] + ".preservation-verification.v1", "source_state_ref": before["record_digest"], "candidate_state_ref": after["record_digest"],
        "checks": [preservation_check(kind, prop) for kind, prop in obligations], "notes": independent["reason"]})
    gate = admission_gate_from_spec(registry, semantic, contract, preservation, {"gate_id": spec["run_id"] + ".gate.v1", "forbidden_forgets": ["identity.logical-source-object.v1"], "notes": "Eligibility for authority review only"})
    envelope = transition_envelope_from_spec(before, after, binding, identity, registry, semantic, contract, preservation, gate,
        {"transition_id": spec["run_id"] + ".transition.v1", "proposer": {"kind": "SOLVER", "proposer_id": "cse", "execution_ref": step["result_id"], "notes": "Actual native conditioning occurrence"}, "required_admission_authority": spec["required_admission_authority"], "notes": SCOPE})
    result.update(source_state=before, candidate_state=after, entity_binding=binding, identity_verification=identity,
                  preservation_verification=preservation, preservation_gate=gate, transition_envelope=envelope)
    return result


def execute_ifc(ifc: bytes, observation: bytes, spec: dict, repositories: dict) -> dict:
    spec = _spec(spec, ifc)
    inspected = inspect_source(ifc, spec["target"])
    source = {"schema": "ciw.bim-quantity-source.v1", "experiment_id": spec["run_id"], "configuration": bim_quantity.POLICY,
              "ifc_bytes_b64": base64.b64encode(ifc).decode(), "observation_bytes_b64": base64.b64encode(observation).decode(),
              "target": spec["target"], "model_frame": spec["model_frame"]}
    raw = canonical(source)
    workflow._source(raw)
    bound = workflow._adapters(repositories)
    if bound[1]["source_tree"] != PROVIDER_TREE:
        raise ValueError("CSE source tree differs from approved revision tree")
    audit = _audit(ifc, bound)
    native = workflow._execute(raw, bound)
    independent = _independent(source, native["steps"][0]["result"]["data"], inspected)
    records = _records(native, audit, spec, inspected, independent)
    value = seal({"schema": SCHEMA, "spec": spec, "ifc_artifact": _blob(ifc), "observation_artifact": _blob(observation),
                  "native_session": native, "native_audit": audit, "records": records,
                  "claims": {"actual_mapping_execution_retained": True, "independent_mapping_check_performed": True,
                             "independent_raw_conditioning_verified": independent["mapping_status"] == "VERIFIED" and independent["verified_raw_posterior_entries"] > 0,
                             "full_ifc_standard_conformance_certified": False, "physical_asset_equivalence_established": False,
                             "canonical_state_mutated": False, "state_admission_performed": False}})
    verify_ifc(value)
    return value


def verify_ifc(value: dict, repositories: dict | None = None) -> dict:
    keys(value, {"schema", "record_digest", "spec", "ifc_artifact", "observation_artifact", "native_session", "native_audit", "records", "claims"})
    check_seal(value)
    if value["schema"] != SCHEMA or len(canonical(value)) > 4 * 1024 * 1024:
        raise ValueError("Wrong IFC transition schema or exceeded bundle budget")
    ifc = _unblob(value["ifc_artifact"], 65536)
    observation = _unblob(value["observation_artifact"], 4096)
    spec = _spec(value["spec"], ifc)
    native = value["native_session"]
    source = workflow._source(workflow._validate(native))
    if (bim_quantity._bytes(source["ifc_bytes_b64"], 65536) != ifc or bim_quantity._bytes(source["observation_bytes_b64"], 4096) != observation
            or source["target"] != spec["target"] or source["model_frame"] != spec["model_frame"] or source["experiment_id"] != spec["run_id"]):
        raise ValueError("IFC transition source/spec/exact-byte bindings differ")
    runtime = native["runtimes"]["cse"]
    if runtime["source_tree"] != PROVIDER_TREE:
        raise ValueError("CSE retained source tree differs from approved revision tree")
    if repositories is not None:
        workflow._adapters(repositories, native["runtimes"])
    inspected = inspect_source(ifc, spec["target"])
    _verify_audit(value["native_audit"], ifc, runtime, inspected)
    if native["steps"][0]["result"]["data"]["reason"] == "native_refusal":
        pipeline = value["native_audit"]["data"]["pipeline"]
        if pipeline["world_digest"] is not None or pipeline["pipeline_ready"]:
            raise ValueError("Native IFC refusal cannot claim an audit-ready compiled world")
    else:
        native_prior = native["steps"][0]["result"]["data"]["prior"]
        if value["native_audit"]["data"]["pipeline"]["world_digest"] != native_prior["world_digest"]:
            raise ValueError("Native IFC audit compiled world differs from actual imported prior")
    independent = _independent(source, native["steps"][0]["result"]["data"], inspected)
    # Recompute every generic record from evidence. Seals/status declarations
    # alone are insufficient, including when an attacker recomputes all seals.
    expected = _records(native, value["native_audit"], spec, inspected, independent)
    if canonical(value["records"]) != canonical(expected):
        raise ValueError("IFC identity/preservation/transition records differ from recomputed evidence")
    if value["claims"] != {"actual_mapping_execution_retained": True, "independent_mapping_check_performed": True,
                            "independent_raw_conditioning_verified": independent["mapping_status"] == "VERIFIED" and independent["verified_raw_posterior_entries"] > 0,
                            "full_ifc_standard_conformance_certified": False, "physical_asset_equivalence_established": False,
                            "canonical_state_mutated": False, "state_admission_performed": False}:
        raise ValueError("IFC transition claims exceed bounded review authority")
    envelope = expected["transition_envelope"]
    return {"schema": "ciw.ifc-transition-verification-summary.v1", "run_ref": value["record_digest"],
            "source_kind": spec["source_provenance"]["kind"], "input_ref": byte_digest(ifc),
            "native_status": native["steps"][0]["result"]["data"]["status"], "reason": independent["reason"],
            "qualification": expected["qualification"]["status"], "transition_readiness": None if envelope is None else envelope["readiness"],
            "independent_verification_scope": SCOPE, "verified_raw_posterior_entries": independent["verified_raw_posterior_entries"],
            "current_runtime_checked": repositories is not None, "standard_conformance_certified": False,
            "physical_validity_established": False, "state_admission_performed": False, "canonical_state_mutated": False}
