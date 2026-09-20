import sys
import types

from schematics import Status, decide, quadratic_drag
from schematics.adapters.covariance import call_first_order_covariance
from schematics.ir import EdgeKind, Node, NodeKind
from schematics.pins import JSPT


def _with_A(*, sigma=None, fixture: bool = False):
    sch = quadratic_drag()
    attrs = dict(sch.node("f").attrs)
    if sigma is not None:
        attrs["sigma_x"] = sigma
    sch.replace(Node(id="f", kind=NodeKind.FUNCTION, attrs=attrs))
    sch.add(Node(id="cert:jspt:f", kind=NodeKind.CERTIFICATE, attrs={"owner": "jspt", "result": Status.SAMPLED.value, "A": [[-1.0]], "fixture": fixture}))
    sch.connect(EdgeKind.LINEARIZES, "cert:jspt:f", "f")
    return sch


def test_covariance_not_eligible_without_sigma():
    rows = [d for d in decide(quadratic_drag()) if d.tool == "jspt.first_order_covariance"]
    assert rows and rows[0].status is Status.NOT_ELIGIBLE


def test_fixture_A_does_not_open_covariance():
    rows = [d for d in decide(_with_A(sigma=[[0.04]], fixture=True)) if d.tool == "jspt.first_order_covariance"]
    assert rows and rows[0].status is Status.NOT_ELIGIBLE


def test_declared_sigma_opens_covariance():
    rows = [d for d in decide(_with_A(sigma=[[0.04]], fixture=False)) if d.tool == "jspt.first_order_covariance"]
    assert rows and rows[0].status is Status.ELIGIBLE


def test_covariance_missing_module_is_not_checked(monkeypatch):
    monkeypatch.setitem(sys.modules, "sensitivity", None)
    event = call_first_order_covariance(_with_A(sigma=[[0.04]], fixture=False), "f")
    assert event.result is Status.NOT_CHECKED
    assert JSPT["sha"] in str(event.detail)


def test_covariance_adapter_writes_sigma_y(monkeypatch):
    fake = types.ModuleType("sensitivity")
    fake.first_order_covariance = lambda J, S: [[0.04]]
    monkeypatch.setitem(sys.modules, "sensitivity", fake)
    sch = _with_A(sigma=[[0.04]], fixture=False)
    event = call_first_order_covariance(sch, "f")
    assert event.result is Status.SAMPLED
    cert = sch.node("cert:jspt.cov:f")
    assert cert.get("sigma_y") == [[0.04]]
    assert cert.get("exact_for_affine") is False
    assert "remainder" in cert.get("reason")
