"""Content-bound scientific signatures over the existing System Board compiler.

Signatures describe whole operations, not runtime payload validation. They do
not discharge textual preconditions or select/execute an implementation.
"""
from __future__ import annotations

from .control_contracts import detached, keys, record, text
from .operations.runner import check_seal
from .representation_morphisms import validate_registry
from .semantic_capabilities import SemanticRegistry
from .system_board import compile_board, validate_board


def bind_board(board: dict, registry: dict, semantic: SemanticRegistry, spec: dict) -> dict:
    """Bind every operation to one scientific morphism, without execution."""
    board = validate_board(board)
    registry = validate_registry(registry, semantic)
    keys(spec, {"binding_id", "node_morphisms"})
    assignments = spec["node_morphisms"]
    operations = {n["node_id"]: n for n in board["nodes"] if n["kind"] == "OPERATION"}
    if not operations or type(assignments) is not dict or set(assignments) != set(operations):
        raise ValueError("Binding must cover every and only Board OPERATION node")
    bound = {}
    for node_id, node in operations.items():
        morphism_id = text(assignments[node_id])
        if morphism_id not in registry["morphisms"]:
            raise ValueError("Binding references an unknown scientific morphism")
        morphism = registry["morphisms"][morphism_id]
        if morphism["semantic_capability"] != node["semantic_capability"]:
            raise ValueError("Board and scientific morphism semantic capabilities differ")
        if not set(node["parameters"]) <= set(morphism["parameter_names"]):
            raise ValueError("Board parameter is not declared by the scientific morphism")
        if len(node["sockets"]["inputs"]) > 1 or len(node["sockets"]["outputs"]) != 1:
            raise ValueError("V1 binds single-output operations with at most one input socket")
        domain = registry["representations"][morphism["domain_representation_id"]]
        codomain = registry["representations"][morphism["codomain_representation_id"]]
        bound[node_id] = {
            "morphism_id": morphism_id, "morphism_ref": morphism["record_digest"],
            "domain_representation_id": domain["representation_id"],
            "domain_representation_ref": domain["record_digest"],
            "codomain_representation_id": codomain["representation_id"],
            "codomain_representation_ref": codomain["record_digest"],
            "parameter_values": {k: v["value"] for k, v in node["parameters"].items()},
        }
    checked_edges = []
    for edge in board["edges"]:
        if edge["kind"] != "DATAFLOW":
            continue
        source = bound.get(edge["source_node_id"])
        target = bound.get(edge["target_node_id"])
        if source is None or target is None:
            raise ValueError("Bound DATAFLOW must connect OPERATION nodes")
        if source["codomain_representation_ref"] != target["domain_representation_ref"]:
            raise ValueError("DATAFLOW scientific codomain/domain mismatch; declare an explicit transform")
        checked_edges.append(edge["edge_id"])
    return record(
        "board-morphism-binding", binding_id=text(spec["binding_id"]),
        board_ref=board["record_digest"], registry_ref=registry["record_digest"],
        node_morphisms=detached(assignments), bound_nodes=bound,
        checked_dataflow_edges=checked_edges,
        claims={"complete_operation_signature_binding": True,
                "scientific_payload_validated": False, "preconditions_discharged": False,
                "provider_execution": False, "engine_selected": False,
                "canonical_state_mutated": False, "execution_authority": False},
    )


def validate_binding(value: dict, board: dict, registry: dict, semantic: SemanticRegistry) -> dict:
    """Recompute the entire binding; a fresh seal cannot conceal stale metadata."""
    keys(value, {"schema", "record_digest", "binding_id", "board_ref", "registry_ref",
                 "node_morphisms", "bound_nodes", "checked_dataflow_edges", "claims"})
    check_seal(value)
    expected = bind_board(board, registry, semantic, {
        "binding_id": value["binding_id"], "node_morphisms": value["node_morphisms"],
    })
    if value != expected:
        raise ValueError("Binding does not match the exact Board, registry and derived signatures")
    return detached(value)


def compile_bound_board(board: dict, binding: dict, registry: dict, semantic: SemanticRegistry) -> dict:
    """Preserve the existing Board -> semantic graph -> experiment lowering."""
    binding = validate_binding(binding, board, registry, semantic)
    compilation = compile_board(board, semantic)
    return record(
        "board-morphism-compilation", board_ref=board["record_digest"],
        binding_ref=binding["record_digest"], registry_ref=registry["record_digest"],
        board_compilation=compilation,
        claims={"uses_existing_board_compiler": True, "provider_execution": False,
                "scientific_payload_validated": False, "preconditions_discharged": False,
                "canonical_state_mutated": False, "execution_authority": False},
    )


def validate_bound_compilation(value: dict, board: dict, binding: dict,
                               registry: dict, semantic: SemanticRegistry) -> dict:
    keys(value, {"schema", "record_digest", "board_ref", "binding_ref", "registry_ref",
                 "board_compilation", "claims"})
    check_seal(value)
    if value != compile_bound_board(board, binding, registry, semantic):
        raise ValueError("Bound compilation differs from recomputed lowering")
    return detached(value)
