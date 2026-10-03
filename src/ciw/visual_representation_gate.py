"""Scientific intervention bindings for the Visual System Board.

The browser never infers representation semantics from labels. This module binds
every exposed Board operation parameter to one exact representation/intervention
contract in the existing morphism registry, then delegates LOCAL / EXPAND /
REFUSE decisions to the existing representation-aware Needle gate.
"""
from __future__ import annotations

from copy import deepcopy

from .control_contracts import content_ref, detached, keys, record, text
from .operations.runner import check_seal
from .representation_interventions import gate_from_spec
from .representation_morphisms import registry_from_specs, validate_registry
from .semantic_capabilities import SemanticRegistry
from .system_board import validate_board
from .visual_board import apply_parameter_edit

BINDING_CLAIMS = {
    "complete_exposed_parameter_gate_binding": True,
    "representation_contract_reused": True,
    "browser_inference": False,
    "provider_execution": False,
    "canonical_state_mutated": False,
    "state_admission": False,
    "execution_authority": False,
}


def _exposed_coordinates(board: dict) -> set[tuple[str, str]]:
    return {
        (node["node_id"], name)
        for node in board["nodes"]
        if node["kind"] == "OPERATION"
        for name, parameter in node["parameters"].items()
        if parameter["exposed"]
    }


def binding_from_spec(board: dict, registry: dict, semantic: SemanticRegistry, spec: dict) -> dict:
    """Bind every exposed Board coordinate to explicit representation semantics."""
    board = validate_board(board)
    registry = validate_registry(registry, semantic)
    keys(spec, {"binding_id", "nodes"})
    nodes = spec["nodes"]
    if type(nodes) is not dict:
        raise ValueError("Visual intervention binding nodes must be an object")

    board_nodes = {node["node_id"]: node for node in board["nodes"]}
    bound = {}
    coordinates = set()
    for node_id, row in nodes.items():
        node_id = text(node_id)
        node = board_nodes.get(node_id)
        if node is None or node["kind"] != "OPERATION":
            raise ValueError("Intervention binding targets an existing OPERATION node")
        keys(row, {
            "representation_id", "parameters", "recovery_representation_id",
            "projection_morphism_id",
        })
        representation_id = text(row["representation_id"])
        if representation_id not in registry["representations"]:
            raise ValueError("Intervention binding references an unknown representation")
        current = registry["representations"][representation_id]

        parameters = row["parameters"]
        if type(parameters) is not dict or not parameters:
            raise ValueError("Intervention binding requires at least one parameter coordinate")
        parameter_bindings = {}
        for parameter, intervention_id in parameters.items():
            parameter = text(parameter)
            intervention_id = text(intervention_id)
            if parameter not in node["parameters"] or not node["parameters"][parameter]["exposed"]:
                raise ValueError("Intervention binding parameter is not an exposed Board coordinate")
            coordinate = (node_id, parameter)
            if coordinate in coordinates:
                raise ValueError("Duplicate visual intervention coordinate")
            coordinates.add(coordinate)
            parameter_bindings[parameter] = intervention_id

        recovery_id = row["recovery_representation_id"]
        if recovery_id is not None:
            recovery_id = text(recovery_id)
            if recovery_id not in registry["representations"]:
                raise ValueError("Recovery binding references an unknown representation")
            recovery = registry["representations"][recovery_id]
            for intervention_id in parameter_bindings.values():
                if (intervention_id not in current["supported_interventions"]
                        and intervention_id not in recovery["supported_interventions"]):
                    raise ValueError("Recovery representation does not support a bound intervention")

        morphism_id = row["projection_morphism_id"]
        morphism_ref = None
        if morphism_id is not None:
            morphism_id = text(morphism_id)
            morphism = registry["morphisms"].get(morphism_id)
            if morphism is None:
                raise ValueError("Projection binding references an unknown scientific morphism")
            if morphism["codomain_representation_id"] != representation_id:
                raise ValueError("Projection morphism codomain is not the bound current representation")
            if morphism["semantic_capability"] != node["semantic_capability"]:
                raise ValueError("Projection morphism capability differs from the Board operation")
            if not set(parameter_bindings) <= set(morphism["parameter_names"]):
                raise ValueError("Bound parameter is not declared by the projection morphism")
            morphism_ref = morphism["record_digest"]

        bound[node_id] = {
            "representation_id": representation_id,
            "representation_ref": current["record_digest"],
            "parameters": parameter_bindings,
            "recovery_representation_id": recovery_id,
            "recovery_representation_ref": (
                registry["representations"][recovery_id]["record_digest"]
                if recovery_id is not None else None
            ),
            "projection_morphism_id": morphism_id,
            "projection_morphism_ref": morphism_ref,
        }

    expected = _exposed_coordinates(board)
    if coordinates != expected:
        missing = sorted(expected - coordinates)
        extra = sorted(coordinates - expected)
        raise ValueError(f"Binding must cover every exposed operation parameter; missing={missing}, extra={extra}")

    return record(
        "board-intervention-binding",
        binding_id=text(spec["binding_id"]),
        board_ref=board["record_digest"],
        registry_ref=registry["record_digest"],
        nodes=bound,
        claims=BINDING_CLAIMS,
    )


