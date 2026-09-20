import sys

from schematics import Status, quadratic_drag
from schematics.adapters.montecarlo import call_monte_carlo_covariance
from schematics.ir import EdgeKind, Node, NodeKind
from schematics.pins import JSPT


def test_mc_not_eligible_without_sigma():
    assert call_monte_carlo_covariance(quadratic_drag(), "f").result is Status.NOT_ELIGIBLE


def test_mc_missing_module_is_not_checked(monkeypatch):
    monkeypatch.setitem(sys.modules, "sensitivity", None)
    sch = quadratic_drag()
    attrs = dict(sch.node("f").attrs)
    attrs["sigma_x"] = [[0.04]]
    sch.replace(Node(id="f", kind=NodeKind.FUNCTION, attrs=attrs))
    sch.add(Node(id="cert:jspt:f", kind=NodeKind.CERTIFICATE, attrs={"owner": "jspt", "result": Status.SAMPLED.value, "A": [[-1.0]], "fixture": False}))
    sch.connect(EdgeKind.LINEARIZES, "cert:jspt:f", "f")
    event = call_monte_carlo_covariance(sch, "f")
    assert event.result is Status.NOT_CHECKED
    assert JSPT["sha"] in str(event.detail)
