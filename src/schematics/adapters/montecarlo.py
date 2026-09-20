"""Optional Monte Carlo gap. Not a default. Never a substitute for Sigma_y."""

from __future__ import annotations

from ..annotate import upsert_certificate
from ..eligibility import _written_A
from ..ir import EdgeKind, Schematic, Status
from ..kernels import KernelEvent
from ..pins import JSPT
from .covariance import declared_sigma
from .jspt import JsptUnavailable, load_sensitivity, resolve_model


def call_monte_carlo_covariance(schematic: Schematic, function_id: str, *, samples: int = 400) -> KernelEvent:
    node = schematic.node(function_id)
    cert_A = _written_A(schematic, function_id)
    try:
        sigma = declared_sigma(schematic, function_id)
    except (TypeError, ValueError, OverflowError) as exc:
        upsert_certificate(schematic, node_id=f"cert:jspt.mc:{function_id}", owner="jspt", result=Status.REFUSED, target=function_id, edge=EdgeKind.LINEARIZES, attrs={"tool": "jspt.run_covariance_experiment", "reason": f"invalid sigma_x: {exc}"})
        return KernelEvent(tool="jspt.run_covariance_experiment", owner="jspt", node_id=function_id, result=Status.REFUSED, detail={"reason": f"invalid sigma_x: {exc}", "pin": JSPT})
    if cert_A is None or sigma is None:
        return KernelEvent(tool="jspt.run_covariance_experiment", owner="jspt", node_id=function_id, result=Status.NOT_ELIGIBLE, detail={"reason": "need non-fixture A and declared sigma_x", "pin": JSPT})
    try:
        sensitivity = load_sensitivity()
        model = resolve_model(sensitivity, str(node.get("model_ref")), dict(node.attrs))
        experiment = sensitivity.run_covariance_experiment(model, node.get("x_star"), sigma, samples=samples)
    except JsptUnavailable as exc:
        return KernelEvent(tool="jspt.run_covariance_experiment", owner="jspt", node_id=function_id, result=Status.NOT_CHECKED, detail={"reason": str(exc), "pin": JSPT})
    except Exception as exc:
        upsert_certificate(schematic, node_id=f"cert:jspt.mc:{function_id}", owner="jspt", result=Status.REFUSED, target=function_id, edge=EdgeKind.LINEARIZES, attrs={"tool": "jspt.run_covariance_experiment", "pin": f"{JSPT['repo']}@{JSPT['sha']}", "reason": str(exc)})
        return KernelEvent(tool="jspt.run_covariance_experiment", owner="jspt", node_id=function_id, result=Status.REFUSED, detail={"reason": str(exc), "pin": JSPT})
    upsert_certificate(
        schematic,
        node_id=f"cert:jspt.mc:{function_id}",
        owner="jspt",
        result=Status.SAMPLED,
        target=function_id,
        edge=EdgeKind.LINEARIZES,
        attrs={"tool": "jspt.run_covariance_experiment", "sigma_x": sigma, "source_result_ref": cert_A.get("binding")["result_id"], "source_execution_ref": cert_A.get("binding")["execution_id"], "frobenius_gap": float(experiment.frobenius_gap), "relative_gap": float(experiment.relative_gap), "samples": int(experiment.samples), "notes": experiment.notes, "pin": f"{JSPT['repo']}@{JSPT['sha']}", "reason": "Monte Carlo measures the remainder; it does not replace Sigma_y"},
    )
    return KernelEvent(tool="jspt.run_covariance_experiment", owner="jspt", node_id=function_id, result=Status.SAMPLED, detail={"frobenius_gap": float(experiment.frobenius_gap), "relative_gap": float(experiment.relative_gap), "pin": JSPT})