def validate_binding(value: dict, board: dict, registry: dict,
                     semantic: SemanticRegistry) -> dict:
    keys(value, {
        "schema", "record_digest", "binding_id", "board_ref",
        "registry_ref", "nodes", "claims",
    })
    if value["schema"] != "ciw.board-intervention-binding.v1":
        raise ValueError("Wrong Board intervention-binding schema")
    check_seal(value)
    spec = {
        "binding_id": value["binding_id"],
        "nodes": {
            node_id: {
                "representation_id": row["representation_id"],
                "parameters": row["parameters"],
                "recovery_representation_id": row["recovery_representation_id"],
                "projection_morphism_id": row["projection_morphism_id"],
            }
            for node_id, row in value["nodes"].items()
        },
    }
    expected = binding_from_spec(board, registry, semantic, spec)
    if value != expected:
        raise ValueError("Board intervention binding differs from exact recomputation")
    return detached(value)


def context_for_request(board: dict, registry: dict, binding: dict,
                        semantic: SemanticRegistry, request: dict) -> dict:
    """Return inspectable scientific context for one already-declared coordinate."""
    binding = validate_binding(binding, board, registry, semantic)
    preview = apply_parameter_edit(board, request, semantic)
    node_id, parameter = request["node_id"], request["parameter"]
    row = binding["nodes"].get(node_id)
    if row is None or parameter not in row["parameters"]:
        raise ValueError("Edit coordinate has no scientific intervention binding")
    current = registry["representations"][row["representation_id"]]
    recovery = (registry["representations"][row["recovery_representation_id"]]
                if row["recovery_representation_id"] is not None else None)
    morphism = (registry["morphisms"][row["projection_morphism_id"]]
                if row["projection_morphism_id"] is not None else None)
    return {
        "binding_ref": binding["record_digest"],
        "registry_ref": registry["record_digest"],
        "preview_ref": preview["record_digest"],
        "node_id": node_id,
        "parameter": parameter,
        "intervention_id": row["parameters"][parameter],
        "current_representation": deepcopy(current),
        "recovery_representation": deepcopy(recovery),
        "projection_morphism": deepcopy(morphism),
        "claims": {
            "inspectable_context_only": True,
            "provider_execution": False,
            "execution_authority": False,
        },
    }


def gate_for_request(board: dict, registry: dict, binding: dict,
                     semantic: SemanticRegistry, request: dict,
                     *, recovery_evidence_ref: str | None = None) -> dict:
    """Delegate the exact visual coordinate to the existing intervention gate."""
    context = context_for_request(board, registry, binding, semantic, request)
    current = context["current_representation"]
    recovery = context["recovery_representation"]
    intervention_id = context["intervention_id"]
    if recovery_evidence_ref is not None:
        recovery_evidence_ref = content_ref(recovery_evidence_ref)
        if intervention_id in current["supported_interventions"]:
            raise ValueError("LOCAL coordinate must not request representation expansion")
        if recovery is None:
            raise ValueError("No richer recovery representation is bound to this coordinate")
        recovery_id = recovery["representation_id"]
    else:
        recovery_id = None
    return gate_from_spec(registry, semantic, {
        "gate_id": "visual-" + request["node_id"] + "-" + request["parameter"],
        "representation_id": current["representation_id"],
        "intervention_id": intervention_id,
        "needle_target": {
            "node_id": request["node_id"],
            "parameter": request["parameter"],
        },
        "recovery_representation_id": recovery_id,
        "recovery_evidence_ref": recovery_evidence_ref,
        "notes": "Derived from exact Board intervention binding; visual action grants no authority.",
    })


