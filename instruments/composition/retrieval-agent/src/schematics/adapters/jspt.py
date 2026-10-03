"""Wrap JSPT without importing it at module load.

Pin is schematics.pins.JSPT. Missing sensitivity is NOT_CHECKED, not a sample.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

from ..annotate import upsert_certificate
from ..ir import EdgeKind, Node, NodeKind, Schematic, Status
from ..kernels import KernelEvent
from ..pins import CATALOGUE_ALIASES, JSPT
from ..binding import call_inputs, declaration, finite_matrix, make_binding


class JsptUnavailable(RuntimeError):
    pass


def load_sensitivity() -> Any:
    try:
        return import_module(JSPT["import"])
    except ImportError as exc:
        raise JsptUnavailable(f"{JSPT['import']} is not installed; pin {JSPT['repo']}@{JSPT['sha']}") from exc


def _build_drag(sensitivity: Any, c: float) -> Any:
    try:
        import numpy as np
    except ImportError:
        np = None

    def forward(vec):
        x = float(vec[0])
        val = -c * x * abs(x)
        return np.array([val]) if np is not None else [val]

    def jacobian(vec):
        x = float(vec[0])
        deriv = -2.0 * c * abs(x) if x != 0.0 else 0.0
        return np.array([[deriv]]) if np is not None else [[deriv]]

    return sensitivity.DifferentiableModel(
        name="quadratic_drag",
        forward=forward,
        input_dim=1,
        output_dim=1,
        jacobian=jacobian,
        notes="state-only slice; u treated as independent. Not a JSPT catalogue map.",
        tags=("nonlinear", "analytical", "sra-wrap"),
    )


def resolve_model(sensitivity: Any, model_ref: str, attrs: dict[str, Any]) -> Any:
    alias = CATALOGUE_ALIASES.get(model_ref)
    if alias is not None:
        catalogue = sensitivity.reference_catalogue()
        if alias not in catalogue:
            raise JsptUnavailable(f"catalogue has no {alias!r} at pin {JSPT['sha']}")
        return catalogue[alias]
    if model_ref == "jspt.reference.quadratic_drag":
        return _build_drag(sensitivity, float(attrs.get("c", 0.5)))
    raise JsptUnavailable(f"unmapped model_ref {model_ref!r}")


def _matrix(estimate: Any) -> list[list[float]]:
    raw = getattr(estimate, "matrix", estimate)
    # NumPy arrays/scalars are normalized without coercing bool/string/complex
    # into plausible real values. The strict validator owns conversion.
    raw = raw.tolist() if hasattr(raw, "tolist") else raw
    return finite_matrix(raw)


def call_jacobian_at(schematic: Schematic, function_id: str) -> KernelEvent:
    node = schematic.node(function_id)
    model_ref = node.get("model_ref")
    x_star = node.get("x_star")
    try:
        declared = declaration(schematic, function_id)
        inputs = call_inputs(declared)
        sensitivity = load_sensitivity()
        model = resolve_model(sensitivity, inputs["model_ref"], declared["function"])
        estimate = sensitivity.jacobian_at(model, inputs["x_star"])
        A = finite_matrix(_matrix(estimate))
        if declaration(schematic, function_id) != declared or inputs != call_inputs(declared):
            raise ValueError("function declaration changed during the adapter call")
        binding = make_binding(declared, A)
    except JsptUnavailable as exc:
        upsert_certificate(schematic, node_id=f"cert:jspt:{function_id}", owner="jspt", result=Status.NOT_CHECKED, target=function_id, edge=EdgeKind.LINEARIZES, attrs={"tool": "jspt.jacobian_at", "fixture": False, "pin": f"{JSPT['repo']}@{JSPT['sha']}", "reason": str(exc)})
        return KernelEvent(tool="jspt.jacobian_at", owner="jspt", node_id=function_id, result=Status.NOT_CHECKED, detail={"reason": str(exc), "pin": JSPT})
    except Exception as exc:
        upsert_certificate(schematic, node_id=f"cert:jspt:{function_id}", owner="jspt", result=Status.REFUSED, target=function_id, edge=EdgeKind.LINEARIZES, attrs={"tool": "jspt.jacobian_at", "fixture": False, "pin": f"{JSPT['repo']}@{JSPT['sha']}", "reason": str(exc)})
        return KernelEvent(tool="jspt.jacobian_at", owner="jspt", node_id=function_id, result=Status.REFUSED, detail={"reason": str(exc), "pin": JSPT})
    upsert_certificate(schematic, node_id=f"cert:jspt:{function_id}", owner="jspt", result=Status.SAMPLED, target=function_id, edge=EdgeKind.LINEARIZES, attrs={"tool": "jspt.jacobian_at", "A": A, "fixture": False, "model_ref": model_ref, "source": getattr(estimate, "source", "unknown"), "pin": f"{JSPT['repo']}@{JSPT['sha']}", "binding": binding, "reason": "content-bound jacobian_at adapter record; source revision and execution origin are not authenticated"})
    return KernelEvent(tool="jspt.jacobian_at", owner="jspt", node_id=function_id, result=Status.SAMPLED, detail={"fixture": False, "A": A, "pin": JSPT, "execution_ref": binding["execution_id"], "result_ref": binding["result_id"], "provenance": dict(binding["provenance"])})


def call_perturbation_sweep(schematic: Schematic, function_id: str, *, scales: tuple[float, ...] = (1e-4, 1e-3, 1e-2, 5e-2)) -> KernelEvent:
    node = schematic.node(function_id)
    try:
        sensitivity = load_sensitivity()
        model = resolve_model(sensitivity, str(node.get("model_ref")), dict(node.attrs))
        sweep = sensitivity.sweep_perturbation_scale(model, node.get("x_star"), [1.0] * len(list(node.get("x_star"))), scales)
        validity = sensitivity.local_validity(sweep)
        radius = validity.valid_scale
    except JsptUnavailable as exc:
        return KernelEvent(tool="jspt.sweep_perturbation_scale", owner="jspt", node_id=function_id, result=Status.NOT_CHECKED, detail={"reason": str(exc), "pin": JSPT})
    except Exception as exc:
        return KernelEvent(tool="jspt.sweep_perturbation_scale", owner="jspt", node_id=function_id, result=Status.REFUSED, detail={"reason": str(exc), "pin": JSPT})
    cert_id = f"cert:jspt:{function_id}"
    if cert_id in schematic.nodes:
        attrs = dict(schematic.node(cert_id).attrs)
        attrs["validity_radius"] = radius
        schematic.replace(Node(id=cert_id, kind=NodeKind.CERTIFICATE, attrs=attrs))
    return KernelEvent(tool="jspt.sweep_perturbation_scale", owner="jspt", node_id=function_id, result=Status.SAMPLED, detail={"validity_radius": radius, "pin": JSPT})
