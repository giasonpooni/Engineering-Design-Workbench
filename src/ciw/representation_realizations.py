"""Evidence projections for declared scientific representations.

Realization means an exact retained source/result satisfies the declared
representation boundary used by this workbench. It is deliberately distinct
from empirical physical validation, morphism-law proof, intervention authority,
canonical-state admission, and provider execution.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .control_checks import inspect_record
from .control_contracts import detached, keys, record, text
from .core.identities import content_identity, validate_evidence_identity
from .instruments import validate_run
from .operations.runner import check_seal, validate_execution
from .operations.schemas import validate_payload, validate_role
from .representation_morphisms import (
    validate_registry,
    validate_witness,
    witness_from_spec,
)
from .semantic_capabilities import SemanticRegistry
from .system_board import compile_board, validate_board
from .visual_representation_gate import validate_binding as validate_intervention_binding

SUBJECTS = {"SOURCE_CHANNEL", "OPERATION_RESULT"}
REALIZATION_CLAIMS = {
    "contract_realization_established": True,
    "empirical_physical_validity_established": False,
    "general_morphism_law_proved": False,
    "canonical_state_admitted": False,
    "provider_execution_performed_by_realization": False,
    "execution_authority": False,
}
PROJECTION_CLAIMS = {
    "read_only_evidence_projection": True,
    "realization_not_verification": True,
    "witness_not_general_proof": True,
    "intervention_authority_unchanged": True,
    "provider_execution": False,
    "canonical_state_mutated": False,
    "state_admission": False,
    "execution_authority": False,
}


def _interval(source: dict, value: Any) -> list[float]:
    if (type(value) is not list or len(value) != 2
            or any(type(v) not in (int, float) or isinstance(v, bool) for v in value)):
        raise ValueError("Realization interval must be [start, end]")
    start, end = float(value[0]), float(value[1])
    duration = float(source["metadata"]["duration_s"])
    if not 0 <= start < end <= duration:
        raise ValueError("Realization interval is outside retained evidence")
    if not any(start <= t < end for t in source["time_s"]):
        raise ValueError("Realization interval contains no retained samples")
    return [start, end]


def source_channel_realization(source: dict, registry: dict, semantic: SemanticRegistry,
                               spec: dict) -> dict:
    """Bind exact retained source-channel content to a declared source representation."""
    validate_run(source)
    validate_evidence_identity(source)
    registry = validate_registry(registry, semantic)
    keys(spec, {"realization_id", "representation_id", "channel", "interval_s", "notes"})
    rep_id = text(spec["representation_id"])
    if rep_id not in registry["representations"]:
        raise ValueError("Realization references an unknown representation")
    rep = registry["representations"][rep_id]
    if rep["schema_id"] != "ciw.run-channel.v1":
        raise ValueError("Source-channel realization requires ciw.run-channel.v1")
    channel = text(spec["channel"])
    if channel not in source["channels"]:
        raise ValueError("Realization channel is absent from retained evidence")
    interval = _interval(source, spec["interval_s"])
    selected = [
        (float(t), source["channels"][channel]["values"][i])
        for i, t in enumerate(source["time_s"]) if interval[0] <= t < interval[1]
    ]
    content_ref = content_identity({
        "source_evidence_id": source["evidence_id"],
        "channel": channel,
        "interval_s": interval,
        "unit": source["channels"][channel]["unit"],
        "samples": selected,
    })
    notes = spec["notes"]
    if type(notes) is not str or len(notes) > 4096:
        raise ValueError("Realization notes must be bounded text")
    return record(
        "representation-realization",
        realization_id=text(spec["realization_id"]),
        registry_ref=registry["record_digest"],
        representation_id=rep_id,
        representation_ref=rep["record_digest"],
        subject_kind="SOURCE_CHANNEL",
        source_evidence_ref=source["evidence_id"],
        execution_ref=None,
        result_ref=None,
        morphism_id=None,
        morphism_ref=None,
        realized_content_ref=content_ref,
        channel=channel,
        interval_s=interval,
        observed={
            "unit": source["channels"][channel]["unit"],
            "coordinate_frame": source["metadata"]["coordinate_frame"],
            "sample_count": len(selected),
            "sample_rate_hz": source["metadata"]["sample_rate_hz"],
            "source_provenance": deepcopy(source["metadata"]["provenance"]),
        },
        record_verification={"status": "not_applicable", "verification_id": None},
        uncertainty={
            "representation": rep["uncertainty_semantics"],
            "morphism": None,
        },
        notes=notes,
        claims=REALIZATION_CLAIMS,
    )


def operation_result_realization(source: dict, execution: dict, result: dict,
                                 registry: dict, semantic: SemanticRegistry,
                                 spec: dict) -> dict:
    """Bind a validated retained operation result to a morphism codomain representation."""
    validate_run(source)
    validate_evidence_identity(source)
    registry = validate_registry(registry, semantic)
    keys(spec, {"realization_id", "morphism_id", "notes"})
    morphism_id = text(spec["morphism_id"])
    morphism = registry["morphisms"].get(morphism_id)
    if morphism is None:
        raise ValueError("Result realization references an unknown morphism")
    if morphism["semantic_capability"] is None:
        raise ValueError("Result realization requires an executable semantic capability")
    check_seal(execution)
    check_seal(result)
    validate_execution(execution, source, execution["selection_revision"],
                       {result["result_id"]: result})
    if result.get("schema") != "ciw.operation-result.v1":
        raise ValueError("Result realization requires ciw.operation-result.v1")
    if result["evidence_id"] != source["evidence_id"]:
        raise ValueError("Result realization source evidence mismatch")
    validate_role(result["operation_id"], result["role"])
    validate_payload(
        result["operation_id"], result["data"], source, result["parameters"],
        {"channel": result["channel"], "interval_s": result["interval_s"]},
    )
    resolution = semantic.resolve(morphism["semantic_capability"])
    if result["operation_id"] != resolution["operation_id"]:
        raise ValueError("Retained result operation differs from morphism semantic lowering")
    rep = registry["representations"][morphism["codomain_representation_id"]]
    notes = spec["notes"]
    if type(notes) is not str or len(notes) > 4096:
        raise ValueError("Realization notes must be bounded text")
    data = result["data"]
    return record(
        "representation-realization",
        realization_id=text(spec["realization_id"]),
        registry_ref=registry["record_digest"],
        representation_id=rep["representation_id"],
        representation_ref=rep["record_digest"],
        subject_kind="OPERATION_RESULT",
        source_evidence_ref=source["evidence_id"],
        execution_ref=content_identity(execution),
        result_ref=content_identity(result),
        morphism_id=morphism_id,
        morphism_ref=morphism["record_digest"],
        realized_content_ref=content_identity(data),
        channel=result["channel"],
        interval_s=deepcopy(result["interval_s"]),
        observed={
            "unit": data.get("unit"),
            "coordinate_frame": source["metadata"]["coordinate_frame"],
            "sample_count": data.get("sample_count"),
            "runtime": deepcopy(result["runtime"]),
            "operation_id": result["operation_id"],
        },
        record_verification={
            "status": result["verification_status"],
            "verification_id": result["verification_id"],
        },
        uncertainty={
            "representation": rep["uncertainty_semantics"],
            "morphism": deepcopy(morphism["uncertainty"]),
        },
        notes=notes,
        claims=REALIZATION_CLAIMS,
    )


def validate_realization(value: dict, source: dict, registry: dict,
                         semantic: SemanticRegistry, *, execution: dict | None = None,
                         result: dict | None = None) -> dict:
    keys(value, {
        "schema", "record_digest", "realization_id", "registry_ref",
        "representation_id", "representation_ref", "subject_kind",
        "source_evidence_ref", "execution_ref", "result_ref", "morphism_id",
        "morphism_ref", "realized_content_ref", "channel", "interval_s",
        "observed", "record_verification", "uncertainty", "notes", "claims",
    })
    if value["schema"] != "ciw.representation-realization.v1":
        raise ValueError("Wrong representation-realization schema")
    check_seal(value)
    if value["subject_kind"] == "SOURCE_CHANNEL":
        expected = source_channel_realization(source, registry, semantic, {
            "realization_id": value["realization_id"],
            "representation_id": value["representation_id"],
            "channel": value["channel"],
            "interval_s": value["interval_s"],
            "notes": value["notes"],
        })
    elif value["subject_kind"] == "OPERATION_RESULT":
        if execution is None or result is None:
            raise ValueError("Operation-result realization validation requires retained execution/result")
        expected = operation_result_realization(source, execution, result, registry, semantic, {
            "realization_id": value["realization_id"],
            "morphism_id": value["morphism_id"],
            "notes": value["notes"],
        })
    else:
        raise ValueError("Unknown representation realization subject")
    if value != expected:
        raise ValueError("Representation realization differs from exact retained content")
    return detached(value)


def finite_result_witness(source_realization: dict, result_realization: dict,
                          source: dict, execution: dict, result: dict,
                          registry: dict, semantic: SemanticRegistry,
                          witness_id: str) -> dict:
    """Create a bounded finite witness; preservation/physical validity remain unresolved."""
    source_realization = validate_realization(
        source_realization, source, registry, semantic)
    result_realization = validate_realization(
        result_realization, source, registry, semantic,
        execution=execution, result=result)
    morphism_id = result_realization["morphism_id"]
    morphism = registry["morphisms"][morphism_id]
    if source_realization["representation_id"] != morphism["domain_representation_id"]:
        raise ValueError("Witness domain realization does not match morphism domain")
    if result_realization["representation_id"] != morphism["codomain_representation_id"]:
        raise ValueError("Witness result realization does not match morphism codomain")
    return witness_from_spec(registry, semantic, {
        "witness_id": text(witness_id),
        "morphism_id": morphism_id,
        "source_evidence_id": source["evidence_id"],
        "execution_ref": content_identity(execution),
        "result_ref": content_identity(result),
        "checks": [
            {"check_id": "domain-realized", "kind": "DOMAIN", "status": "PASS",
             "evidence_ref": source_realization["record_digest"],
             "notes": "Exact retained source content satisfies the declared domain realization boundary."},
            {"check_id": "source-retained", "kind": "PROVENANCE", "status": "PASS",
             "evidence_ref": source["evidence_id"],
             "notes": "Exact source evidence identity is retained."},
            {"check_id": "execution-bound", "kind": "EXECUTION", "status": "PASS",
             "evidence_ref": content_identity(execution),
             "notes": "Retained completed execution validates against the exact source/result."},
            {"check_id": "codomain-realized", "kind": "CODOMAIN", "status": "PASS",
             "evidence_ref": result_realization["record_digest"],
             "notes": "Validated result payload realizes the declared morphism codomain boundary."},
            {"check_id": "general-preservation", "kind": "PRESERVATION", "status": "UNRESOLVED",
             "evidence_ref": None,
             "notes": "Schema/result realization does not prove all declared preservation obligations."},
            {"check_id": "physical-validity", "kind": "VALIDITY", "status": "UNRESOLVED",
             "evidence_ref": None,
             "notes": "Finite synthetic execution is not empirical physical validation."},
        ],
        "notes": "Finite retained execution witness only; no general morphism theorem.",
    })


def _summary(witness: dict | None) -> dict:
    if witness is None:
        return {"status": "NO_WITNESS", "PASS": 0, "FAIL": 0, "UNRESOLVED": 0,
                "physical_validity_established": False}
    counts = {name: sum(c["status"] == name for c in witness["checks"])
              for name in ("PASS", "FAIL", "UNRESOLVED")}
    if counts["FAIL"]:
        status = "FINITE_WITNESS_FAIL"
    elif counts["UNRESOLVED"]:
        status = "FINITE_WITNESS_WITH_UNRESOLVED"
    else:
        status = "FINITE_WITNESS_ALL_DECLARED_CHECKS_PASS"
    return {**counts, "status": status,
            "physical_validity_established": witness["claims"]["physical_validity_established"]}


def board_evidence_projection(board: dict, baseline: dict, source: dict,
                              registry: dict, intervention_binding: dict,
                              semantic: SemanticRegistry) -> dict:
    """Project exact retained evidence onto bound Board nodes without changing authority."""
    board = validate_board(board)
    registry = validate_registry(registry, semantic)
    binding = validate_intervention_binding(
        intervention_binding, board, registry, semantic)
    validate_run(source)
    validate_evidence_identity(source)
    inspect_record(baseline)
    if baseline.get("schema") != "ciw.graph-run.v1" or baseline.get("status") != "completed":
        raise ValueError("Evidence projection requires a completed retained graph-run")
    if baseline["source_evidence_id"] != source["evidence_id"]:
        raise ValueError("Evidence projection baseline/source mismatch")
    compilation = compile_board(board, semantic)
    if baseline["experiment"] != compilation["semantic_compilation"]["experiment"]:
        raise ValueError("Evidence projection baseline differs from exact Board compilation")

    projected = {}
    for node_id, bound in binding["nodes"].items():
        payload = baseline["nodes"].get(node_id)
        if payload is None or payload.get("status") != "completed":
            raise ValueError("Evidence projection requires completed bound operation nodes")
        execution, result = payload["execution"], payload["result"]
        current = registry["representations"][bound["representation_id"]]
        source_realization = source_channel_realization(source, registry, semantic, {
            "realization_id": f"{node_id}-source-{result['channel']}",
            "representation_id": (
                bound["representation_id"]
                if current["schema_id"] == "ciw.run-channel.v1"
                else registry["morphisms"][bound["projection_morphism_id"]]["domain_representation_id"]
            ),
            "channel": result["channel"],
            "interval_s": result["interval_s"],
            "notes": "Derived read-only realization for Board evidence inspection.",
        })
        result_realization = None
        witness = None
        current_realization = source_realization
        if bound["projection_morphism_id"] is not None:
            result_realization = operation_result_realization(
                source, execution, result, registry, semantic, {
                    "realization_id": f"{node_id}-result",
                    "morphism_id": bound["projection_morphism_id"],
                    "notes": "Validated retained result realizes the declared codomain boundary.",
                })
            if result_realization["representation_id"] != bound["representation_id"]:
                raise ValueError("Bound current representation differs from realized result codomain")
            current_realization = result_realization
            witness = finite_result_witness(
                source_realization, result_realization, source, execution, result,
                registry, semantic, f"{node_id}-finite-morphism-witness")
            validate_witness(witness, registry)

        projected[node_id] = {
            "representation_id": current["representation_id"],
            "representation_ref": current["record_digest"],
            "current_realization": current_realization,
            "source_realization": source_realization,
            "result_realization": result_realization,
            "morphism_witness": witness,
            "witness_summary": _summary(witness),
            "record_verification": deepcopy(current_realization["record_verification"]),
            "uncertainty": {
                "representation": current["uncertainty_semantics"],
                "morphism": (
                    deepcopy(registry["morphisms"][bound["projection_morphism_id"]]["uncertainty"])
                    if bound["projection_morphism_id"] is not None else None
                ),
            },
            "provenance": {
                "source_evidence_ref": source["evidence_id"],
                "source_metadata": deepcopy(source["metadata"]["provenance"]),
                "representation_refs": deepcopy(current["provenance_refs"]),
                "morphism_refs": (
                    deepcopy(registry["morphisms"][bound["projection_morphism_id"]]["provenance_refs"])
                    if bound["projection_morphism_id"] is not None else []
                ),
            },
            "physical_validity": "NOT_ESTABLISHED",
        }

    return record(
        "board-evidence-projection",
        board_ref=board["record_digest"],
        baseline_ref=baseline["record_digest"],
        source_evidence_ref=source["evidence_id"],
        registry_ref=registry["record_digest"],
        intervention_binding_ref=binding["record_digest"],
        nodes=projected,
        claims=PROJECTION_CLAIMS,
    )


def validate_board_evidence_projection(value: dict, board: dict, baseline: dict,
                                       source: dict, registry: dict,
                                       intervention_binding: dict,
                                       semantic: SemanticRegistry) -> dict:
    keys(value, {
        "schema", "record_digest", "board_ref", "baseline_ref",
        "source_evidence_ref", "registry_ref", "intervention_binding_ref",
        "nodes", "claims",
    })
    if value["schema"] != "ciw.board-evidence-projection.v1":
        raise ValueError("Wrong Board evidence-projection schema")
    check_seal(value)
    expected = board_evidence_projection(
        board, baseline, source, registry, intervention_binding, semantic)
    if value != expected:
        raise ValueError("Board evidence projection differs from exact retained evidence recomputation")
    return detached(value)