def demo_registry(semantic: SemanticRegistry) -> dict:
    """Scientific registry for the synthetic oscillator Visual Board specimen."""
    scale = lambda label: {
        "length_m": None, "time_s": None, "energy_j": None,
        "resolution": None, "label": label,
    }
    representations = [
        {
            "representation_id": "signal.timeseries.uniform-scalar.v1",
            "role": "SIGNAL",
            "source_state_type": "retained-recording-channel",
            "schema_id": "ciw.run-channel.v1",
            "quantity_semantics": "uniform sampled scalar signal",
            "unit_semantics": "source-channel-unit",
            "frame_semantics": "source-recording-coordinate-frame",
            "time_semantics": "retained source sample clock",
            "scale": scale("source-time-series"),
            "uncertainty_semantics": "source-declared-or-none",
            "equivalence_contract": "EXACT",
            "preserved_queries": ["retained-sample-values"],
            "supported_interventions": ["select-channel-and-half-open-interval"],
            "recovery_route": "retained source recording",
            "provenance_refs": [],
            "notes": "Synthetic oscillator retained-source representation.",
        },
        {
            "representation_id": "signal.periodogram.one-sided-density.v1",
            "role": "SPECTRAL",
            "source_state_type": "derived-spectral-result",
            "schema_id": "ciw.periodogram-data.v1",
            "quantity_semantics": "one-sided power spectral density",
            "unit_semantics": "(source-channel-unit)^2/Hz",
            "frame_semantics": "frequency axis from source sample rate",
            "time_semantics": "selected source interval summary",
            "scale": scale("frequency-domain"),
            "uncertainty_semantics": "no uncertainty model declared",
            "equivalence_contract": "TASK_SPECIFIC",
            "preserved_queries": ["frequency-grid", "peak-frequency"],
            "supported_interventions": [],
            "recovery_route": "retained source recording",
            "provenance_refs": [],
            "notes": "Lossy spectral representation; not sufficient for time-domain intervention.",
        },
    ]
    morphisms = [{
        "morphism_id": "signal.periodogram.transform.v1",
        "kind": "TRANSFORM",
        "domain_representation_id": "signal.timeseries.uniform-scalar.v1",
        "codomain_representation_id": "signal.periodogram.one-sided-density.v1",
        "semantic_capability": "analysis.spectrum.v1",
        "parameter_names": ["channel", "interval_s"],
        "preconditions": ["retained source recording validates"],
        "validity": {
            "assumptions": ["periodic Hann window"],
            "operating_regime": ["finite source signal"],
            "failure_conditions": ["fewer than four samples"],
        },
        "preservation": {
            "queries": ["frequency-grid", "peak-frequency"],
            "interventions": [],
            "invariants": ["source evidence identity retained"],
            "approximation_tolerance": None,
        },
        "loss": {
            "class": "LOSSY",
            "description": "Phase and time-local source ordering are not retained.",
            "metrics": {"phase_retained": False},
        },
        "uncertainty": {"behavior": "UNKNOWN", "method": None},
        "reversibility": "NONE",
        "authority_requirements": ["read:recording"],
        "verification_requirements": ["source evidence retained"],
        "provenance_refs": [],
        "notes": "Finite provider executions are witnesses only.",
    }]
    return registry_from_specs(representations, morphisms, semantic)


def demo_binding(board: dict, registry: dict, semantic: SemanticRegistry) -> dict:
    """Complete exposed-coordinate binding for demo_board()."""
    return binding_from_spec(board, registry, semantic, {
        "binding_id": "visual-oscillator-interventions",
        "nodes": {
            "statistics": {
                "representation_id": "signal.timeseries.uniform-scalar.v1",
                "parameters": {"channel": "select-channel-and-half-open-interval"},
                "recovery_representation_id": None,
                "projection_morphism_id": None,
            },
            "spectrum": {
                "representation_id": "signal.periodogram.one-sided-density.v1",
                "parameters": {"channel": "select-channel-and-half-open-interval"},
                "recovery_representation_id": "signal.timeseries.uniform-scalar.v1",
                "projection_morphism_id": "signal.periodogram.transform.v1",
            },
            "energy_statistics": {
                "representation_id": "signal.timeseries.uniform-scalar.v1",
                "parameters": {"channel": "select-channel-and-half-open-interval"},
                "recovery_representation_id": None,
                "projection_morphism_id": None,
            },
        },
    })
