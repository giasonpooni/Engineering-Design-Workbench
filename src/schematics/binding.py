"""Content-bound adapter records, not authentication or independent proof.

The graph remains readable when legacy annotations have no binding. Only a
current, unambiguous, self-consistent adapter record may route dependent calls.
An author able to rewrite an entire record can recompute these hashes; trust in
the record's origin must be established outside this package.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from uuid import uuid4

from .ir import EdgeKind, Node, NodeKind, Schematic, Status
from .pins import JSPT

SCHEMA = "NsJacobianBinding@0.1"
TOOL = "jspt.jacobian_at"
PROVENANCE = {
    "kind": "adapter_call_record",
    "authentication": "not_authenticated",
    "kernel_revision_status": "declared_pin_not_verified",
    "independent_verification": "not_claimed",
}
# Neither derived annotations nor a later covariance query change the Jacobian.
_DERIVED = {"rank", "invisible_dim", "sigma_x"}


def snapshot(value):
    """Strict finite JSON snapshot, avoiding aliases and lossy key conversion."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (int, float)):
        try:
            if math.isfinite(value):
                return value
        except OverflowError:
            pass
        raise ValueError("binding values must be finite")
    if isinstance(value, Mapping):
        if any(not isinstance(k, str) for k in value):
            raise ValueError("binding object keys must be strings")
        return {k: snapshot(v) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [snapshot(v) for v in value]
    raise ValueError("binding values must be finite JSON data")


def digest(namespace: str, value) -> str:
    payload = json.dumps(snapshot(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256((namespace + "\0" + payload).encode()).hexdigest()


def finite_vector(value, name: str) -> list[float]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise ValueError(f"{name} must be a nonempty numeric sequence")
    out = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise ValueError(f"{name} must contain numeric scalars")
        try:
            number = float(item)
        except (ValueError, OverflowError) as exc:
            raise ValueError(f"{name} must be finite") from exc
        if not math.isfinite(number):
            raise ValueError(f"{name} must be finite")
        out.append(number)
    return out


def finite_matrix(value) -> list[list[float]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)) or not value:
        raise ValueError("A must be a nonempty numeric matrix")
    rows = [finite_vector(row, "A row") for row in value]
    if any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("A must be rectangular")
    return rows


def declaration(schematic: Schematic, function_id: str) -> dict:
    node = schematic.node(function_id)
    if node.kind is not NodeKind.FUNCTION:
        raise ValueError("Jacobian target must be a function")
    attrs = {k: v for k, v in node.attrs.items() if k not in _DERIVED}
    ports = []
    for edge in schematic.edges:
        if edge.kind in {EdgeKind.INPUT, EdgeKind.OUTPUT, EdgeKind.ACTUATES} and function_id in {edge.src, edge.dst}:
            other = schematic.node(edge.dst if edge.src == function_id else edge.src)
            ports.append({"edge": edge.kind.value, "src": edge.src, "dst": edge.dst,
                          "attrs": dict(edge.attrs), "node_kind": other.kind.value,
                          "node_attrs": dict(other.attrs)})
    return snapshot({"target": function_id, "function": attrs, "ports": ports})


def call_inputs(declared: dict) -> dict:
    attrs = declared["function"]
    if attrs.get("class") not in {"linear", "lpv", "nonlinear"}:
        raise ValueError("Jacobian call requires a known declared plant class")
    model_ref = attrs.get("model_ref")
    if not isinstance(model_ref, str) or not model_ref.strip():
        raise ValueError("model_ref must be declared")
    result = {"model_ref": model_ref, "x_star": finite_vector(attrs.get("x_star"), "x_star")}
    if model_ref == "jspt.reference.quadratic_drag":
        result["parameters"] = {"c": finite_vector([attrs.get("c", 0.5)], "c")[0]}
    else:
        result["parameters"] = {"source": "pinned reference catalogue defaults"}
    return result


def make_binding(declared: dict, A, *, execution_id: str | None = None) -> dict:
    matrix = finite_matrix(A)
    inputs = call_inputs(declared)
    if len(matrix[0]) != len(inputs["x_star"]):
        raise ValueError("A columns must match the actual x_star dimension")
    binding = {"schema": SCHEMA, "operation": TOOL,
               "execution_id": execution_id or "sra-execution:" + str(uuid4()),
               "declaration_id": digest("sra.declaration.v1", declared),
               "call_inputs": inputs, "kernel": dict(JSPT), "provenance": dict(PROVENANCE)}
    binding["result_id"] = digest("sra.jacobian-result.v1", {**binding, "A": matrix})
    return binding


def matches(schematic: Schematic, function_id: str, cert: Node) -> bool:
    if (cert.kind is not NodeKind.CERTIFICATE or cert.get("owner") != "jspt"
            or cert.get("tool") != TOOL or cert.get("fixture") is not False
            or cert.get("result") != Status.SAMPLED.value
            or cert.get("pin") != f"{JSPT['repo']}@{JSPT['sha']}"):
        return False
    binding = cert.get("binding")
    if not isinstance(binding, Mapping):
        return False
    execution_id = binding.get("execution_id")
    if not isinstance(execution_id, str) or not execution_id.startswith("sra-execution:") or not execution_id.removeprefix("sra-execution:"):
        return False
    try:
        declared = declaration(schematic, function_id)
        return (cert.get("model_ref") == declared["function"].get("model_ref")
                and dict(binding) == make_binding(declared, cert.get("A"), execution_id=execution_id))
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        return False
