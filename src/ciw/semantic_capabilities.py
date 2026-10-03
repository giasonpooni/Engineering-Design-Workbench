"""Stable semantic capabilities over replaceable concrete NET operations.

Concrete categorical interpretation:
- Port/object specifications are objects.
- Semantic capabilities are morphisms between typed objects.
- Engine bindings are functor-like lowerings into the concrete operation category.
- Cross-engine comparisons are retained finite witnesses, not proofs of naturality.

This module never creates another scheduler, Session, evidence store, numerical
implementation, or plugin loader. It compiles into the existing ciw.experiment.v1.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import re
from typing import Any

from .agent_tools import _shape, tool
from .control_contracts import detached, keys, text
from .control_plane import CapabilityRegistry, Port, experiment, plan_graph
from .core.identities import content_identity
from .operations.runner import seal

CAPABILITY = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z][a-z0-9_-]*)+\.v[1-9][0-9]*$")
KINDS = {"compute", "representation"}
MODES = {"headless", "interactive"}
PROFILES = {"orchestration", "scientific", "coordination", "systems", "native_edge", "hardware", "external"}
MAX_CAPABILITIES = 128
MAX_IMPLEMENTATIONS = 8
MAX_NODES = 64
MAX_EFFECTS = 16
MAX_RESOURCES = 16


def _capability_id(value: Any) -> str:
    if type(value) is not str or CAPABILITY.fullmatch(value) is None or len(value) > 160:
        raise ValueError("Capability IDs must be bounded, hierarchical and versioned")
    return value


def _names(values, maximum, label):
    if type(values) not in (list, tuple) or len(values) > maximum:
        raise ValueError(f"{label} exceeds bound")
    result = [text(value) for value in values]
    if len(result) != len(set(result)):
        raise ValueError(f"{label} contains duplicates")
    return tuple(result)


def _ports(value):
    if type(value) is not dict or len(value) > 32:
        raise ValueError("Semantic ports must be bounded objects")
    result = {}
    for name, spec in value.items():
        text(name)
        result[name] = Port.from_dict(spec).to_dict()
    return result


@dataclass(frozen=True)
class SemanticMorphism:
    """Stable operation meaning, independent of a current engine/language."""

    capability_id: str
    kind: str
    inputs: dict[str, dict]
    outputs: dict[str, dict]
    effects: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict:
        _capability_id(self.capability_id)
        if self.kind not in KINDS:
            raise ValueError("Unknown semantic capability kind")
        if type(self.description) is not str or len(self.description) > 512:
            raise ValueError("Semantic description must be bounded text")
        if self.description and not self.description.strip():
            raise ValueError("Semantic description cannot be whitespace-only")
        return {
            "capability_id": self.capability_id,
            "kind": self.kind,
            "inputs": _ports(self.inputs),
            "outputs": _ports(self.outputs),
            "effects": list(_names(self.effects, MAX_EFFECTS, "Capability effects")),
            "description": self.description,
        }


@dataclass(frozen=True)
class EngineLowering:
    """Functor-like mapping from one semantic morphism to one concrete operation.

    execution_profile is routing metadata, not a claim about what a language can
    or cannot do. runtime_family may be python/julia/rust/cpp/mojo/elixir/zig/
    taichi/hdl/external or another explicitly named runtime.
    """

    capability_id: str
    operation_id: str
    engine_id: str
    runtime_family: str
    execution_profile: str
    execution_mode: str
    resources: tuple[str, ...] = ()
    priority: int = 100

    def to_dict(self) -> dict:
        _capability_id(self.capability_id)
        for value in (self.operation_id, self.engine_id, self.runtime_family):
            text(value)
        if self.execution_profile not in PROFILES:
            raise ValueError("Unknown execution profile")
        if self.execution_mode not in MODES:
            raise ValueError("Execution mode must be headless or interactive")
        if type(self.priority) is not int or not 0 <= self.priority <= 10000:
            raise ValueError("Implementation priority must be an integer in 0..10000")
        return {
            "capability_id": self.capability_id,
            "operation_id": self.operation_id,
            "engine_id": self.engine_id,
            "runtime_family": self.runtime_family,
            "execution_profile": self.execution_profile,
            "execution_mode": self.execution_mode,
            "resources": list(_names(self.resources, MAX_RESOURCES, "Implementation resources")),
            "priority": self.priority,
        }


@dataclass(frozen=True)
class ComparisonWitness:
    """Retained evidence comparing two lowerings under one named policy.

    A finite comparison is intentionally not named a natural transformation:
    naturality would require a law over an entire diagram/category, not one run.
    """

    capability_id: str
    left_engine: str
    right_engine: str
    policy_id: str
    evidence_id: str

    def to_dict(self) -> dict:
        _capability_id(self.capability_id)
        for value in (self.left_engine, self.right_engine, self.policy_id, self.evidence_id):
            text(value)
        if self.left_engine == self.right_engine:
            raise ValueError("Comparison witness requires two different engine identities")
        return {
            "capability_id": self.capability_id,
            "left_engine": self.left_engine,
            "right_engine": self.right_engine,
            "policy_id": self.policy_id,
            "evidence_id": self.evidence_id,
            "claim": "finite_comparison_witness_not_naturality_proof",
        }


class SemanticRegistry:
    """Operator-owned semantic catalog over the existing concrete registry."""

    def __init__(self, concrete: CapabilityRegistry):
        if not isinstance(concrete, CapabilityRegistry):
            raise TypeError("Semantic registry requires the existing CapabilityRegistry")
        self.concrete = concrete
        self._morphisms: dict[str, dict] = {}
        self._lowerings: dict[str, list[dict]] = {}
        self._witnesses: list[dict] = []

    def declare(self, morphism: SemanticMorphism) -> None:
        value = morphism.to_dict()
        name = value["capability_id"]
        if name in self._morphisms or len(self._morphisms) >= MAX_CAPABILITIES:
            raise ValueError("Duplicate capability or catalog capacity exceeded")
        self._morphisms[name] = value
        self._lowerings[name] = []

    def implement(self, lowering: EngineLowering) -> None:
        value = lowering.to_dict()
        name = value["capability_id"]
        if name not in self._morphisms:
            raise ValueError("Lowering refers to undeclared semantic morphism")
        rows = self._lowerings[name]
        if len(rows) >= MAX_IMPLEMENTATIONS:
            raise ValueError("Too many lowerings for one capability")
        if any(row["operation_id"] == value["operation_id"] or
               row["engine_id"] == value["engine_id"] for row in rows):
            raise ValueError("Ambiguous implementation identity")

        concrete = self.concrete.contract(value["operation_id"])
        semantic = self._morphisms[name]
        concrete_inputs = {port: Port.from_dict(spec).to_dict()
                           for port, spec in concrete["inputs"].items()}
        concrete_outputs = {port: Port.from_dict(spec["type"]).to_dict()
                            for port, spec in concrete["outputs"].items()}
        if concrete_inputs != semantic["inputs"] or concrete_outputs != semantic["outputs"]:
            raise ValueError("Engine lowering does not preserve semantic object/port contracts")
        rows.append(value)
        rows.sort(key=lambda row: (row["priority"], row["engine_id"], row["operation_id"]))

    def retain_witness(self, witness: ComparisonWitness) -> None:
        value = witness.to_dict()
        if value["capability_id"] not in self._morphisms:
            raise ValueError("Comparison witness refers to undeclared capability")
        engines = {row["engine_id"] for row in self._lowerings[value["capability_id"]]}
        if value["left_engine"] not in engines or value["right_engine"] not in engines:
            raise ValueError("Comparison witness refers to an unknown lowering")
        self._witnesses.append(value)

    def catalog(self) -> dict:
        bound = {row["operation_id"] for row in self.concrete.operations.describe()}
        return seal({
            "schema": "ciw.semantic-capability-catalog.v1",
            "authorizes_execution": False,
            "headless_default": True,
            "visualization_policy": "demand_driven",
            "execution_profiles": sorted(PROFILES),
            "objects": sorted({
                content_identity(port)
                for value in self._morphisms.values()
                for port in list(value["inputs"].values()) + list(value["outputs"].values())
            }),
            "morphisms": deepcopy(self._morphisms),
            "lowerings": {
                name: [{**deepcopy(row), "bound": row["operation_id"] in bound}
                       for row in rows]
                for name, rows in self._lowerings.items()
            },
            "comparison_witnesses": deepcopy(self._witnesses),
        })

    def resolve(self, capability_id: str, *, required_resources=(), inspection_requested=False) -> dict:
        name = _capability_id(capability_id)
        if name not in self._morphisms:
            raise ValueError("Unknown semantic capability")
        morphism = self._morphisms[name]
        resources = set(_names(required_resources, MAX_RESOURCES, "Requested resources"))
        if morphism["kind"] == "representation" and inspection_requested is not True:
            raise ValueError("Representation capabilities are demand-driven and require an explicit inspection request")
        bound = {row["operation_id"] for row in self.concrete.operations.describe()}
        eligible = []
        for row in self._lowerings[name]:
            if row["operation_id"] not in bound:
                continue
            if morphism["kind"] == "compute" and row["execution_mode"] != "headless":
                continue
            if not resources <= set(row["resources"]):
                continue
            eligible.append(row)
        if not eligible:
            raise ValueError("No explicitly bound lowering satisfies semantic policy")
        chosen = deepcopy(eligible[0])
        return seal({
            "schema": "ciw.semantic-resolution.v1",
            "capability_id": name,
            "kind": morphism["kind"],
            "operation_id": chosen["operation_id"],
            "engine_id": chosen["engine_id"],
            "runtime_family": chosen["runtime_family"],
            "execution_profile": chosen["execution_profile"],
            "execution_mode": chosen["execution_mode"],
            "resources": chosen["resources"],
            "inspection_requested": bool(inspection_requested),
            "operator_selected": True,
            "agent_selected_engine": False,
        })


def _graph(value: dict) -> list[str]:
    keys(value, {"schema", "graph_id", "mandate", "model_id", "nodes"})
    if value["schema"] != "ciw.semantic-work-graph.v1":
        raise ValueError("Unsupported semantic work graph")
    text(value["graph_id"])
    text(value["mandate"])
    text(value["model_id"])
    nodes = value["nodes"]
    if type(nodes) is not list or not 1 <= len(nodes) <= MAX_NODES:
        raise ValueError("Semantic graph requires 1..64 nodes")
    seen, deps = set(), {}
    for node in nodes:
        keys(node, {"node_id", "capability", "parameters", "inputs", "depends_on",
                    "resources", "acceptance", "inspection"})
        node_id = text(node["node_id"])
        if node_id in seen:
            raise ValueError("Duplicate semantic node")
        seen.add(node_id)
        _capability_id(node["capability"])
        if type(node["parameters"]) is not dict or type(node["inputs"]) is not dict or type(node["acceptance"]) is not dict:
            raise ValueError("Semantic parameters/inputs/acceptance must be objects")
        detached(node["parameters"])
        detached(node["acceptance"])
        _names(node["resources"], MAX_RESOURCES, "Node resources")
        if type(node["inspection"]) is not bool or type(node["depends_on"]) is not list:
            raise ValueError("Semantic inspection/dependencies have invalid type")
        current = set()
        for dep in node["depends_on"]:
            current.add(text(dep))
        for port_name, edge in node["inputs"].items():
            text(port_name)
            keys(edge, {"node_id", "port"})
            current.add(text(edge["node_id"]))
            text(edge["port"])
        if node_id in current:
            raise ValueError("Semantic node cannot depend on itself")
        deps[node_id] = current
    if any(value - seen for value in deps.values()):
        raise ValueError("Semantic graph has a missing dependency")
    order = []
    while len(order) < len(nodes):
        ready = [node["node_id"] for node in nodes
                 if node["node_id"] not in order and deps[node["node_id"]] <= set(order)]
        if not ready:
            raise ValueError("Semantic graph contains a cycle")
        order.extend(ready)
    return order


def compile_graph(value: dict, registry: SemanticRegistry) -> dict:
    """Lower a semantic graph into the original experiment contract plus a receipt."""
    value = detached(value)
    order = _graph(value)
    nodes = {node["node_id"]: node for node in value["nodes"]}
    resolutions, lowered = {}, []

    for node_id in order:
        node = nodes[node_id]
        resolution = registry.resolve(
            node["capability"],
            required_resources=node["resources"],
            inspection_requested=node["inspection"],
        )
        resolutions[node_id] = resolution
        morphism = registry._morphisms[node["capability"]]
        if set(node["inputs"]) != set(morphism["inputs"]):
            if morphism["inputs"] or node["inputs"]:
                raise ValueError("Semantic node inputs differ from capability contract")
        for input_name, edge in node["inputs"].items():
            producer = nodes[edge["node_id"]]
            output_morphism = registry._morphisms[producer["capability"]]
            if edge["port"] not in output_morphism["outputs"]:
                raise ValueError("Semantic input selects unknown producer port")
            expected = Port.from_dict(morphism["inputs"][input_name]).to_dict()
            produced = Port.from_dict(output_morphism["outputs"][edge["port"]]).to_dict()
            if expected != produced:
                raise ValueError("Semantic port mismatch; no implicit schema/unit/frame conversion")
        lowered.append({
            "node_id": node_id,
            "operation_id": resolution["operation_id"],
            "parameters": deepcopy(node["parameters"]),
            "inputs": deepcopy(node["inputs"]),
            "depends_on": deepcopy(node["depends_on"]),
        })

    concrete = experiment(value["graph_id"], model_id=value["model_id"], nodes=lowered)
    plan_graph(concrete, registry.concrete)
    catalog = registry.catalog()
    return seal({
        "schema": "ciw.semantic-compilation.v1",
        "graph": value,
        "graph_digest": content_identity(value),
        "catalog_digest": content_identity(catalog),
        "resolution_order": order,
        "resolutions": resolutions,
        "experiment": concrete,
        "headless_default": True,
        "visualization_policy": "demand_driven",
        "authorizes_execution": False,
        "acceptance": {node_id: deepcopy(nodes[node_id]["acceptance"]) for node_id in order},
    })


def builtin_semantic_registry(concrete: CapabilityRegistry) -> SemanticRegistry:
    result = SemanticRegistry(concrete)
    result_port = Port("ciw.operation-result.v1").to_dict()
    for capability, operation, description in (
        ("analysis.statistics.v1", "statistics.v1", "Compute retained descriptive statistics."),
        ("analysis.spectrum.v1", "spectrum.periodogram.v1", "Compute a retained periodogram."),
    ):
        result.declare(SemanticMorphism(
            capability, "compute", {}, {"result": result_port},
            effects=("read:recording",), description=description))
        result.implement(EngineLowering(
            capability, operation, "ciw.oscillator", "python",
            "orchestration", "headless", resources=("cpu",), priority=10))
    return result


TOOLS = {
    "net_semantic_catalog": tool(
        "catalog",
        "Read the operator-owned semantic catalog. Discovery never authorizes provider execution."),
    "net_semantic_compile": tool(
        "compile",
        "Validate and lower a typed semantic work graph into an ordinary NET experiment. Name capabilities, not engines. Representation operations require explicit inspection requests.",
        {"graph": {"type": "object"}}, ("graph",), read=False),
}


def descriptions():
    return [{"name": name, **deepcopy({k: v for k, v in spec.items() if k != "method"})}
            for name, spec in TOOLS.items()]


class SemanticHost:
    """MCP-compatible data-only host; no execute, merge, release, or rendering tool."""

    instructions = (
        "Submit semantic capabilities, never provider names or shell commands. "
        "Computation is headless by default. Representations require explicit inspection. "
        "Compilation cannot authorize execution, release, state admission, or hardware actuation."
    )

    def __init__(self, registry: SemanticRegistry):
        self.registry = registry

    def descriptions(self):
        return descriptions()

    def call(self, name, arguments):
        if name not in TOOLS:
            raise ValueError("Unknown semantic tool")
        _shape(arguments, TOOLS[name]["inputSchema"])
        detached(arguments)
        return getattr(self, TOOLS[name]["method"])(**arguments)

    def catalog(self):
        return self.registry.catalog()

    def compile(self, graph):
        return compile_graph(graph, self.registry)
