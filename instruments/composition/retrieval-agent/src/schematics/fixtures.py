"""Shipped plants. Small enough to walk by hand."""

from __future__ import annotations

from .ir import EdgeKind, Node, NodeKind, Schematic, Status


def quadratic_drag(*, with_digest: bool = False) -> Schematic:
    sch = Schematic(meta={"id": "quadratic_drag.v0", "schema": "NsObservabilitySchematic@0.1"})
    sch.add(Node(id="u", kind=NodeKind.VARIABLE, attrs={"role": "input", "units": "N"}))
    sch.add(Node(id="x", kind=NodeKind.VARIABLE, attrs={"role": "state", "units": "m/s"}))
    sch.add(Node(id="xdot", kind=NodeKind.VARIABLE, attrs={"role": "state_dot", "units": "m/s^2"}))
    sch.add(Node(id="y", kind=NodeKind.VARIABLE, attrs={"role": "output", "units": "m/s"}))
    sch.add(Node(id="f", kind=NodeKind.FUNCTION, attrs={"class": "nonlinear", "model_ref": "jspt.reference.quadratic_drag", "x_star": [1.0], "c": 0.5, "law": "xdot = u - c * x * abs(x); y = x", "chart": "identity", "units": "SI"}))
    meas_attrs = {"quality": "undeclared"}
    if with_digest:
        meas_attrs["rci_digest"] = "fixture-not-a-field-sample"
        meas_attrs["quality"] = "fixture"
    sch.add(Node(id="ySensor", kind=NodeKind.MEASUREMENT, attrs=meas_attrs))
    sch.add(Node(id="observer", kind=NodeKind.OBSERVER, attrs={"status": Status.UNRESOLVED.value}))
    sch.connect(EdgeKind.INPUT, "u", "f")
    sch.connect(EdgeKind.INPUT, "x", "f")
    sch.connect(EdgeKind.OUTPUT, "f", "xdot")
    sch.connect(EdgeKind.OUTPUT, "f", "y")
    sch.connect(EdgeKind.ACTUATES, "u", "f")
    sch.connect(EdgeKind.MEASURES, "ySensor", "y")
    sch.connect(EdgeKind.OBSERVES, "observer", "f")
    sch.connect(EdgeKind.SENSES, "observer", "ySensor")
    return sch


def fixture_A_at_xstar(c: float, x_star: float) -> list[list[float]]:
    return [[-c * 2.0 * abs(x_star)]] if x_star != 0.0 else [[0.0]]
