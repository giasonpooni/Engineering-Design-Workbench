"""Bounded wiring algebra compiled to the original NET experiment DAG.

Series connects typed wires; parallel juxtaposes them, not CPU threads. Identities
and permutations are structural and never create execution occurrences. Operator
annotations are static contracts, NOT inferred permissions or physical evidence.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import re

from .control_contracts import _base, bytes_ref, content_ref, detached, keys, text
from .control_plane import Port, _plan_contracts, experiment, run_graph
from .core.identities import content_identity
from .operations.registry import valid_operation_id
from .operations.runner import seal

MAX_TERMS = 256
MAX_DEPTH = 10
MAX_PORTS = 64
AUTHORITY = {"authorizes_execution": False, "verification_id": None,
             "state_admission": "not_performed", "release": "not_performed"}


def _names(values, *, maximum=64):
    if type(values) is not list or len(values) > maximum:
        raise ValueError("Expected bounded list of distinct names")
    for value in values:
        text(value)
    if len(set(values)) != len(values):
        raise ValueError("Duplicate name")
    return sorted(values)


def wire(schema: str, *, unit=None, frame=None, clock=None, meaning=None) -> dict:
    """Refine an existing port. None means unspecified, never a wildcard.

    Clock/meaning are operator declarations: the owning payload validator must
    establish them at runtime. Matching labels do not synchronize two clocks.
    """
    value = {"port": Port(schema, unit, frame).to_dict(), "clock": clock, "meaning": meaning}
    _wire(value)
    return value


def _wire(value):
    keys(value, {"port", "clock", "meaning"})
    Port.from_dict(value["port"])
    for key in ("clock", "meaning"):
        if value[key] is not None:
            text(value[key])
    return detached(value)


def _ports(values):
    if type(values) is not list or len(values) > MAX_PORTS:
        raise ValueError("Interface exceeds 64 ports")
    return [_wire(value) for value in values]


def effects(*, reads=(), writes=(), unknown=False):
    """Logical hierarchical resource names, not host paths or an OS sandbox."""
    if type(reads) not in (tuple, list) or type(writes) not in (tuple, list):
        raise ValueError("Effect resources must be explicit lists or tuples")
    value = {"reads": list(reads), "writes": list(writes), "unknown": unknown}
    return _effects(value)


def _effects(value):
    keys(value, {"reads", "writes", "unknown"})
    if type(value["unknown"]) is not bool:
        raise ValueError("Unknown-effect flag must be Boolean")
    result = {key: _names(value[key]) for key in ("reads", "writes")}
    for resource in result["reads"] + result["writes"]:
        if re.fullmatch(r"[A-Za-z0-9_.:-]+(?:/[A-Za-z0-9_.:-]+)*", resource) is None or any(
                part in {".", ".."} for part in resource.split("/")):
            raise ValueError("Effects require explicit logical resource names")
    return {**result, "unknown": value["unknown"]}


def grant(*, permissions=(), qualifications=None):
    """Operator-owned exact grants. A release grant does not imply build rights."""
    if type(permissions) not in (tuple, list):
        raise ValueError("Permissions must be an explicit list or tuple")
    permissions = _names(list(permissions))
    qualifications = {} if qualifications is None else detached(qualifications)
    if type(qualifications) is not dict or len(qualifications) > 64:
        raise ValueError("Invalid qualification references")
    for name, ref in qualifications.items():
        text(name); content_ref(ref)
    return {"permissions": permissions, "qualifications": qualifications}


def _grant(value):
    keys(value, {"permissions", "qualifications"})
    if type(value["permissions"]) is not list:
        raise ValueError("Permissions must be a list")
    return grant(permissions=value["permissions"], qualifications=value["qualifications"])


def declare(registry, operation_id, *, effect=None, permissions=(), qualifications=None,
            inputs=None, outputs=None):
    """Pin one original contract; never bind code or discover a provider.

    Omitted effects are UNKNOWN, not pure. Optional input/output refinements must
    name exactly the original ports and retain their schema/unit/frame contracts.
    """
    contract = registry.contract(operation_id)
    basic_inputs = contract["inputs"]
    basic_outputs = {name: item["type"] for name, item in contract["outputs"].items()}
    def ports(original, refined):
        if refined is None:
            return {name: {"port": deepcopy(port), "clock": None, "meaning": None}
                    for name, port in original.items()}
        keys(refined, set(original))
        for name, value in refined.items():
            if _wire(value)["port"] != original[name]:
                raise ValueError("Refinement cannot change the original port")
        return detached(refined)
    requirements = grant(permissions=permissions, qualifications=qualifications)
    return {"contract_digest": content_identity(contract),
            "inputs": ports(basic_inputs, inputs), "outputs": ports(basic_outputs, outputs),
            "effects": effects(unknown=True) if effect is None else _effects(effect),
            **requirements}


def _declarations(contracts, declarations, authorization):
    """Validate data-only snapshots; no runtime callbacks are invoked here."""
    keys(declarations, set(contracts))
    for op, declaration in declarations.items():
        if not valid_operation_id(op):
            raise ValueError("Operation must have a versioned identity")
        keys(declaration, {"contract_digest", "inputs", "outputs", "effects", "permissions", "qualifications"})
        contract = contracts[op]
        if declaration["contract_digest"] != content_identity(contract):
            raise ValueError("Operation contract drift")
        for kind in ("inputs", "outputs"):
            basic = contract[kind]
            keys(declaration[kind], set(basic))
            for name, value in declaration[kind].items():
                port = basic[name] if kind == "inputs" else basic[name]["type"]
                if _wire(value)["port"] != port:
                    raise ValueError("Refinement contradicts an original port")
        _effects(declaration["effects"])
        required = _grant({key: declaration[key] for key in ("permissions", "qualifications")})
        if set(required["permissions"]) - set(authorization["permissions"]):
            raise ValueError("Missing exact operation permission")
        if any(authorization["qualifications"].get(name) != ref
               for name, ref in required["qualifications"].items()):
            raise ValueError("Missing or mismatched qualification reference")


def call(node_id: str, operation_id: str, parameters=None):
    return {"kind": "call", "node_id": text(node_id), "operation_id": operation_id,
            "parameters": detached({} if parameters is None else parameters)}


def identity(ports=()):
    return {"kind": "identity", "ports": _ports(list(ports))}


def sequence(*items):
    return {"kind": "sequence", "items": list(items)}


def parallel(*items):
    return {"kind": "parallel", "items": list(items)}


def permute(ports, order):
    return {"kind": "permute", "ports": _ports(list(ports)), "order": list(order)}


def _validate_expression(value, *, production=False):
    count = 0
    operations = set()
    names = set()
    def visit(node, depth):
        nonlocal count
        count += 1
        if depth > MAX_DEPTH or count > MAX_TERMS:
            raise ValueError("Workflow syntax exceeds depth/term budget")
        if type(node) is not dict:
            raise ValueError("Workflow term must be an object")
        kind = node.get("kind")
        if kind in ("sequence", "parallel"):
            keys(node, {"kind", "items"})
            if type(node["items"]) is not list or len(node["items"]) > 64:
                raise ValueError("Composition exceeds term-list budget")
            for item in node["items"]:
                visit(item, depth + 1)
        elif kind == "identity":
            keys(node, {"kind", "ports"}); _ports(node["ports"])
            if production and node["ports"]:
                raise ValueError("Production identity has no data ports")
        elif kind == "permute" and not production:
            keys(node, {"kind", "ports", "order"}); _ports(node["ports"])
            order = node["order"]
            if type(order) is not list or any(type(i) is not int for i in order) or sorted(order) != list(range(len(node["ports"]))):
                raise ValueError("Permutation must use every wire exactly once")
        elif kind == "call" and not production:
            keys(node, {"kind", "node_id", "operation_id", "parameters"})
            name = text(node["node_id"])
            if not valid_operation_id(node["operation_id"]) or type(node["parameters"]) is not dict:
                raise ValueError("Invalid operation or parameters")
            if name in names:
                raise ValueError("Duplicate call label; repeated execution needs a fresh label")
            names.add(name); operations.add(node["operation_id"])
            detached(node["parameters"])
        elif kind in ("stage", "bounded_retry") and production:
            keys(node, {"kind", "name"} | ({"max_attempts"} if kind == "bounded_retry" else set()))
            name = text(node["name"])
            if name in names:
                raise ValueError("A stage may occur only once; retries are explicit")
            names.add(name)
            if kind == "bounded_retry" and (type(node["max_attempts"]) is not int or not 1 <= node["max_attempts"] <= 3):
                raise ValueError("Retry bound must be an integer in 1..3")
        else:
            raise ValueError("Unknown workflow constructor; unbounded feedback/choice is unsupported")
    visit(value, 0)
    detached(value)
    if len(names) > 64:
        raise ValueError("Workflow exceeds original 64-node/job bound")
    return operations, names


def _topology(nodes, dependencies):
    """Reuse the original graph validator; impose stable order only on ready nodes."""
    from .control_plane import _experiment
    names = sorted(nodes)
    graph = experiment("workflow-topology", model_id="workflow-declaration.v1", nodes=[
        {"node_id": name, "operation_id": "workflow.order.v1", "parameters": {},
         "inputs": {}, "depends_on": sorted(dependencies[name])} for name in names])
    return _experiment(graph)


def _overlap(a, b):
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _conflict(a, b):
    if a["unknown"] or b["unknown"]:
        return True
    return (any(_overlap(x, y) for x in a["writes"] for y in b["reads"] + b["writes"])
            or any(_overlap(x, y) for x in b["writes"] for y in a["reads"]))


def _check_independence(order, dependencies, effects_by_node):
    ancestors = {}
    for name in order:
        ancestors[name] = set(dependencies[name])
        for dep in dependencies[name]:
            ancestors[name].update(ancestors[dep])
    for i, left in enumerate(order):
        for right in order[i+1:]:
            if left not in ancestors[right] and _conflict(effects_by_node[left], effects_by_node[right]):
                raise ValueError(f"Unordered effect conflict: {left} / {right}")


@dataclass
class _Diagram:
    inputs: list
    outputs: list  # (wire type, endpoint): external index or node/port
    nodes: dict


def _shift(diagram, offset):
    def edge(ref):
        return {"external": ref["external"] + offset} if "external" in ref else ref
    return _Diagram(diagram.inputs, [(t, edge(r)) for t, r in diagram.outputs],
                    {n: {**v, "inputs": {p: edge(r) for p, r in v["inputs"].items()}}
                     for n, v in diagram.nodes.items()})


def _wire_diagram(expr, declarations):
    kind = expr["kind"]
    if kind == "call":
        declaration = declarations[expr["operation_id"]]
        ins, outs = sorted(declaration["inputs"]), sorted(declaration["outputs"])
        if set(ins) & set(expr["parameters"]):
            raise ValueError("A literal parameter cannot replace a connected input")
        node = {"node_id": expr["node_id"], "operation_id": expr["operation_id"],
                "parameters": deepcopy(expr["parameters"]),
                "inputs": {name: {"external": i} for i, name in enumerate(ins)}, "depends_on": []}
        return _Diagram([declaration["inputs"][name] for name in ins],
                        [(declaration["outputs"][name], {"node_id": expr["node_id"], "port": name}) for name in outs],
                        {expr["node_id"]: node})
    if kind in ("identity", "permute"):
        ports = expr["ports"]
        order = list(range(len(ports))) if kind == "identity" else expr["order"]
        return _Diagram(ports, [(ports[i], {"external": i}) for i in order], {})
    parts = [_wire_diagram(item, declarations) for item in expr["items"]]
    if not parts:
        return _Diagram([], [], {})
    current = parts[0]
    for following in parts[1:]:
        if kind == "parallel":
            shifted = _shift(following, len(current.inputs))
            current = _Diagram(current.inputs + following.inputs, current.outputs + shifted.outputs,
                               {**current.nodes, **shifted.nodes})
        else:
            if [t for t, _ in current.outputs] != following.inputs:
                raise ValueError("Sequential interface mismatch: schema/unit/frame/clock/meaning or arity")
            def edge(ref):
                return current.outputs[ref["external"]][1] if "external" in ref else ref
            new_nodes = {n: {**v, "inputs": {p: edge(r) for p, r in v["inputs"].items()}}
                         for n, v in following.nodes.items()}
            current = _Diagram(current.inputs, [(t, edge(r)) for t, r in following.outputs],
                               {**current.nodes, **new_nodes})
        if len(current.inputs) > MAX_PORTS or len(current.outputs) > MAX_PORTS:
            raise ValueError("Composed interface exceeds port budget")
    return current


def _normalize(expr, contracts, declarations, authorization):
    _declarations(contracts, declarations, authorization)
    diagram = _wire_diagram(expr, declarations)
    dependencies = {name: {ref["node_id"] for ref in node["inputs"].values() if "node_id" in ref}
                    for name, node in diagram.nodes.items()}
    order = _topology(diagram.nodes, dependencies) if diagram.nodes else []
    _check_independence(order, dependencies,
                        {name: declarations[node["operation_id"]]["effects"] for name, node in diagram.nodes.items()})
    return {"inputs": deepcopy(diagram.inputs),
            "outputs": [{"type": deepcopy(t), "source": deepcopy(r)} for t, r in diagram.outputs],
            "nodes": [deepcopy(diagram.nodes[name]) for name in order]}


def normal_form(expr, registry, declarations, authorization):
    """Typed open wiring diagram; node labels/ports retain derivation identity.

    This is not an isomorphism solver and never executes an identity/permutation.
    """
    operations, _ = _validate_expression(expr)
    contracts = {op: registry.contract(op) for op in sorted(operations)}
    selected = {op: detached(declarations[op]) for op in sorted(operations)}
    return _normalize(detached(expr), contracts, selected, _grant(authorization))


def _compile_graph(expr, contracts, declarations, authorization, experiment_id, model_id):
    normal = _normalize(expr, contracts, declarations, authorization)
    if normal["inputs"]:
        raise ValueError("Open workflow: close all inputs with declared source operations before execution")
    if not normal["nodes"]:
        raise ValueError("Structural identity has no executable nodes; use normal_form instead")
    graph = experiment(experiment_id, model_id=model_id, nodes=normal["nodes"])
    _plan_contracts(graph, contracts)
    return seal({"schema": "ciw.workflow-compilation.v1", "expression": detached(expr),
                 "contracts": detached(contracts), "declarations": detached(declarations),
                 "grant_snapshot": authorization, "normal_form": normal, "experiment": graph,
                 "compiler_sha256": bytes_ref(Path(__file__).read_bytes()),
                 "authority": deepcopy(AUTHORITY)})


def compile_graph(expr, registry, declarations, authorization, *, experiment_id, model_id):
    operations, _ = _validate_expression(expr)
    contracts = {op: registry.contract(op) for op in sorted(operations)}
    selected = {op: detached(declarations[op]) for op in sorted(operations)}
    return _compile_graph(expr, contracts, selected, _grant(authorization), experiment_id, model_id)


def inspect_compilation(value):
    """Recompile saved declarations; consistency only, not live execution authority."""
    value = detached(value)
    _base(value, "workflow-compilation", {"expression", "contracts", "declarations", "grant_snapshot",
          "normal_form", "experiment", "compiler_sha256", "authority"})
    operations, _ = _validate_expression(value["expression"])
    keys(value["contracts"], operations)
    expected = _compile_graph(value["expression"], value["contracts"], value["declarations"],
        _grant(value["grant_snapshot"]), value["experiment"]["experiment_id"], value["experiment"]["model_id"])
    if content_identity(value) != content_identity(expected):
        raise ValueError("Compilation does not match recomputed original declarations/compiler")
    return {"integrity": "checked", "fresh_execution": False, **deepcopy(AUTHORITY)}


def run_compiled(session, value, registry, declarations, authorization):
    """Recheck live host contracts/grants, then use the ORIGINAL graph runner."""
    value = detached(value)
    inspect_compilation(value)
    current = compile_graph(value["expression"], registry, declarations, authorization,
        experiment_id=value["experiment"]["experiment_id"], model_id=value["experiment"]["model_id"])
    if content_identity(current) != content_identity(value):
        raise ValueError("Live binding or grant changed; explicit recompilation required")
    return run_graph(session, value["experiment"], registry)
