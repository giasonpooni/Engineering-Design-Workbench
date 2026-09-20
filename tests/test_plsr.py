import sys
import types

from schematics import Status, decide, quadratic_drag, run
from schematics.adapters.plsr import call_evaluate
from schematics.ir import EdgeKind, Node, NodeKind
from schematics.pins import PLSR


def test_fixture_A_does_not_call_plsr():
    report = run(quadratic_drag(), attach_fixture_A=True, call_plsr=True)
    assert [d for d in report.decisions if d.tool == "lyapunov.evaluate"][0].status is Status.NOT_ELIGIBLE
    assert [e for e in report.events if e.tool == "lyapunov.evaluate" and e.result is Status.SAMPLED] == []


def test_plsr_missing_module_is_not_checked(monkeypatch):
    monkeypatch.setitem(sys.modules, "lyapunov", None)
    sch = quadratic_drag()
    sch.add(Node(id="cert:jspt:f", kind=NodeKind.CERTIFICATE, attrs={"owner": "jspt", "result": Status.SAMPLED.value, "A": [[-1.0]], "fixture": False}))
    sch.connect(EdgeKind.LINEARIZES, "cert:jspt:f", "f")
    event = call_evaluate(sch, "f")
    assert event.result is Status.NOT_CHECKED
    assert PLSR["sha"] in str(event.detail)


def test_plsr_adapter_with_fake_lyapunov(monkeypatch):
    fake = types.ModuleType("lyapunov")

    class Plant:
        dim = 1
        time = "continuous"
        name = "A"

    class Certificate:
        dim = 1
        name = "V"

    class Sample:
        P = [[1.0]]
        value = 1.0
        decrease = -2.0

    class Verdict:
        status = "certified"
        details = "ok"

    fake.plant_from_jacobian = lambda A, name="A", time="continuous": Plant()
    fake.certificate_for_plant = lambda plant, Q=None, name=None: Certificate()
    fake.evaluate = lambda plant, cert, x, **kw: Sample()
    fake.verdict = lambda plant, cert, x, **kw: Verdict()
    monkeypatch.setitem(sys.modules, "lyapunov", fake)
    sch = quadratic_drag()
    sch.add(Node(id="cert:jspt:f", kind=NodeKind.CERTIFICATE, attrs={"owner": "jspt", "result": Status.SAMPLED.value, "A": [[-1.0]], "fixture": False}))
    sch.connect(EdgeKind.LINEARIZES, "cert:jspt:f", "f")
    event = call_evaluate(sch, "f")
    assert event.result is Status.SAMPLED
    assert event.detail["verdict"] == "certified"
    assert sch.node("cert:lyapunov:f").get("P") == [[1.0]]


def test_identity_chart_is_not_eligible_for_transport():
    rows = [d for d in decide(quadratic_drag()) if d.tool == "jspt.check_coordinate_consistency"]
    assert rows and rows[0].status is Status.NOT_ELIGIBLE


def test_declared_scale_chart_is_eligible():
    sch = quadratic_drag()
    node = sch.node("f")
    sch.replace(Node(id="f", kind=NodeKind.FUNCTION, attrs={**dict(node.attrs), "chart": "milli", "chart_T": [[1000.0]], "chart_S": [[1000.0]], "chart_dx": [0.001]}))
    rows = [d for d in decide(sch) if d.tool == "jspt.check_coordinate_consistency"]
    assert rows and rows[0].status is Status.ELIGIBLE
